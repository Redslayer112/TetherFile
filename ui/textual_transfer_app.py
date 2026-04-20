import os
import socket
import threading
import re
from dataclasses import dataclass

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Log, ProgressBar, Select, Static

from core import CONFIG
from core.utils import clean_path
from transfers.lan import network as lan_network
from transfers.lan import receiver as lan_receiver
from transfers.lan import sender as lan_sender
from transfers.wan import network as wan_network
from transfers.wan import receiver as wan_receiver
from transfers.wan import sender as wan_sender


def _scan_fs_paths(s: str) -> list[str]:
    """Split a string of concatenated absolute paths using filesystem validation."""
    paths: list[str] = []
    i = 0
    while i < len(s):
        if s[i] == '/':
            best = None
            for j in range(len(s), i, -1):
                if os.path.exists(s[i:j]):
                    best = s[i:j]
                    break
            if best:
                paths.append(best)
                i += len(best)
            else:
                # No existing path here; treat everything from this / onwards as
                # one non-existent path (e.g. a new file being transferred).
                paths.append(s[i:])
                break
        else:
            i += 1
    return paths


def _extract_latest_path(raw: str) -> str:
    """
    Extract the most recently dropped/typed path from raw input text.
    Uses position tracking so the last path in the string always wins.
    Falls back to filesystem scanning for unquoted paths with spaces.
    Handles: single/double quotes, escaped spaces, & prefix, file:// URIs.
    """
    if not raw:
        return ""

    raw = raw.strip()
    if raw.startswith("& "):
        raw = raw[2:].lstrip()

    # Handle file:// URIs (some file managers paste these on drag-drop).
    if raw.startswith("file://"):
        from urllib.parse import unquote, urlparse
        path = unquote(urlparse(raw.splitlines()[0].strip()).path)
        if path:
            return os.path.normpath(path)

    # Collect (end_position, path) pairs — highest end_pos = most recent drop.
    found: list[tuple[int, str]] = []

    for m in re.finditer(
        r"'([^']+)'"                    # single-quoted  → group 1
        r'|"([^"]+)"'                   # double-quoted  → group 2
        r'|(/(?:[^\s\'"\\]|\\.)+)',     # unquoted /path → group 3
        raw,
    ):
        if m.group(1) is not None:
            found.append((m.end(), m.group(1)))
        elif m.group(2) is not None:
            found.append((m.end(), m.group(2)))
        elif m.group(3) is not None:
            found.append((m.end(), m.group(3).replace('\\ ', ' ')))

    if found:
        found.sort(key=lambda x: x[0])
        regex_best = os.path.normpath(found[-1][1])
        # If the regex-extracted path exists, use it immediately.
        if os.path.exists(regex_best):
            return regex_best

        # The regex may have fragmented an unquoted path with spaces.
        # Try filesystem scan — only prefer it if it found a LONGER existing
        # path (i.e. it successfully reassembled the fragments).
        fs = _scan_fs_paths(raw)
        if fs:
            fs_best = os.path.normpath(fs[-1])
            if os.path.exists(fs_best) and len(fs_best) > len(regex_best):
                return fs_best

        # Regex result is the best we have (path may not exist yet).
        return regex_best

    # No regex matches — try filesystem scan as last resort.
    fs = _scan_fs_paths(raw)
    if fs:
        return os.path.normpath(fs[-1])

    return clean_path(raw)


class PathInput(Input):
    """
    Input field for file/folder paths.
    Overrides Textual's default paste behaviour: a paste/drop REPLACES the
    field value with the extracted path instead of appending to it. This makes
    drag-and-drop ‘change of mind’ (drop a different file) Just Work.
    """

    def _on_paste(self, event: events.Paste) -> None:
        text = (event.text or "").strip()
        if not text:
            event.stop()
            return
        candidate = _extract_latest_path(text)
        # If extraction yields an absolute path, replace the entire field.
        if candidate.startswith('/'):
            # Guard against on_input_changed re-processing the clean value.
            self.app._updating_path = True
            try:
                self.value = candidate
                # Move cursor to end so the user sees the full path tail.
                self.cursor_position = len(candidate)
            finally:
                self.app._updating_path = False
        else:
            # Not a path — fall back to default insert behaviour (single line).
            line = text.splitlines()[0]
            if self.selection.is_empty:
                self.insert_text_at_cursor(line)
            else:
                self.replace(line, *self.selection)
        event.stop()


@dataclass
class _ReceiverState:
    mode: str | None = None
    thread: threading.Thread | None = None
    control: dict | None = None


class _ScreenShim:
    def __init__(self):
        self._nodelay = False
        self._timeout_ms = -1

    def clear(self):
        return

    def erase(self):
        return

    def refresh(self):
        return

    def nodelay(self, value):
        self._nodelay = bool(value)

    def timeout(self, ms):
        self._timeout_ms = int(ms)

    def move(self, *_):
        return

    def clrtoeol(self):
        return

    def getch(self):
        # Keep non-blocking loops alive and instantly skip "press key" waits.
        return 10


class _TextualTransferAdapter:
    def __init__(self, app: "TetherFileTextualApp"):
        self.app = app
        self.stdscr = _ScreenShim()
        self.height = 40
        self.width = 120

    def draw_header(self, title):
        self.app.call_from_thread(self.app._set_transfer_title, title)

    def print_colored(self, _y, _x, text, color='normal'):
        self.app.call_from_thread(self.app._append_log, f"[{color}] {text}")

    def draw_progress_bar(self, _y, _x, _width, progress, _title='', _color='info'):
        self.app.call_from_thread(self.app._set_progress, progress)

    def show_message(self, message, color='info', duration=0):
        self.app.call_from_thread(self.app._append_log, f"[{color}] {message}")


class TetherFileTextualApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #root {
        height: 1fr;
    }

    #mode_bar {
        height: auto;
        margin: 0 1;
    }

    .panel {
        border: round #4aa3ff;
        padding: 1;
        margin: 1;
        height: auto;
    }

    #status {
        color: cyan;
        margin: 0 1;
        height: auto;
    }

    #transfer_title {
        color: green;
        margin: 0 1;
        height: auto;
    }

    #progress {
        margin: 0 1;
        height: 1;
    }

    #log_panel {
        border: round #666666;
        margin: 1;
        height: 1fr;
    }

    #log_header {
        height: 3;
        align: center middle;
    }

    #log_title {
        width: 1fr;
        color: #aaaaaa;
    }

    #clear_log {
        width: 10;
        min-width: 10;
        height: 3;
        margin: 0 0 0 1;
        color: white;
        text-style: bold;
        content-align: center middle;
    }

    #log {
        height: 1fr;
        overflow-y: auto;
    }

    .row {
        height: auto;
        margin-bottom: 1;
    }

    .half {
        width: 1fr;
        margin-right: 1;
    }

    .ip_box {
        border: round #e2b714;
        padding: 0 1;
        margin-top: 1;
        height: auto;
    }

    .ip_label {
        color: #ffdf5d;
        text-style: bold;
        margin-bottom: 1;
    }

    .ip_value {
        border: tall #ffdf5d;
        width: 1fr;
    }

    .copy_btn {
        width: 14;
    }

    Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        ("l", "show_lan", "LAN"),
        ("w", "show_wan", "WAN"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self._active_mode = "lan"
        self._lan_recv = _ReceiverState()
        self._wan_recv = _ReceiverState()
        self.adapter = _TextualTransferAdapter(self)
        self._log_lines: list[str] = []
        self._updating_path = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="root"):
            with Horizontal(id="mode_bar"):
                yield Button("LAN", id="mode_lan", variant="primary")
                yield Button("WAN", id="mode_wan", variant="success")
                yield Button("Quit", id="mode_quit", variant="error")

            yield Static("Mode: LAN", id="status")
            yield Static("Idle", id="transfer_title")
            yield ProgressBar(total=100, id="progress")

            with Container(id="lan_panel", classes="panel"):
                yield Label("LAN / WiFi")
                with Horizontal(classes="row"):
                    yield Button("Refresh Interfaces", id="lan_refresh")
                    yield Select([], id="lan_iface", prompt="Select interface")
                with Horizontal(classes="row"):
                    yield Input(placeholder="Target IPv4", id="lan_target", classes="half")
                    yield Input(value=str(CONFIG['PORT']), placeholder="Port", id="lan_port", classes="half")
                with Horizontal(classes="row"):
                    yield PathInput(placeholder="File/Folder path (drag & drop or paste)", id="lan_path")
                with Horizontal(classes="row"):
                    yield Button("Send File", id="lan_send_file", variant="primary")
                    yield Button("Send Directory", id="lan_send_dir", variant="primary")
                    yield Button("Start Receiving", id="lan_receive_start", variant="success")
                    yield Button("Stop Receiving", id="lan_receive_stop", variant="warning")
                with Container(classes="ip_box"):
                    yield Static("Share This LAN IPv4 With Friend", classes="ip_label")
                    with Horizontal(classes="row"):
                        yield Input(value="-", id="lan_share_ipv4", classes="ip_value")
                        yield Button("Copy IP", id="lan_copy_ip", classes="copy_btn", variant="success")

            with Container(id="wan_panel", classes="panel"):
                yield Label("WAN / Internet")
                with Horizontal(classes="row"):
                    yield Input(value=str(CONFIG['PORT']), placeholder="Port", id="wan_port")
                with Horizontal(classes="row"):
                    yield Input(placeholder="Target host (IPv4/IPv6/hostname)", id="wan_target", classes="half")
                    yield PathInput(placeholder="File/Folder path (drag & drop or paste)", id="wan_path", classes="half")
                with Horizontal(classes="row"):
                    yield Button("Send File", id="wan_send_file", variant="primary")
                    yield Button("Send Directory", id="wan_send_dir", variant="primary")
                    yield Button("Start Receiving", id="wan_receive_start", variant="success")
                    yield Button("Stop Receiving", id="wan_receive_stop", variant="warning")
                with Container(classes="ip_box"):
                    yield Static("Share This WAN IPv6 With Friend", classes="ip_label")
                    with Horizontal(classes="row"):
                        yield Input(value="-", id="wan_share_ipv6", classes="ip_value")
                        yield Button("Copy IP", id="wan_copy_ip", classes="copy_btn", variant="success")
            with Container(id="log_panel"):
                with Horizontal(id="log_header"):
                    yield Static("Log", id="log_title")
                    yield Button("Clear", id="clear_log", variant="error")
                yield Log(id="log", auto_scroll=True, max_lines=400)
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_lan_interfaces()
        self._refresh_wan_addresses()
        self._show_mode("lan")

    def action_show_lan(self) -> None:
        self._show_mode("lan")

    def action_show_wan(self) -> None:
        self._show_mode("wan")

    def _show_mode(self, mode: str) -> None:
        self._active_mode = mode
        self.query_one("#lan_panel", Container).display = (mode == "lan")
        self.query_one("#wan_panel", Container).display = (mode == "wan")
        self.query_one("#status", Static).update(f"Mode: {mode.upper()}")

    def _append_log(self, message: str) -> None:
        log = self.query_one("#log", Log)
        self._log_lines.append(message)
        if len(self._log_lines) > 400:
            self._log_lines = self._log_lines[-400:]
        log.write_line(message)

    def _set_transfer_title(self, title: str) -> None:
        self.query_one("#transfer_title", Static).update(title)

    def _set_progress(self, progress: float) -> None:
        pct = max(0, min(100, int(progress * 100)))
        bar = self.query_one("#progress", ProgressBar)
        bar.update(progress=pct)

    def _refresh_lan_interfaces(self) -> None:
        try:
            interfaces = lan_network.get_all_network_interfaces()
            options = []
            ipv4_list = []
            for desc, ip, iface in interfaces:
                label = f"{desc} - {ip} ({iface})"
                options.append((label, ip))
                ipv4_list.append(ip)
            iface_select = self.query_one("#lan_iface", Select)
            iface_select.set_options(options)
            if not ipv4_list:
                fallback_ipv4 = self._get_fallback_ipv4()
                if fallback_ipv4:
                    ipv4_list.append(fallback_ipv4)
            text = ", ".join(ipv4_list) if ipv4_list else "-"
            if options:
                try:
                    iface_select.value = options[0][1]
                except Exception:
                    pass
                self.query_one("#lan_share_ipv4", Input).value = options[0][1]
            elif ipv4_list:
                self.query_one("#lan_share_ipv4", Input).value = ipv4_list[0]
            else:
                self.query_one("#lan_share_ipv4", Input).value = "-"
            self._append_log(f"[info] LAN interfaces refreshed ({len(options)} found)")
        except Exception as e:
            self._append_log(f"[error] Failed to refresh LAN interfaces: {e}")

    def _refresh_wan_addresses(self) -> None:
        shareable = wan_network.get_shareable_ipv6()
        if shareable:
            ipv6 = shareable['address']
            scope = shareable['scope']
            note = shareable['note']
            self.query_one("#wan_share_ipv6", Input).value = ipv6
            self._append_log(f"[info] {note}")
        else:
            self.query_one("#wan_share_ipv6", Input).value = "-"
            self._append_log("[warning] No IPv6 address detected")

    def _get_fallback_ipv4(self) -> str | None:
        """Best-effort local IPv4 discovery when interface filtering returns no LAN entries."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        return None

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "lan_iface":
            value = event.value if event.value else "-"
            self.query_one("#lan_share_ipv4", Input).value = str(value)

    def on_paste(self, event: events.Paste) -> None:
        """
        Global drop-anywhere handler.
        Routes three kinds of paste regardless of current focus:
          1. Absolute file path  → current mode's path field (lan_path / wan_path)
          2. IP / hostname       → current mode's target field (lan_target / wan_target)
          3. Misc / accidental   → ignored (no field touched)
        If the focused widget is already the correct destination, let normal
        input handling take over (on_input_changed cleans path fields).
        """
        text = (event.text or "").strip()
        if not text:
            return

        focused_id = getattr(self.focused, 'id', None)

        # ── 1. File path ────────────────────────────────────────────────────
        # event.text is the RAW pasted text only (not the combined Input value),
        # so _extract_latest_path here always sees a clean single path.
        # We intercept regardless of focus so the Input never appends to old text.
        candidate = _extract_latest_path(text)
        if candidate.startswith('/'):
            target_id = "lan_path" if self._active_mode == "lan" else "wan_path"
            self._updating_path = True
            try:
                self.query_one(f"#{target_id}", Input).value = candidate
            finally:
                self._updating_path = False
            event.stop()
            return

        # ── 2. IP / hostname ────────────────────────────────────────────────
        # Match: bare IPv4, IPv4:port, IPv6 (with or without brackets/port), hostname
        _IP_RE = re.compile(
            r'^('
            r'\[?[0-9a-fA-F:]+\]?'          # IPv6 (bare or bracketed)
            r'|(?:\d{1,3}\.){3}\d{1,3}'     # IPv4
            r'|[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z]{2,})+' # hostname
            r')(?::\d+)?$'                   # optional :port
        )
        # Strip port suffix to get just the address for the field
        ip_text = text.split(':', 1)[0].strip('[]') if ':' in text else text
        if _IP_RE.match(text):
            if focused_id in ('lan_target', 'wan_target'):
                return  # already in the right field, let it type normally
            target_id = "lan_target" if self._active_mode == "lan" else "wan_target"
            self.query_one(f"#{target_id}", Input).value = ip_text
            event.stop()
            return

        # ── 3. Misc / accidental — do nothing ──────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._updating_path:
            return
        # Path fields are handled by PathInput._on_paste directly;
        # no post-processing needed here.

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "mode_lan":
            self._show_mode("lan")
            return
        if button_id == "mode_wan":
            self._show_mode("wan")
            return
        if button_id == "mode_quit":
            self.exit()
            return

        if button_id == "lan_refresh":
            self._refresh_lan_interfaces()
            return

        if button_id == "clear_log":
            self._log_lines.clear()
            self.query_one("#log", Log).clear()
            return

        if button_id == "lan_copy_ip":
            self._copy_to_clipboard("#lan_share_ipv4", "LAN IPv4")
            return
        if button_id == "wan_copy_ip":
            self._copy_to_clipboard("#wan_share_ipv6", "WAN IPv6")
            return

        if button_id == "lan_send_file":
            self._start_send("lan", is_directory=False)
            return
        if button_id == "lan_send_dir":
            self._start_send("lan", is_directory=True)
            return
        if button_id == "wan_send_file":
            self._start_send("wan", is_directory=False)
            return
        if button_id == "wan_send_dir":
            self._start_send("wan", is_directory=True)
            return

        if button_id == "lan_receive_start":
            self._start_receive("lan")
            return
        if button_id == "wan_receive_start":
            self._start_receive("wan")
            return
        if button_id == "lan_receive_stop":
            self._stop_receive("lan")
            return
        if button_id == "wan_receive_stop":
            self._stop_receive("wan")
            return

    def _copy_to_clipboard(self, widget_id: str, label: str) -> None:
        value = self.query_one(widget_id, Input).value.strip()
        if not value or value == "-":
            self._append_log(f"[warning] {label} is not available to copy")
            return

        # Try pyperclip first (uses xclip on Linux, reliable in real terminals).
        try:
            import pyperclip
            pyperclip.copy(value)
            self._append_log(f"[success] Copied {label}: {value}")
            return
        except Exception:
            pass

        # Fallback: xclip directly.
        try:
            import subprocess
            proc = subprocess.Popen(
                ['xclip', '-selection', 'clipboard'],
                stdin=subprocess.PIPE,
            )
            proc.communicate(input=value.encode())
            if proc.returncode == 0:
                self._append_log(f"[success] Copied {label}: {value}")
                return
        except Exception:
            pass

        # Last resort: OSC 52 via Textual driver.
        try:
            self.copy_to_clipboard(value)
            self._append_log(f"[success] Copied {label}: {value}")
        except Exception:
            self._append_log(f"[warning] Clipboard not available — select and copy manually: {value}")

    def _start_send(self, mode: str, is_directory: bool) -> None:
        if mode == "lan":
            target = self.query_one("#lan_target", Input).value.strip()
            path = clean_path(self.query_one("#lan_path", Input).value)
            port_str = self.query_one("#lan_port", Input).value.strip() or str(CONFIG['PORT'])
            local_ip = self.query_one("#lan_iface", Select).value
            if not local_ip:
                self._append_log("[error] Select a LAN interface first.")
                return
            if not target or not lan_network.validate_ip(target):
                self._append_log("[error] Invalid LAN target IPv4.")
                return
            try:
                port = int(port_str)
            except ValueError:
                self._append_log("[error] Invalid LAN port.")
                return

            def _worker():
                ok = False
                if is_directory:
                    ok = lan_sender.send_directory(path, target, port, local_ip, self.adapter)
                else:
                    ok = lan_sender.send_file(path, target, port, local_ip, self.adapter)
                self.call_from_thread(self._append_log, f"[{'success' if ok else 'error'}] {'Directory' if is_directory else 'File'} transfer {'completed' if ok else 'failed'}")

            threading.Thread(target=_worker, daemon=True).start()
            return

        target = self.query_one("#wan_target", Input).value.strip()
        path = clean_path(self.query_one("#wan_path", Input).value)
        port_str = self.query_one("#wan_port", Input).value.strip() or str(CONFIG['PORT'])
        if not wan_network.validate_target_host(target):
            self._append_log("[error] Invalid WAN target host/IP.")
            return
        try:
            port = int(port_str)
        except ValueError:
            self._append_log("[error] Invalid WAN port.")
            return

        def _worker():
            ok = False
            if is_directory:
                ok = wan_sender.send_directory(path, target, port, self.adapter)
            else:
                ok = wan_sender.send_file(path, target, port, self.adapter)
            self.call_from_thread(self._append_log, f"[{'success' if ok else 'error'}] {'Directory' if is_directory else 'File'} transfer {'completed' if ok else 'failed'}")

        threading.Thread(target=_worker, daemon=True).start()

    def _start_receive(self, mode: str) -> None:
        recv = self._lan_recv if mode == "lan" else self._wan_recv
        if recv.thread and recv.thread.is_alive():
            self._append_log(f"[warning] {mode.upper()} receiver is already running.")
            return

        control = {'running': False, 'socket': None, 'single_transfer': True}
        if mode == "lan":
            local_ip = self.query_one("#lan_iface", Select).value
            if not local_ip:
                self._append_log("[error] Select a LAN interface first.")
                return
            port_str = self.query_one("#lan_port", Input).value.strip() or str(CONFIG['PORT'])
            try:
                port = int(port_str)
            except ValueError:
                self._append_log("[error] Invalid LAN port.")
                return

            def _worker():
                lan_receiver.start_server(local_ip, port, self.adapter, control)
                self.call_from_thread(self._append_log, "[info] LAN receive session ended.")

            thread = threading.Thread(target=_worker, daemon=True)
            self._lan_recv = _ReceiverState(mode=mode, thread=thread, control=control)
            thread.start()

        else:
            bind_ip = str(CONFIG.get('WAN_BIND_IP', '')).strip()
            port_str = self.query_one("#wan_port", Input).value.strip() or str(CONFIG['PORT'])
            try:
                port = int(port_str)
            except ValueError:
                self._append_log("[error] Invalid WAN port.")
                return

            def _worker():
                wan_receiver.start_server(bind_ip, port, self.adapter, control)
                self.call_from_thread(self._append_log, "[info] WAN receive session ended.")

            thread = threading.Thread(target=_worker, daemon=True)
            self._wan_recv = _ReceiverState(mode=mode, thread=thread, control=control)
            thread.start()

        self._append_log(f"[success] {mode.upper()} receive mode started.")

    def _stop_receive(self, mode: str) -> None:
        recv = self._lan_recv if mode == "lan" else self._wan_recv
        if not recv.control:
            self._append_log(f"[warning] {mode.upper()} receiver is not running.")
            return

        try:
            if mode == "lan":
                lan_receiver.stop_server(recv.control)
            else:
                wan_receiver.stop_server(recv.control)
            self._append_log(f"[warning] {mode.upper()} receive mode stopped by user.")
        except Exception as e:
            self._append_log(f"[error] Failed to stop {mode.upper()} receiver: {e}")


def run_textual_transfer_app() -> None:
    app = TetherFileTextualApp()
    app.run()
