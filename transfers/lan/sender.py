import struct
import time
import os
import socket
import json
import threading
import hashlib
from core import CONFIG
from transfers.lan.network import create_socket
from transfers.lan.protocol import ACK_METADATA, DONE, FAIL, MISMATCH
from core.utils import collect_directory_files, exceeds_size_limit, format_size, get_hash_digest_size
from core.progress import ProgressTracker

BUFFER_SIZE = CONFIG['BUFFER_SIZE']
TRANSFER_TYPES = CONFIG['TRANSFER_TYPES']
HASH_ALGORITHM = CONFIG['HASH_ALGORITHM']
CONNECTION_TIMEOUT = CONFIG['CONNECTION_TIMEOUT']
MAX_FILE_SIZE_MB = CONFIG['MAX_FILE_SIZE_MB']
MAX_DIRECTORY_FILES = CONFIG['MAX_DIRECTORY_FILES']

ui_lock = threading.Lock()

def _handle_hash_mismatch(ui, sock):
    """Handle hash algorithm mismatch display and user input"""
    ui.stdscr.clear()
    ui.draw_header("⚠️ Hash Algorithm Mismatch")
    ui.print_colored(4, 2, f"📤 You are using: {HASH_ALGORITHM.upper()}", 'error')
    ui.print_colored(5, 2, "📥 Receiver is using a different algorithm", 'error')

    ui.print_colored(7, 2, "💡 Solutions:", 'highlight')
    ui.print_colored(8, 4, "1. Match HASH_ALGORITHM in config.json with receiver", 'info')
    ui.print_colored(9, 4, "2. Set SKIP_HASH_VERIFICATION = True in config.json (receiver side)", 'info')
    ui.print_colored(10, 4, "3. Ask receiver to change their hash algorithm", 'info')
    ui.print_colored(12, 2, "Press any key to continue...", 'warning')

    ui.stdscr.refresh()
    # Use nodelay to make it non-blocking, then restore blocking mode
    ui.stdscr.nodelay(True)
    try:
        # Wait for input with timeout
        start_time = time.time()
        while time.time() - start_time < 10:  # 10 second timeout
            try:
                key = ui.stdscr.getch()
                if key != -1:  # Key was pressed
                    break
            except Exception:
                pass
            time.sleep(0.1)
    finally:
        ui.stdscr.nodelay(False)  # Restore blocking mode


def _receive_acknowledgment(sock, expected_responses, timeout=30):
    """
    Receive and validate acknowledgment from receiver
    Args:
        sock: socket object
        expected_responses: list of expected byte responses
        timeout: timeout in seconds
    Returns:
        tuple: (success, response) where success is bool and response is bytes
    """
    try:
        sock.settimeout(timeout)
        max_length = max(len(resp) for resp in expected_responses)
        response = _recv_exact(sock, max_length)

        for expected in expected_responses:
            if response.startswith(expected):
                return True, expected

        if not response:
            return False, b'EOF'

        return False, response

    except socket.timeout:
        return False, b'TIMEOUT'
    except Exception as e:
        return False, str(e).encode()

    
def _recv_exact(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            break
        data += chunk
    return data


def _stream_send_file(sock, filepath, file_size, progress, sent_so_far=0):
    """Stream file_size bytes from filepath into sock while computing the
    configured hash in a single pass. Returns (digest_bytes, sent_total_after).

    Uses a pre-allocated bytearray + memoryview + readinto so no Python bytes
    object is allocated per chunk (halves disk I/O vs. pre-hash + send).
    """
    hash_func = hashlib.new(HASH_ALGORITHM)
    buf = bytearray(BUFFER_SIZE)
    view = memoryview(buf)
    sent_total = sent_so_far
    sent_in_file = 0

    with open(filepath, 'rb') as f:
        while sent_in_file < file_size:
            remaining = file_size - sent_in_file
            n = f.readinto(view if remaining >= BUFFER_SIZE else view[:remaining])
            if not n:
                raise IOError(f"Unexpected EOF: {filepath}")
            chunk = view[:n]
            hash_func.update(chunk)
            sock.sendall(chunk)
            sent_in_file += n
            sent_total += n
            progress.update(sent_total)

    return hash_func.digest(), sent_total


def send_file(filepath, target_ip, port, local_ip, ui):
    if not os.path.exists(filepath):
        with ui_lock:
            ui.show_message(f"❌ File not found: {filepath}", 'error')
        return False

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)

    if exceeds_size_limit(file_size, MAX_FILE_SIZE_MB):
        with ui_lock:
            ui.show_message(f"❌ File exceeds {MAX_FILE_SIZE_MB} MB limit ({format_size(file_size)})", 'error')
        return False

    ui.stdscr.clear()
    ui.draw_header(f"📤 Sending File: {filename}")
    ui.print_colored(4, 2, f"📄 Size: {format_size(file_size)}", 'info')
    ui.print_colored(5, 2, f"🎯 Target: {target_ip}", 'info')

    sock = None
    try:
        sock = create_socket(local_ip)
        sock.settimeout(15)  # short timeout just for the connect handshake
        ui.print_colored(7, 2, f"🔗 Connecting to {target_ip}...", 'warning')
        ui.stdscr.refresh()
        sock.connect((target_ip, port))
        sock.settimeout(max(CONNECTION_TIMEOUT, file_size // (1024 * 256)))  # extend for transfer

        ui.print_colored(8, 2, f"✅ Connected to receiver at {target_ip}:{port}", 'success')
        ui.stdscr.refresh()

        # Streaming hash: digest is computed during send and appended as a
        # raw 32-byte trailer (for sha256). No more pre-flight disk pass.
        file_info = {
            'type': TRANSFER_TYPES['FILE'],
            'name': filename,
            'size': file_size,
            'hash_algorithm': HASH_ALGORITHM,
            'timestamp': time.time()
        }

        metadata = json.dumps(file_info).encode('utf-8')
        sock.sendall(struct.pack('!I', len(metadata)))
        sock.sendall(metadata)

        # Handle acknowledgment with proper error checking
        success, response = _receive_acknowledgment(sock, [ACK_METADATA, MISMATCH])
        if not success:
            if response == b'TIMEOUT':
                raise socket.timeout("Timeout waiting for metadata acknowledgment")
            else:
                raise Exception(f"Failed to receive metadata acknowledgment: {response}")

        if response == MISMATCH:
            _handle_hash_mismatch(ui, sock)
            return False

        # Continue with file transfer (stream + hash in one pass).
        progress = ProgressTracker(file_size, f"📤 Sending {filename}", ui)
        try:
            digest, _ = _stream_send_file(sock, filepath, file_size, progress)
        except socket.timeout:
            raise socket.timeout("Timeout during file transfer")
        except socket.error as e:
            raise socket.error(f"Network error during transfer: {e}")

        # Per-file digest trailer (raw bytes; receiver knows length from algorithm).
        sock.sendall(digest)

        # Receive final acknowledgment
        success, response = _receive_acknowledgment(sock, [DONE, FAIL])
        if response == FAIL:
            raise Exception("Receiver reported failure")

        if not success:
            if response == b'TIMEOUT':
                raise socket.timeout("Timeout waiting for completion acknowledgment")
            else:
                raise Exception(f"Failed to receive completion acknowledgment: {response}")

        return True

    except socket.timeout as e:
        with ui_lock:
            ui.show_message(f"⏰ Connection timeout: {e}", 'error')
        return False
    except ConnectionRefusedError:
        with ui_lock:
            ui.show_message(f"🚫 Connection refused: Receiver might not be running on {target_ip}:{port}", 'error')
        return False
    except socket.error as e:
        with ui_lock:
            ui.show_message(f"🌐 Network error: {e}", 'error')
        return False
    except Exception as e:
        with ui_lock:
            ui.show_message(f"❌ Error sending file: {e}", 'error')
        return False
    finally:
        if sock:
            try: 
                sock.close()
            except Exception: 
                pass

def send_directory(dir_path, target_ip, port, local_ip, ui):
    """Send entire directory (single-session, protocol-clean)"""
    if not os.path.isdir(dir_path):
        with ui_lock:
            ui.show_message(f"Directory not found: {dir_path}", 'error')
        return False

    dirname = os.path.basename(dir_path)
    ui.stdscr.clear()
    ui.draw_header(f"Sending Directory: {dirname}")

    sock = None
    try:
        sock = create_socket(local_ip)
        sock.settimeout(15)

        ui.print_colored(4, 2, f"Connecting to {target_ip}:{port}...", 'warning')
        ui.stdscr.refresh()
        sock.connect((target_ip, port))
        sock.settimeout(CONNECTION_TIMEOUT)

        ui.print_colored(5, 2, "Scanning directory...", 'warning')
        ui.stdscr.refresh()
        files_info, total_size = collect_directory_files(dir_path)
        sock.settimeout(max(CONNECTION_TIMEOUT, total_size // (1024 * 256)))

        if not files_info:
            with ui_lock:
                ui.show_message("No files found in directory", 'error')
            return False

        if len(files_info) > MAX_DIRECTORY_FILES:
            with ui_lock:
                ui.show_message(f"❌ Directory has {len(files_info)} files (limit: {MAX_DIRECTORY_FILES})", 'error')
            return False

        if exceeds_size_limit(total_size, MAX_FILE_SIZE_MB):
            with ui_lock:
                ui.show_message(f"❌ Directory exceeds {MAX_FILE_SIZE_MB} MB limit ({format_size(total_size)})", 'error')
            return False

        ui.print_colored(
            6, 2,
            f"{len(files_info)} files, total size: {format_size(total_size)}",
            'info'
        )

        # Per-file hashes are streamed as trailers during send — no pre-flight pass.
        metadata_files = [
            {
                'path': f['path'],
                'size': f['size'],
            }
            for f in files_info
        ]

        dir_info = {
            'type': TRANSFER_TYPES['DIRECTORY'],
            'name': dirname,
            'files': metadata_files,
            'total_files': len(files_info),
            'total_size': total_size,
            'hash_algorithm': HASH_ALGORITHM,
            'timestamp': time.time()
        }

        metadata = json.dumps(dir_info).encode('utf-8')
        sock.sendall(struct.pack('!I', len(metadata)))
        sock.sendall(metadata)

        success, response = _receive_acknowledgment(sock, [ACK_METADATA, MISMATCH])
        if not success:
            raise Exception(f"Metadata acknowledgment failed: {response}")

        if response == MISMATCH:
            _handle_hash_mismatch(ui, sock)
            return False

        progress = ProgressTracker(total_size, f"Sending {dirname}", ui)
        sent_total = 0

        for i, file_info in enumerate(files_info, 1):
            ui.print_colored(
                ui.height - 5, 2,
                f"[{i}/{len(files_info)}] {file_info['path']}",
                'special'
            )
            ui.stdscr.refresh()

            digest, sent_total = _stream_send_file(
                sock, file_info['full_path'], file_info['size'], progress, sent_total
            )
            # Per-file digest trailer.
            sock.sendall(digest)

        # Final completion ACK
        success, response = _receive_acknowledgment(sock, [DONE], timeout=30)
        if not success:
            raise Exception(f"Final acknowledgment failed: {response}")

        return True

    except Exception as e:
        with ui_lock:
            ui.show_message(f"Error sending directory: {e}", 'error')
        return False

    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass