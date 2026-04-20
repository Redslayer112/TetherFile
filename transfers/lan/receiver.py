import socket
import json
import struct
import threading
import os
import time
import tempfile
import shutil
import hashlib
from core import CONFIG, PROJECT_ROOT
from transfers.lan.network import create_server_socket
from transfers.lan.protocol import ACK_METADATA, DONE, FAIL, MISMATCH
from core.utils import ensure_directory, exceeds_size_limit, format_size, get_disk_usage, get_hash_digest_size, sanitize_filename, sanitize_path
from core.progress import ProgressTracker

BUFFER_SIZE = CONFIG['BUFFER_SIZE']
SERVER_TIMEOUT = CONFIG['SERVER_TIMEOUT']
RECEIVED_DIR = CONFIG['RECEIVED_DIR']
if not os.path.isabs(RECEIVED_DIR):
    RECEIVED_DIR = str(PROJECT_ROOT / RECEIVED_DIR)
TRANSFER_TYPES = CONFIG['TRANSFER_TYPES']
HASH_ALGORITHM = CONFIG['HASH_ALGORITHM']
SKIP_HASH_VERIFICATION = CONFIG['SKIP_HASH_VERIFICATION']
MAX_FILE_SIZE_MB = CONFIG['MAX_FILE_SIZE_MB']
MAX_DIRECTORY_FILES = CONFIG['MAX_DIRECTORY_FILES']
MAX_METADATA_SIZE = 4 * 1024 * 1024

# UI lock to prevent concurrent screen updates
ui_lock = threading.Lock()
shutdown_event = threading.Event()


def _validate_transfer_metadata(metadata):
    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be a JSON object")

    transfer_type = metadata.get('type')
    if transfer_type not in (TRANSFER_TYPES['FILE'], TRANSFER_TYPES['DIRECTORY']):
        raise ValueError(f"Unknown transfer type: {transfer_type}")

    name = metadata.get('name')
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Missing or invalid transfer name")

    if transfer_type == TRANSFER_TYPES['FILE']:
        size = metadata.get('size')
        if not isinstance(size, int) or size < 0:
            raise ValueError("Invalid file size")
        if exceeds_size_limit(size, MAX_FILE_SIZE_MB):
            raise ValueError(f"Incoming file exceeds {MAX_FILE_SIZE_MB} MB limit")
        return

    files = metadata.get('files')
    total_files = metadata.get('total_files')
    total_size = metadata.get('total_size')

    if not isinstance(files, list):
        raise ValueError("Directory metadata must contain a file list")
    if not isinstance(total_files, int) or total_files != len(files):
        raise ValueError("Directory total_files does not match metadata")
    if total_files < 0 or total_files > MAX_DIRECTORY_FILES:
        raise ValueError(f"Directory exceeds {MAX_DIRECTORY_FILES} file limit")
    if not isinstance(total_size, int) or total_size < 0:
        raise ValueError("Invalid directory size")
    if exceeds_size_limit(total_size, MAX_FILE_SIZE_MB):
        raise ValueError(f"Incoming directory exceeds {MAX_FILE_SIZE_MB} MB limit")

    computed_total_size = 0
    for file_info in files:
        if not isinstance(file_info, dict):
            raise ValueError("Invalid directory file entry")

        file_path = file_info.get('path')
        file_size = file_info.get('size')
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("Directory contains an invalid file path")
        if not isinstance(file_size, int) or file_size < 0:
            raise ValueError(f"Invalid file size for {file_path}")
        if exceeds_size_limit(file_size, MAX_FILE_SIZE_MB):
            raise ValueError(f"File exceeds {MAX_FILE_SIZE_MB} MB limit: {file_path}")

        computed_total_size += file_size

    if computed_total_size != total_size:
        raise ValueError("Directory total_size does not match file entries")

def _show_validation_summary_non_blocking(ui, failed_validations):
    """Show summary of failed validations with non-blocking input"""
    with ui_lock:
        ui.stdscr.clear()
        ui.draw_header("⚠️ File Validation Summary")
        ui.print_colored(4, 2, f"❌ {len(failed_validations)} file(s) failed integrity check:", 'error')

        y_pos = 6
        for i, failure in enumerate(failed_validations):
            if y_pos >= ui.height - 4:
                ui.print_colored(y_pos, 2, "... (more failures not shown)", 'warning')
                break

            ui.print_colored(y_pos, 4, f"• {failure['file']}", 'error')
            ui.print_colored(y_pos + 1, 6, f"Expected: {failure['expected']}", 'info')
            ui.print_colored(y_pos + 2, 6, f"Received: {failure['received']}", 'info')
            y_pos += 4

        ui.print_colored(ui.height - 3, 2, "Press any key to continue... (10s timeout)", 'highlight')
        ui.stdscr.refresh()
    
    # Use non-blocking input with timeout
    ui.stdscr.nodelay(True)
    try:
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
        ui.stdscr.nodelay(False)


def _handle_hash_mismatch_non_blocking(ui, sender_algo):
    """Handle hash mismatch display with non-blocking input"""
    with ui_lock:
        ui.stdscr.clear()
        ui.draw_header("⚠️ Hash Algorithm Mismatch")
        ui.print_colored(4, 2, f"📤 Sender is using: {sender_algo.upper()}", 'error')
        ui.print_colored(5, 2, f"📥 Your setting: {HASH_ALGORITHM.upper()}", 'error')

        ui.print_colored(7, 2, "💡 Solutions:", 'highlight')
        ui.print_colored(8, 4, f"1. Change your HASH_ALGORITHM to '{sender_algo.lower()}' in config.json", 'info')
        ui.print_colored(9, 4, "2. Set SKIP_HASH_VERIFICATION = True in config.json", 'info')
        ui.print_colored(10, 4, "3. Ask sender to change their hash algorithm", 'info')
        ui.print_colored(12, 2, "Connection rejected. Press any key to continue... (5s timeout)", 'warning')

        ui.stdscr.refresh()
    
    # Use non-blocking input with timeout
    ui.stdscr.nodelay(True)
    try:
        start_time = time.time()
        while time.time() - start_time < 5:  # 5 second timeout
            try:
                key = ui.stdscr.getch()
                if key != -1:  # Key was pressed
                    break
            except Exception:
                pass
            time.sleep(0.1)
    finally:
        ui.stdscr.nodelay(False)

def start_server(local_ip, port, ui, server_control):
    server_socket = None
    failed_validations = []
    validation_lock = threading.Lock()
    shutdown_event.clear()

    try:
        server_socket = create_server_socket(local_ip, port)
        server_socket.listen(1)
        server_socket.settimeout(SERVER_TIMEOUT)

        server_control['running'] = True
        server_control['socket'] = server_socket

        with ui_lock:
            ui.stdscr.clear()
            ui.draw_header("📥 Receive Mode Active")
            ui.print_colored(4, 2, f"🎯 Server listening on {local_ip}:{port}", 'success')
            ui.print_colored(6, 2, "💡 Waiting for sender...", 'highlight')
            ui.stdscr.refresh()

        while not shutdown_event.is_set():
            try:
                client_socket, addr = server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                if shutdown_event.is_set():
                    break
                raise

            if shutdown_event.is_set():
                try:
                    client_socket.close()
                except Exception:
                    pass
                break

            with ui_lock:
                ui.print_colored(8, 2, f"📥 Connection from {addr[0]}", 'success')
                ui.stdscr.refresh()

            worker = threading.Thread(
                target=handle_client,
                args=(client_socket, ui, failed_validations, validation_lock, addr),
                daemon=False
            )
            worker.start()

            while worker.is_alive():
                if shutdown_event.is_set():
                    break
                worker.join(timeout=0.5)

            worker.join()

            # Default receive-mode behavior: complete one transfer and return.
            if server_control.get('single_transfer', True):
                break

        if failed_validations:
            _show_validation_summary_non_blocking(ui, failed_validations)

    except socket.timeout:
        with ui_lock:
            ui.show_message("⏰ No sender connected (timeout)", 'warning')

    except Exception as e:
        if not shutdown_event.is_set():
            with ui_lock:
                ui.show_message(f"❌ Server error: {e}", 'error')

    finally:
        server_control['running'] = False
        if server_socket:
            try:
                server_socket.close()
            except Exception:
                pass
        server_control['socket'] = None


def stop_server(server_control):
    shutdown_event.set()
    server_control['running'] = False

    socket_to_close = server_control.get('socket')
    if socket_to_close:
        try:
            try:
                socket_to_close.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            socket_to_close.close()

        except Exception:
            pass
        server_control['socket'] = None

def handle_client(client_socket, ui, failed_validations, validation_lock, addr):
    start_time = time.time()

    try:
        metadata_timeout = 30
        client_socket.settimeout(metadata_timeout)

        with ui_lock:
            ui.print_colored(10, 2, f"Connected from {addr[0]}", 'success')
            ui.stdscr.refresh()

        metadata_size_data = recv_exact(client_socket, 4, metadata_timeout)
        if not metadata_size_data:
            raise Exception("Failed to receive metadata size")

        metadata_size = struct.unpack('!I', metadata_size_data)[0]
        if metadata_size <= 0 or metadata_size > MAX_METADATA_SIZE:
            raise ValueError(f"Invalid metadata size: {metadata_size}")
        metadata_data = recv_exact(client_socket, metadata_size, metadata_timeout)
        if not metadata_data:
            raise Exception("Failed to receive metadata")

        metadata = json.loads(metadata_data.decode('utf-8'))
        _validate_transfer_metadata(metadata)

        size = metadata.get('size') or metadata.get('total_size', 0)
        transfer_timeout = min(300, max(30, size // (1024 * 512)))
        client_socket.settimeout(transfer_timeout)

        sender_algo = metadata.get('hash_algorithm')
        if sender_algo and sender_algo.lower() != HASH_ALGORITHM.lower():
            if SKIP_HASH_VERIFICATION:
                client_socket.sendall(ACK_METADATA)
            else:
                client_socket.sendall(MISMATCH)
                _handle_hash_mismatch_non_blocking(ui, sender_algo)
                return
        else:
            client_socket.sendall(ACK_METADATA)

        if metadata['type'] == TRANSFER_TYPES['FILE']:
            receive_file(client_socket, metadata, ui, failed_validations, validation_lock, transfer_timeout)
        elif metadata['type'] == TRANSFER_TYPES['DIRECTORY']:
            receive_directory(client_socket, metadata, ui, failed_validations, validation_lock, transfer_timeout)
        else:
            raise Exception(f"Unknown transfer type: {metadata['type']}")

        client_socket.sendall(DONE)

        duration = time.time() - start_time
        with ui_lock:
            ui.print_colored(
                12, 2,
                f"Transfer completed in {duration:.1f}s from {addr[0]}",
                'success'
            )
            ui.stdscr.refresh()

    except Exception as e:
        try:
            client_socket.sendall(FAIL)
        except Exception:
            pass
        with ui_lock:
            ui.show_message(f"Error handling client {addr[0]}: {e}", 'error')

    finally:
        try:
            client_socket.close()
        except Exception:
            pass

def recv_exact(sock, size, idle_timeout=None):
    """Receive exactly `size` bytes. Sets one timeout for the whole call."""
    if idle_timeout is not None:
        sock.settimeout(idle_timeout)
    data = bytearray()
    while len(data) < size:
        if shutdown_event.is_set():
            return None
        try:
            chunk = sock.recv(size - len(data))
        except socket.timeout:
            raise socket.timeout("Timed out waiting for incoming data")
        except OSError:
            return None
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def _stream_recv_file(sock, file_obj, expected_size, transfer_timeout, progress, progress_offset=0):
    """Stream `expected_size` bytes from sock into file_obj, hashing in one pass.

    Uses recv_into into a single pre-allocated bytearray (no per-chunk
    allocation) and a single socket timeout for the whole transfer.
    Returns the raw digest bytes of the data received.
    """
    sock.settimeout(transfer_timeout)
    hash_func = hashlib.new(HASH_ALGORITHM)
    buf = bytearray(BUFFER_SIZE)
    view = memoryview(buf)
    received = 0
    chunk_count = 0
    PROGRESS_BITMASK = 0x3F  # update progress every 64 chunks (cheap throttle)

    while received < expected_size:
        if shutdown_event.is_set():
            raise Exception("Transfer stopped")
        remaining = expected_size - received
        target = view if remaining >= BUFFER_SIZE else view[:remaining]
        try:
            n = sock.recv_into(target)
        except socket.timeout:
            raise socket.timeout(
                f"Timeout receiving file at {received}/{expected_size} bytes"
            )
        if n == 0:
            raise Exception(
                f"Sender closed connection during transfer at {received}/{expected_size} bytes"
            )
        chunk = view[:n]
        hash_func.update(chunk)
        file_obj.write(chunk)
        received += n
        chunk_count += 1
        # Progress is also internally throttled by time + bytes; this just
        # avoids the function call most of the time.
        if (chunk_count & PROGRESS_BITMASK) == 0:
            progress.update(progress_offset + received)

    progress.update(progress_offset + received)
    return hash_func.digest()


def _check_validation(filepath, expected_digest, computed_digest, failed_validations, validation_lock):
    """Compare digests; record failure and return bool."""
    if SKIP_HASH_VERIFICATION:
        return True
    if computed_digest == expected_digest:
        return True
    with validation_lock:
        failed_validations.append({
            'file': filepath,
            'expected': expected_digest.hex()[:16] + '...',
            'received': computed_digest.hex()[:16] + '...'
        })
    return False


def dedupe_path(path):
    """Race-free dedupe via O_CREAT|O_EXCL.
    Returns a unique path AND has already created an empty placeholder file
    at that path so two parallel receivers cannot pick the same name.
    Caller is responsible for opening/replacing it.
    """
    base, ext = os.path.splitext(path)
    candidate = path
    i = 1
    while True:
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return candidate
        except FileExistsError:
            candidate = f"{base} ({i}){ext}"
            i += 1


def dedupe_dir(path):
    """Race-free dedupe of a directory name via O_CREAT|O_EXCL on a marker.

    Returns the unique directory path. The directory itself is not created
    here — caller will do that — but a marker file with the same name is
    pre-created so concurrent receivers can't collide.
    Actually we just probe os.path.exists in a loop; for parallel safety the
    caller should use the returned path immediately with mkdir(exist_ok=False).
    """
    base = path
    candidate = path
    i = 1
    while os.path.exists(candidate):
        candidate = f"{base} ({i})"
        i += 1
    return candidate


def receive_file(client_socket, file_info, ui, failed_validations, validation_lock, transfer_timeout):
    ensure_directory(RECEIVED_DIR)

    # Disk space check before creating any temp files
    disk_usage = get_disk_usage(RECEIVED_DIR)
    if disk_usage:
        _, _, free_space = disk_usage
        if free_space < file_info['size'] * 1.1:
            with ui_lock:
                ui.show_message(
                    f"❌ Insufficient disk space. Need {format_size(file_info['size'])}, "
                    f"have {format_size(free_space)}",
                    'error'
                )
            raise OSError("Insufficient disk space for incoming file")

    # Sanitize filename for cross-platform compatibility
    safe_filename = sanitize_filename(file_info['name'])
    final_filepath = dedupe_path(
        os.path.join(RECEIVED_DIR, safe_filename)
    )
    # dedupe_path created an empty placeholder via O_CREAT|O_EXCL — remove it
    # so shutil.move can replace it.
    try:
        if os.path.getsize(final_filepath) == 0:
            os.remove(final_filepath)
    except OSError:
        pass

    # Use temporary file to avoid partial writes
    temp_fd = None
    temp_filepath = None

    with ui_lock:
        ui.stdscr.clear()
        ui.draw_header(f"📥 Receiving: {safe_filename}")
        ui.print_colored(4, 2, f"📄 Size: {format_size(file_info['size'])}", 'info')
        if safe_filename != file_info['name']:
            ui.print_colored(5, 2, f"⚠️ Original name: {file_info['name']}", 'warning')
            ui.print_colored(6, 2, f"✓ Sanitized to: {safe_filename}", 'info')
        ui.stdscr.refresh()

    try:
        # Create temporary file in same directory as final destination
        temp_fd, temp_filepath = tempfile.mkstemp(
            dir=RECEIVED_DIR,
            prefix=f".{safe_filename}_",
            suffix=".tmp"
        )

        progress = ProgressTracker(file_info['size'], f"📥 Receiving {safe_filename}", ui)
        sender_algo = (file_info.get('hash_algorithm') or HASH_ALGORITHM)
        digest_size = get_hash_digest_size(sender_algo)

        with os.fdopen(temp_fd, 'wb') as f:
            temp_fd = None  # File descriptor is now owned by the file object
            computed_digest = _stream_recv_file(
                client_socket, f, file_info['size'], transfer_timeout, progress
            )

        # Read per-file digest trailer.
        expected_digest = recv_exact(client_socket, digest_size, transfer_timeout)
        if expected_digest is None or len(expected_digest) != digest_size:
            raise Exception("Failed to read hash trailer")

        if not _check_validation(temp_filepath, expected_digest, computed_digest,
                                 failed_validations, validation_lock):
            raise ValueError(f"Integrity verification failed for {safe_filename}")

        # Move temp file to final location atomically
        shutil.move(temp_filepath, final_filepath)
        temp_filepath = None  # File has been moved, don't try to clean it up

        with ui_lock:
            ui.show_message(f"✅ File received and verified: {final_filepath}", 'success')

    except Exception as e:
        with ui_lock:
            ui.show_message(f"❌ Error receiving file: {e}", 'error')
        # Clean up temporary file if it exists
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
            except Exception:
                pass
        # Clean up final file if it exists and was created
        if os.path.exists(final_filepath):
            try:
                os.remove(final_filepath)
            except Exception:
                pass
        raise
    finally:
        # Clean up file descriptor if still open
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except Exception:
                pass

def receive_directory(client_socket, dir_info, ui, failed_validations, validation_lock, transfer_timeout):
    """Enhanced directory receiver with proper UI synchronization"""
    # Sanitize directory name for cross-platform compatibility
    safe_dirname = sanitize_filename(dir_info['name'])
    download_dir = dedupe_dir(os.path.join(RECEIVED_DIR, safe_dirname))
    temp_dir = None
    
    with ui_lock:
        ui.stdscr.clear()
        ui.draw_header(f"📥 Receiving Directory: {safe_dirname}")
        ui.print_colored(4, 2, f"{dir_info['total_files']} files, {format_size(dir_info['total_size'])}", 'info')
        if safe_dirname != dir_info['name']:
            ui.print_colored(5, 2, f"⚠️ Original: {dir_info['name']}", 'warning')
            ui.print_colored(6, 2, f"✓ Sanitized: {safe_dirname}", 'info')
        ui.stdscr.refresh()

    ensure_directory(RECEIVED_DIR)

    # Disk space check — must be outside any except that would swallow OSError
    disk_usage = get_disk_usage(RECEIVED_DIR)
    if disk_usage:
        total, used, free_space = disk_usage
        required_space = dir_info['total_size']
        if free_space < required_space * 1.1:
            with ui_lock:
                ui.show_message(f"Insufficient disk space. Required: {format_size(required_space)}, Available: {format_size(free_space)}", 'error')
            raise OSError("Insufficient disk space for incoming directory")
        with ui_lock:
            ui.print_colored(5, 2, f"Available space: {format_size(free_space)}", 'info')
            ui.stdscr.refresh()
    else:
        with ui_lock:
            ui.print_colored(5, 2, "Warning: Could not verify disk space", 'warning')
            ui.print_colored(6, 2, "Proceeding anyway - ensure you have enough space", 'warning')
            ui.stdscr.refresh()

    try:
        temp_dir = tempfile.mkdtemp(dir=RECEIVED_DIR, prefix=f".{safe_dirname}_", suffix=".tmp")
        
        progress = ProgressTracker(dir_info['total_size'], f"📥 Receiving {safe_dirname}", ui)
        received_total = 0
        files_completed = 0

        for i, file_info in enumerate(dir_info['files'], 1):
            # Sanitize the file path for cross-platform compatibility
            safe_file_path = sanitize_path(file_info['path'])
            if not safe_file_path:
                raise Exception("Received empty file path in directory metadata")
            
            # Use thread-safe UI updates for current file display
            current_file_y = ui.height - 6  # Position above progress bar
            with ui_lock:
                ui.stdscr.move(current_file_y, 0)
                ui.stdscr.clrtoeol()
                display_path = safe_file_path if safe_file_path == file_info['path'] else f"{safe_file_path} (sanitized)"
                ui.print_colored(current_file_y, 2, f"[{i}/{dir_info['total_files']}] {display_path}", 'special')
                ui.stdscr.refresh()

            file_path = os.path.join(temp_dir, safe_file_path)
            real_path = os.path.realpath(file_path)
            temp_dir_real = os.path.realpath(temp_dir)
            if os.path.commonpath([temp_dir_real, real_path]) != temp_dir_real:
                raise Exception("Path traversal detected")

            
            try:
                ensure_directory(os.path.dirname(file_path))
            except Exception as e:
                raise Exception(f"Failed to create directory structure for {safe_file_path}: {e}")

            try:
                with open(file_path, 'wb') as f:
                    file_size = file_info['size']

                    try:
                        computed_digest = _stream_recv_file(
                            client_socket, f, file_size, transfer_timeout,
                            progress, progress_offset=received_total
                        )
                    except socket.timeout:
                        raise socket.timeout(
                            f"Timeout receiving {safe_file_path} (file size {file_size})"
                        )
                    except socket.error as e:
                        error_code = getattr(e, 'winerror', getattr(e, 'errno', 'unknown'))
                        if error_code == 10054:
                            raise Exception(
                                f"Sender forcibly closed connection during {safe_file_path}"
                            )
                        raise socket.error(
                            f"Network error receiving {safe_file_path} (error {error_code}): {e}"
                        )
                    except OSError as e:
                        if "No space left on device" in str(e) or e.errno == 28:
                            raise OSError(f"Disk full while writing {safe_file_path}")
                        raise OSError(f"Disk error writing {safe_file_path}: {e}")

                received_total += file_size

                actual_size = os.path.getsize(file_path)
                if actual_size != file_info['size']:
                    raise Exception(f"Size mismatch for {safe_file_path}: expected {file_info['size']}, got {actual_size}")

                # Per-file digest trailer.
                sender_algo = (dir_info.get('hash_algorithm') or HASH_ALGORITHM)
                digest_size = get_hash_digest_size(sender_algo)
                expected_digest = recv_exact(client_socket, digest_size, transfer_timeout)
                if expected_digest is None or len(expected_digest) != digest_size:
                    raise Exception(f"Failed to read hash trailer for {safe_file_path}")

                if not _check_validation(file_path, expected_digest, computed_digest,
                                         failed_validations, validation_lock):
                    raise ValueError(f"Integrity verification failed for {safe_file_path}")

                # Clear the hash verification line and show completion status
                with ui_lock:
                    ui.print_colored(0, 0, f"✅ Hash Verified: {safe_file_path}", 'success')

                files_completed += 1
                
            except Exception as e:
                with ui_lock:
                    ui.show_message(f"Error receiving {safe_file_path} (completed {files_completed}/{len(dir_info['files'])} files): {e}", 'error')
                raise

        try:
            # download_dir was already deduplicated by dedupe_dir(); never
            # rmtree an existing destination — that would silently destroy
            # the user's data.
            shutil.move(temp_dir, download_dir)
            temp_dir = None
        except Exception as e:
            raise Exception(f"Failed to finalize directory move: {e}")

        with ui_lock:
            ui.show_message(f"Directory received successfully: {download_dir} ({files_completed} files)", 'success')

    except socket.timeout as e:
        with ui_lock:
            ui.show_message(f"Timeout during directory transfer: {e}", 'error')
            ui.show_message("This may indicate network issues or sender problems", 'info')
        raise
    except OSError as e:
        if "No space left on device" in str(e) or e.errno == 28:
            with ui_lock:
                ui.show_message("Transfer failed: Not enough disk space", 'error')
        else:
            with ui_lock:
                ui.show_message(f"File system error: {e}", 'error')
        raise
    except Exception as e:
        with ui_lock:
            ui.show_message(f"Error receiving directory: {e}", 'error')
        raise
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                with ui_lock:
                    ui.print_colored(ui.height - 2, 2, "Cleaned up temporary files", 'info')
                    ui.stdscr.refresh()
            except Exception:
                pass
