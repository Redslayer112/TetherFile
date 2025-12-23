import socket
import json
import struct
import threading
import os
import time
import tempfile
import shutil
from transfers.lan.network import create_server_socket
from core.utils import calculate_file_hash, ensure_directory, format_size, get_disk_usage, sanitize_filename, sanitize_path
from core.progress import ProgressTracker

CONFIG = json.load(open('config.json'))
BUFFER_SIZE = CONFIG['BUFFER_SIZE']
SERVER_TIMEOUT = CONFIG['SERVER_TIMEOUT']
RECEIVED_DIR = CONFIG['RECEIVED_DIR']
TRANSFER_TYPES = CONFIG['TRANSFER_TYPES']
HASH_ALGORITHM = CONFIG['HASH_ALGORITHM']
SKIP_HASH_VERIFICATION = CONFIG['SKIP_HASH_VERIFICATION']

# UI lock to prevent concurrent screen updates
ui_lock = threading.Lock()

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
            except:
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
        ui.print_colored(8, 4, f"1. Change your HASH_ALGORITHM to '{sender_algo.lower()}' in config.py", 'info')
        ui.print_colored(9, 4, "2. Set SKIP_HASH_VERIFICATION = True in config.py", 'info')
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
            except:
                pass
            time.sleep(0.1)
    finally:
        ui.stdscr.nodelay(False)

def start_server(local_ip, port, ui, server_control):
    server_socket = None
    # Thread-safe list for failed validations
    failed_validations = []
    validation_lock = threading.Lock()
    
    try:
        server_socket = create_server_socket(local_ip, port)
        server_socket.listen(5)
        server_control['running'] = True
        server_control['socket'] = server_socket

        # Only show UI messages if server started successfully
        with ui_lock:
            ui.stdscr.clear()
            ui.draw_header("📥 Receive Mode Active")
            ui.print_colored(4, 2, f"🎯 Server listening on {local_ip or 'all interfaces'}:{port}", 'success')
            ui.print_colored(5, 2, f"💾 Files will be saved in '{RECEIVED_DIR}' directory", 'info')
            ui.print_colored(6, 2, "🔗 Other laptop should use this IP as target", 'info')
            ui.print_colored(8, 2, "💡 Ready to receive files... (Press 'q' to stop)", 'highlight')
            ui.stdscr.refresh()

        while server_control['running']:
            try:
                server_socket.settimeout(SERVER_TIMEOUT)
                client_socket, addr = server_socket.accept()
                
                with ui_lock:
                    ui.print_colored(10, 2, f"📥 Connection from {addr[0]}", 'success')
                    ui.stdscr.refresh()

                thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket, ui, failed_validations, validation_lock, addr),
                    daemon=True
                )
                thread.start()

            except socket.timeout:
                continue
            except socket.error as e:
                if server_control['running']:
                    # Only show error if server should be running
                    ui.show_message(f"⚠️ Server socket error: {e}", 'warning')
                break
            except Exception as e:
                if server_control['running']:
                    ui.show_message(f"❌ Unexpected server error: {e}", 'error')
                break

        # Show validation summary with non-blocking input
        if failed_validations:
            _show_validation_summary_non_blocking(ui, failed_validations)

    except OSError as e:
        if e.errno == 98 or "Address already in use" in str(e):
            ui.show_message(f"❌ Port {port} is already in use. Try a different port or close other applications using this port.", 'error')
        elif e.errno == 99 or "Cannot assign requested address" in str(e):
            ui.show_message(f"❌ Cannot bind to {local_ip}:{port}. Check if the IP address is correct and available.", 'error')
        else:
            ui.show_message(f"❌ Network error: {e}", 'error')
        server_control['running'] = False
    except Exception as e:
        ui.show_message(f"❌ Error starting server: {e}", 'error')
        server_control['running'] = False
    finally:
        # Only close if we created the socket and it's not already closed
        if server_socket and server_control.get('socket') == server_socket:
            try: 
                server_socket.close()
            except: 
                pass
            # Clear the reference to avoid double-close in stop_server
            server_control['socket'] = None

def stop_server(server_control):
    server_control['running'] = False
    socket_to_close = server_control.get('socket')
    if socket_to_close:
        try: 
            socket_to_close.close()
        except: 
            pass
        server_control['socket'] = None


def handle_client(client_socket, ui, failed_validations, validation_lock, addr):
    """Enhanced client handler with better error reporting and UI synchronization"""
    start_time = time.time()
    try:
        # Set initial timeout for metadata
        client_socket.settimeout(30)
        
        with ui_lock:
            ui.print_colored(10, 2, f"Connected from {addr[0]} at {time.strftime('%H:%M:%S')}", 'success')
            ui.stdscr.refresh()
        
        metadata_size_data = recv_exact(client_socket, 4)
        if not metadata_size_data:
            raise Exception("Failed to receive metadata size")

        metadata_size = struct.unpack('!I', metadata_size_data)[0]
        if metadata_size > 10 * 1024 * 1024:  # 10MB limit
            raise Exception(f"Metadata too large: {metadata_size} bytes")

        metadata_data = recv_exact(client_socket, metadata_size)
        if not metadata_data:
            raise Exception("Failed to receive metadata")

        try:
            metadata = json.loads(metadata_data.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid metadata JSON: {e}")

        # Log transfer details with UI lock
        transfer_type = metadata.get('type', 'unknown')
        with ui_lock:
            if transfer_type == TRANSFER_TYPES['FILE']:
                ui.print_colored(11, 2, f"Receiving file: {metadata.get('name', 'unknown')} ({format_size(metadata.get('size', 0))})", 'info')
            elif transfer_type == TRANSFER_TYPES['DIRECTORY']:
                ui.print_colored(11, 2, f"Receiving directory: {metadata.get('name', 'unknown')} ({metadata.get('total_files', 0)} files, {format_size(metadata.get('total_size', 0))})", 'info')
            ui.stdscr.refresh()

        # Hash algorithm check with better error handling
        sender_algo = metadata.get('hash_algorithm', None)
        if sender_algo and sender_algo.lower() != HASH_ALGORITHM.lower():
            if SKIP_HASH_VERIFICATION:
                ui.show_message(
                    f"Hash algorithm mismatch (sender={sender_algo}, receiver={HASH_ALGORITHM}). Skipping verification.",
                    'warning'
                )
                try: 
                    client_socket.send(b'ACK1')
                except Exception as e:
                    raise Exception(f"Failed to send ACK1 after hash mismatch warning: {e}")
            else:
                try: 
                    client_socket.send(b'MISMATCH')
                except: 
                    pass
                _handle_hash_mismatch_non_blocking(ui, sender_algo)
                return
        else:
            # Send acknowledgment for metadata
            try: 
                client_socket.send(b'ACK1')
            except Exception as e:
                raise Exception(f"Failed to send metadata acknowledgment: {e}")

        # Process the transfer with detailed error reporting
        try:
            if metadata['type'] == TRANSFER_TYPES['FILE']:
                receive_file(client_socket, metadata, ui, failed_validations, validation_lock)
            elif metadata['type'] == TRANSFER_TYPES['DIRECTORY']:
                receive_directory(client_socket, metadata, ui, failed_validations, validation_lock)
            else:
                raise Exception(f"Unknown transfer type: {metadata['type']}")
                
            duration = time.time() - start_time
            with ui_lock:
                ui.print_colored(12, 2, f"Transfer completed in {duration:.1f}s from {addr[0]}", 'success')
                ui.stdscr.refresh()
            
        except Exception as e:
            duration = time.time() - start_time
            ui.show_message(f"Transfer failed after {duration:.1f}s: {e}", 'error')
            raise

    except socket.timeout as e:
        ui.show_message(f"Timeout from client {addr[0]}: {e}", 'error')
    except socket.error as e:
        error_code = getattr(e, 'winerror', getattr(e, 'errno', 'unknown'))
        if error_code == 10054:
            ui.show_message(f"Client {addr[0]} forcibly closed connection", 'warning')
        else:
            ui.show_message(f"Network error from {addr[0]} (code {error_code}): {e}", 'error')
    except Exception as e:
        ui.show_message(f"Error handling client {addr[0]}: {e}", 'error')
    finally:
        try: 
            client_socket.close()
        except: 
            pass


def recv_exact(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def _verify_file_hash(filepath, expected_hash, failed_validations, validation_lock, ui):
    """Verify file hash and handle validation failure thread-safely"""
    if SKIP_HASH_VERIFICATION:
        return True

    with ui_lock:
        hash_verify_line = ui.height - 3
        ui.stdscr.move(hash_verify_line, 0)
        ui.stdscr.clrtoeol()
        ui.print_colored(
            hash_verify_line,
            2,
            "🔐 Verifying file integrity...",
            'warning'
        )
        ui.stdscr.refresh()

    # 🔁 Retry hash calculation (Windows AV / filesystem safety)
    received_hash = None
    last_error = None

    for attempt in range(3):
        try:
            received_hash = calculate_file_hash(filepath)
            break
        except PermissionError as e:
            last_error = e
            time.sleep(0.2)  # allow file lock to release
        except OSError as e:
            last_error = e
            time.sleep(0.2)

    if received_hash is None:
        raise Exception(f"Failed to read file for hash verification: {last_error}")

    if received_hash == expected_hash:
        return True
    else:
        with validation_lock:
            failed_validations.append({
                'file': filepath,
                'expected': expected_hash[:16] + '...',
                'received': received_hash[:16] + '...'
            })
        return False

def dedupe_path(path):
    base, ext = os.path.splitext(path)
    i = 1
    candidate = path
    while os.path.exists(candidate):
        candidate = f"{base} ({i}){ext}"
        i += 1
    return candidate


def receive_file(client_socket, file_info, ui, failed_validations, validation_lock):
    ensure_directory(RECEIVED_DIR)
    
    # Sanitize filename for cross-platform compatibility
    safe_filename = sanitize_filename(file_info['name'])
    final_filepath = dedupe_path(
        os.path.join(RECEIVED_DIR, safe_filename)
    )

    
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

        with os.fdopen(temp_fd, 'wb') as f:
            temp_fd = None  # File descriptor is now owned by the file object
            received = 0
            while received < file_info['size']:
                chunk = client_socket.recv(min(BUFFER_SIZE, file_info['size'] - received))
                if not chunk:
                    raise Exception("Connection lost during file transfer")
                f.write(chunk)
                received += len(chunk)
                progress.update(received)

        # Verify hash if enabled
        hash_valid = _verify_file_hash(temp_filepath, file_info['hash'], failed_validations, validation_lock, ui)
        
        # Move temp file to final location atomically
        shutil.move(temp_filepath, final_filepath)
        temp_filepath = None  # File has been moved, don't try to clean it up
        
        if hash_valid:
            ui.show_message(f"✅ File received and verified: {final_filepath}", 'success')
        else:
            ui.show_message(f"⚠️ File received but integrity check failed: {final_filepath}", 'error')

        client_socket.send(b'DONE')

    except Exception as e:
        ui.show_message(f"❌ Error receiving file: {e}", 'error')
        # Clean up temporary file if it exists
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
            except:
                pass
        # Clean up final file if it exists and was created
        if os.path.exists(final_filepath):
            try:
                os.remove(final_filepath)
            except:
                pass
    finally:
        # Clean up file descriptor if still open
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except:
                pass

def receive_directory(client_socket, dir_info, ui, failed_validations, validation_lock):
    """Enhanced directory receiver with proper UI synchronization"""
    # Sanitize directory name for cross-platform compatibility
    safe_dirname = sanitize_filename(dir_info['name'])
    download_dir = os.path.join(RECEIVED_DIR, safe_dirname)
    temp_dir = None
    
    with ui_lock:
        ui.stdscr.clear()
        ui.draw_header(f"📥 Receiving Directory: {safe_dirname}")
        ui.print_colored(4, 2, f"{dir_info['total_files']} files, {format_size(dir_info['total_size'])}", 'info')
        if safe_dirname != dir_info['name']:
            ui.print_colored(5, 2, f"⚠️ Original: {dir_info['name']}", 'warning')
            ui.print_colored(6, 2, f"✓ Sanitized: {safe_dirname}", 'info')
        ui.stdscr.refresh()

    try:
        ensure_directory(RECEIVED_DIR)
        
        # Use the utility function for disk usage
        disk_usage = get_disk_usage(RECEIVED_DIR)
        if disk_usage:
            total, used, free_space = disk_usage
            required_space = dir_info['total_size']
            
            if free_space < required_space * 1.1:
                ui.show_message(f"Insufficient disk space. Required: {format_size(required_space)}, Available: {format_size(free_space)}", 'error')
                try:
                    client_socket.send(b'SPACE_ERROR')
                except:
                    pass
                return
                
            with ui_lock:
                ui.print_colored(5, 2, f"Available space: {format_size(free_space)}", 'info')
                ui.stdscr.refresh()
        else:
            with ui_lock:
                ui.print_colored(5, 2, "Warning: Could not verify disk space", 'warning')
                ui.print_colored(6, 2, "Proceeding anyway - ensure you have enough space", 'warning')
                ui.stdscr.refresh()
        
    except Exception as e:
        with ui_lock:
            ui.print_colored(5, 2, f"Warning: Could not verify disk space: {e}", 'warning')
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
            
            # Use thread-safe UI updates for current file display
            current_file_y = ui.height - 6  # Position above progress bar
            with ui_lock:
                ui.stdscr.move(current_file_y, 0)
                ui.stdscr.clrtoeol()
                display_path = safe_file_path if safe_file_path == file_info['path'] else f"{safe_file_path} (sanitized)"
                ui.print_colored(current_file_y, 2, f"[{i}/{dir_info['total_files']}] {display_path}", 'special')
                ui.stdscr.refresh()

            file_path = os.path.join(temp_dir, safe_file_path)
            
            try:
                ensure_directory(os.path.dirname(file_path))
            except Exception as e:
                raise Exception(f"Failed to create directory structure for {safe_file_path}: {e}")

            try:
                with open(file_path, 'wb') as f:
                    file_received = 0
                    file_size = file_info['size']
                    chunk_count = 0
                    last_progress_time = time.time()

                    while file_received < file_size:
                        remaining = file_size - file_received
                        chunk_size = min(BUFFER_SIZE, remaining)
                        
                        try:
                            client_socket.settimeout(30)
                            data = client_socket.recv(chunk_size)
                            
                            if not data:
                                raise Exception(f"Connection lost during {safe_file_path} transfer at {file_received}/{file_size} bytes")
                                
                            f.write(data)
                            file_received += len(data)
                            received_total += len(data)
                            chunk_count += 1
                            
                            current_time = time.time()
                            if current_time - last_progress_time > 0.1:
                                progress.update(received_total)
                                last_progress_time = current_time
                            
                        except socket.timeout:
                            raise socket.timeout(f"Timeout receiving {safe_file_path} at {file_received}/{file_size} bytes (chunk {chunk_count})")
                        except socket.error as e:
                            error_code = getattr(e, 'winerror', getattr(e, 'errno', 'unknown'))
                            if error_code == 10054:
                                raise Exception(f"Sender forcibly closed connection during {safe_file_path} at {file_received}/{file_size} bytes")
                            else:
                                raise socket.error(f"Network error receiving {safe_file_path} (error {error_code}): {e}")
                        except OSError as e:
                            if "No space left on device" in str(e) or e.errno == 28:
                                raise OSError(f"Disk full while writing {safe_file_path}")
                            else:
                                raise OSError(f"Disk error writing {safe_file_path}: {e}")

                progress.update(received_total)

                actual_size = os.path.getsize(file_path)
                if actual_size != file_info['size']:
                    raise Exception(f"Size mismatch for {safe_file_path}: expected {file_info['size']}, got {actual_size}")

                hash_valid = True
                if 'hash' in file_info and not SKIP_HASH_VERIFICATION:
                    hash_valid = _verify_file_hash(file_path, file_info['hash'], failed_validations, validation_lock, ui)
                    
                # Clear the hash verification line and show completion status
                with ui_lock:
                    hash_verify_line = ui.height - 3
                    ui.stdscr.move(hash_verify_line, 0)
                    ui.stdscr.clrtoeol()
                    
                    if hash_valid:
                        ui.print_colored(hash_verify_line, 2, f"✅ Hash Verified: {safe_file_path}", 'success')
                    else:
                        ui.print_colored(hash_verify_line, 2, f"⚠️ Failed hash check: {safe_file_path}", 'error')
                    ui.stdscr.refresh()

                try:
                    client_socket.settimeout(10)
                    client_socket.send(b'ACK2')
                    files_completed += 1
                except Exception as e:
                    raise Exception(f"Failed to send acknowledgment for {safe_file_path}: {e}")
                
            except Exception as e:
                ui.show_message(f"Error receiving {safe_file_path} (completed {files_completed}/{len(dir_info['files'])} files): {e}", 'error')
                raise

        try:
            if os.path.exists(download_dir):
                shutil.rmtree(download_dir)
            shutil.move(temp_dir, download_dir)
            temp_dir = None
        except Exception as e:
            raise Exception(f"Failed to finalize directory move: {e}")

        try:
            client_socket.settimeout(10)
            client_socket.send(b'DONE')
        except Exception as e:
            ui.show_message(f"Directory received successfully but failed to send final acknowledgment: {e}", 'warning')
            return

        ui.show_message(f"Directory received successfully: {download_dir} ({files_completed} files)", 'success')

    except socket.timeout as e:
        ui.show_message(f"Timeout during directory transfer: {e}", 'error')
        ui.show_message("This may indicate network issues or sender problems", 'info')
    except OSError as e:
        if "No space left on device" in str(e) or e.errno == 28:
            ui.show_message("Transfer failed: Not enough disk space", 'error')
        else:
            ui.show_message(f"File system error: {e}", 'error')
    except Exception as e:
        ui.show_message(f"Error receiving directory: {e}", 'error')
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                with ui_lock:
                    ui.print_colored(ui.height - 2, 2, "Cleaned up temporary files", 'info')
                    ui.stdscr.refresh()
            except:
                pass

def show_validation_summary(ui, failed_validations):
    """Show summary of failed validations - kept for backward compatibility"""
    _show_validation_summary_non_blocking(ui, failed_validations)