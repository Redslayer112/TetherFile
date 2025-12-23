import json
import struct
import time
import os
import socket
from transfers.lan.network import create_socket
from core.utils import calculate_file_hash, collect_directory_files, format_size
from core.progress import ProgressTracker

CONFIG = json.load(open('config.json'))
BUFFER_SIZE = CONFIG['BUFFER_SIZE']
TRANSFER_TYPES = CONFIG['TRANSFER_TYPES']
HASH_ALGORITHM = CONFIG['HASH_ALGORITHM']

def _handle_hash_mismatch(ui, sock):
    """Handle hash algorithm mismatch display and user input"""
    ui.stdscr.clear()
    ui.draw_header("⚠️ Hash Algorithm Mismatch")
    ui.print_colored(4, 2, f"📤 You are using: {HASH_ALGORITHM.upper()}", 'error')
    ui.print_colored(5, 2, "📥 Receiver is using a different algorithm", 'error')

    ui.print_colored(7, 2, "💡 Solutions:", 'highlight')
    ui.print_colored(8, 4, "1. Match HASH_ALGORITHM in config.py with receiver", 'info')
    ui.print_colored(9, 4, "2. Set SKIP_HASH_VERIFICATION = True in config.py (receiver side)", 'info')
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
            except:
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
        # Read the longest expected response length
        max_length = max(len(resp) for resp in expected_responses)
        response = sock.recv(max_length)
        
        # Check if response matches any expected responses
        for expected in expected_responses:
            if response.startswith(expected):
                return True, expected
        
        return False, response
    except socket.timeout:
        return False, b'TIMEOUT'
    except Exception as e:
        return False, str(e).encode()


def send_file(filepath, target_ip, port, local_ip, ui):
    if not os.path.exists(filepath):
        ui.show_message(f"❌ File not found: {filepath}", 'error')
        return False

    filename = os.path.basename(filepath)
    file_size = os.path.getsize(filepath)

    ui.stdscr.clear()
    ui.draw_header(f"📤 Sending File: {filename}")
    ui.print_colored(4, 2, f"📄 Size: {format_size(file_size)}", 'info')
    ui.print_colored(5, 2, f"🎯 Target: {target_ip}", 'info')

    sock = None
    try:
        sock = create_socket(local_ip)
        sock.settimeout(30)
        ui.print_colored(7, 2, f"🔗 Connecting to {target_ip}...", 'warning')
        ui.stdscr.refresh()
        sock.connect((target_ip, port))

        ui.print_colored(8, 2, f"✅ Connected to receiver at {target_ip}:{port}", 'success')
        ui.stdscr.refresh()

        ui.print_colored(9, 2, "🔐 Calculating file hash...", 'warning')
        ui.stdscr.refresh()
        file_hash = calculate_file_hash(filepath)

        file_info = {
            'type': TRANSFER_TYPES['FILE'],
            'name': filename,
            'size': file_size,
            'hash': file_hash,
            'hash_algorithm': HASH_ALGORITHM,
            'timestamp': time.time()
        }

        metadata = json.dumps(file_info).encode('utf-8')
        sock.send(struct.pack('!I', len(metadata)))
        sock.send(metadata)

        # Handle acknowledgment with proper error checking
        success, response = _receive_acknowledgment(sock, [b'ACK1', b'MISMATCH'])
        if not success:
            if response == b'TIMEOUT':
                raise socket.timeout("Timeout waiting for metadata acknowledgment")
            else:
                raise Exception(f"Failed to receive metadata acknowledgment: {response}")

        if response == b'MISMATCH':
            _handle_hash_mismatch(ui, sock)
            return False

        # Continue with file transfer
        progress = ProgressTracker(file_size, f"📤 Sending {filename}", ui)
        with open(filepath, 'rb') as f:
            sent = 0
            while sent < file_size:
                chunk = f.read(min(BUFFER_SIZE, file_size - sent))
                if not chunk: 
                    break
                
                try:
                    sock.sendall(chunk)
                    sent += len(chunk)
                    progress.update(sent)
                except socket.timeout:
                    raise socket.timeout("Timeout during file transfer")
                except socket.error as e:
                    raise socket.error(f"Network error during transfer: {e}")

        # Receive final acknowledgment
        success, response = _receive_acknowledgment(sock, [b'DONE'])
        if not success:
            if response == b'TIMEOUT':
                raise socket.timeout("Timeout waiting for completion acknowledgment")
            else:
                raise Exception(f"Failed to receive completion acknowledgment: {response}")

        ui.show_message("✅ File sent successfully!", 'success')
        return True

    except socket.timeout as e:
        ui.show_message(f"⏰ Connection timeout: {e}", 'error')
        return False
    except ConnectionRefusedError:
        ui.show_message(f"🚫 Connection refused: Receiver might not be running on {target_ip}:{port}", 'error')
        return False
    except socket.error as e:
        ui.show_message(f"🌐 Network error: {e}", 'error')
        return False
    except Exception as e:
        ui.show_message(f"❌ Error sending file: {e}", 'error')
        return False
    finally:
        if sock:
            try: 
                sock.close()
            except: 
                pass


def send_directory(dir_path, target_ip, port, local_ip, ui):
    """Send entire directory with enhanced error handling and debugging"""
    if not os.path.isdir(dir_path):
        ui.show_message(f"Directory not found: {dir_path}", 'error')
        return False

    dirname = os.path.basename(dir_path)
    ui.stdscr.clear()
    ui.draw_header(f"Sending Directory: {dirname}")

    sock = None
    try:
        sock = create_socket(local_ip)
        # Increase socket timeouts for large transfers
        sock.settimeout(120)  # Increased from 60 to 120 seconds
        
        # Enable socket keep-alive to detect connection issues earlier
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        ui.print_colored(4, 2, f"Connecting to {target_ip}...", 'warning')
        ui.stdscr.refresh()
        sock.connect((target_ip, port))

        ui.print_colored(5, 2, "Scanning directory...", 'warning')
        ui.stdscr.refresh()
        files_info, total_size = collect_directory_files(dir_path)

        if not files_info:
            ui.show_message("No files found in directory", 'error')
            return False

        ui.print_colored(6, 2, f"{len(files_info)} files, total size: {format_size(total_size)}", 'info')
        ui.stdscr.refresh()

        dir_info = {
            'type': TRANSFER_TYPES['DIRECTORY'],
            'name': dirname,
            'files': files_info,
            'total_files': len(files_info),
            'total_size': total_size,
            'hash_algorithm': HASH_ALGORITHM,
            'timestamp': time.time()
        }

        metadata = json.dumps(dir_info).encode('utf-8')
        sock.send(struct.pack('!I', len(metadata)))
        sock.send(metadata)

        # Handle acknowledgment with hash mismatch support
        success, response = _receive_acknowledgment(sock, [b'ACK1', b'MISMATCH'])
        if not success:
            if response == b'TIMEOUT':
                raise socket.timeout("Timeout waiting for metadata acknowledgment")
            else:
                raise Exception(f"Failed to receive metadata acknowledgment: {response}")

        if response == b'MISMATCH':
            _handle_hash_mismatch(ui, sock)
            return False

        progress = ProgressTracker(total_size, f"Sending {dirname}", ui)
        sent_total = 0
        last_successful_file = None

        for i, file_info in enumerate(files_info, 1):
            current_file_y = ui.height - 5
            ui.stdscr.move(current_file_y, 0)
            ui.stdscr.clrtoeol()
            ui.print_colored(current_file_y, 2, f"[{i}/{len(files_info)}] {file_info['path']}", 'special')
            ui.stdscr.refresh()

            try:
                # Add connection health check before each file
                try:
                    sock.send(b'\x00')  # Send empty data to check connection
                except socket.error as e:
                    raise socket.error(f"Connection lost before sending {file_info['path']}: {e}")

                with open(file_info['full_path'], 'rb') as f:
                    file_sent = 0
                    chunk_count = 0
                    while file_sent < file_info['size']:
                        chunk = f.read(min(BUFFER_SIZE, file_info['size'] - file_sent))
                        if not chunk:
                            break
                        
                        try:
                            sock.sendall(chunk)
                            file_sent += len(chunk)
                            sent_total += len(chunk)
                            progress.update(sent_total)
                            chunk_count += 1
                            
                            # Add periodic connection health check for large files
                            if chunk_count % 100 == 0:  # Every 100 chunks
                                try:
                                    sock.send(b'')  # Ping connection
                                except socket.error as e:
                                    raise socket.error(f"Connection lost during {file_info['path']} (chunk {chunk_count}): {e}")
                                    
                        except socket.timeout:
                            raise socket.timeout(f"Timeout during transfer of {file_info['path']} at {file_sent}/{file_info['size']} bytes")
                        except socket.error as e:
                            error_code = getattr(e, 'winerror', getattr(e, 'errno', 'unknown'))
                            raise socket.error(f"Network error during transfer of {file_info['path']} (error {error_code}): {e}")
            
            except IOError as e:
                raise IOError(f"Error reading file {file_info['path']}: {e}")

            # Receive file acknowledgment with enhanced error reporting
            try:
                success, response = _receive_acknowledgment(sock, [b'ACK2'], timeout=60)
                if not success:
                    if response == b'TIMEOUT':
                        raise socket.timeout(f"Timeout waiting for acknowledgment of {file_info['path']} (file {i}/{len(files_info)})")
                    else:
                        # Decode the response for better error reporting
                        try:
                            response_str = response.decode('utf-8', errors='replace')
                        except:
                            response_str = str(response)
                        raise Exception(f"Failed to receive acknowledgment for {file_info['path']}: {response_str}")
                        
                last_successful_file = file_info['path']
                
            except Exception as e:
                # Add context about which file failed and how many were successful
                files_completed = i - 1
                raise Exception(f"Acknowledgment failed for {file_info['path']} (completed {files_completed}/{len(files_info)} files). Last successful: {last_successful_file}. Error: {e}")

        # Receive final acknowledgment
        success, response = _receive_acknowledgment(sock, [b'DONE'], timeout=30)
        if not success:
            if response == b'TIMEOUT':
                raise socket.timeout("Timeout waiting for final completion acknowledgment")
            else:
                raise Exception(f"Failed to receive final completion acknowledgment: {response}")

        ui.show_message("Directory sent successfully!", 'success')
        return True

    except socket.timeout as e:
        ui.show_message(f"Connection timeout: {e}", 'error')
        ui.show_message("Try: 1) Check receiver is still running 2) Increase timeouts in config", 'info')
        return False
    except ConnectionRefusedError:
        ui.show_message(f"Connection refused: Receiver might not be running on {target_ip}:{port}", 'error')
        return False
    except socket.error as e:
        error_code = getattr(e, 'winerror', getattr(e, 'errno', 'unknown'))
        if error_code == 10054:
            ui.show_message(f"Connection forcibly closed by receiver. Check receiver logs and available disk space.", 'error')
            ui.show_message("This often happens when receiver runs out of space or crashes.", 'info')
        else:
            ui.show_message(f"Network error (code {error_code}): {e}", 'error')
        return False
    except IOError as e:
        ui.show_message(f"File access error: {e}", 'error')
        return False
    except Exception as e:
        ui.show_message(f"Error sending directory: {e}", 'error')
        return False
    finally:
        if sock:
            try: 
                sock.close()
            except: 
                pass