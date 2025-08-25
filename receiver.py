import socket
import json
import struct
import threading
import os
from network import create_server_socket
from utils import calculate_file_hash, ensure_directory, format_size
from progress import ProgressTracker
from config import BUFFER_SIZE, SERVER_TIMEOUT, RECEIVED_DIR, TRANSFER_TYPES


def start_server(local_ip, port, ui, server_control):
    """Start receiving server"""
    server_socket = None
    try:
        server_socket = create_server_socket(local_ip, port)
        server_socket.listen(5)
        server_control['running'] = True
        server_control['socket'] = server_socket

        ui.stdscr.clear()
        ui.draw_header("📥 Receive Mode Active")
        ui.print_colored(4, 2, f"🎯 Server listening on {local_ip or 'all interfaces'}:{port}", 'success')
        ui.print_colored(5, 2, f"💾 Files will be saved in '{RECEIVED_DIR}' directory", 'info')
        ui.print_colored(6, 2, "🔗 Other laptop should use this IP as target", 'info')
        ui.print_colored(8, 2, "💡 Ready to receive files... (Press 'q' to stop)", 'highlight')
        ui.stdscr.refresh()

        failed_validations = []

        while server_control['running']:
            try:
                server_socket.settimeout(SERVER_TIMEOUT)
                client_socket, addr = server_socket.accept()
                ui.print_colored(10, 2, f"📥 Connection from {addr[0]}", 'success')
                ui.stdscr.refresh()

                # Handle each client in a separate thread
                thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket, ui, failed_validations),
                    daemon=True
                )
                thread.start()

            except socket.timeout:
                continue
            except socket.error:
                if server_control['running']:
                    ui.show_message("❌ Server error occurred", 'error')
                break

        # Show validation summary if there were failures
        if failed_validations:
            show_validation_summary(ui, failed_validations)

    except Exception as e:
        ui.show_message(f"❌ Error starting server: {e}", 'error')
    finally:
        if server_socket:
            try:
                server_socket.close()
            except:
                pass


def stop_server(server_control):
    """Stop the server"""
    server_control['running'] = False
    if server_control.get('socket'):
        try:
            server_control['socket'].close()
        except:
            pass


def handle_client(client_socket, ui, failed_validations):
    """Handle incoming file transfer"""
    try:
        client_socket.settimeout(60)  # Set timeout for client operations
        
        # Receive metadata
        metadata_size_data = recv_exact(client_socket, 4)
        if not metadata_size_data:
            raise Exception("Failed to receive metadata size")
            
        metadata_size = struct.unpack('!I', metadata_size_data)[0]
        
        if metadata_size > 10 * 1024 * 1024:  # 10MB max for metadata
            raise Exception("Metadata too large")
            
        metadata_data = recv_exact(client_socket, metadata_size)
        if not metadata_data:
            raise Exception("Failed to receive metadata")
            
        metadata = json.loads(metadata_data.decode('utf-8'))

        if metadata['type'] == TRANSFER_TYPES['FILE']:
            receive_file(client_socket, metadata, ui, failed_validations)
        elif metadata['type'] == TRANSFER_TYPES['DIRECTORY']:
            receive_directory(client_socket, metadata, ui, failed_validations)
        else:
            raise Exception(f"Unknown transfer type: {metadata['type']}")

    except Exception as e:
        ui.show_message(f"❌ Error handling client: {e}", 'error')
    finally:
        try:
            client_socket.close()
        except:
            pass


def recv_exact(sock, size):
    """Receive exactly 'size' bytes from socket"""
    data = b''
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def receive_file(client_socket, file_info, ui, failed_validations):
    """Receive a single file with progress tracking"""
    ensure_directory(RECEIVED_DIR)
    filepath = os.path.join(RECEIVED_DIR, file_info['name'])

    ui.stdscr.clear()
    ui.draw_header(f"📥 Receiving: {file_info['name']}")
    ui.print_colored(4, 2, f"📄 Size: {format_size(file_info['size'])}", 'info')
    ui.stdscr.refresh()

    try:
        # Send acknowledgment that metadata was received
        client_socket.send(b'ACK1')

        progress = ProgressTracker(file_info['size'], f"📥 Receiving {file_info['name']}", ui)

        with open(filepath, 'wb') as f:
            received = 0
            total_size = file_info['size']

            while received < total_size:
                remaining = total_size - received
                chunk_size = min(BUFFER_SIZE, remaining)
                
                try:
                    data = client_socket.recv(chunk_size)
                    if not data:
                        raise Exception("Connection lost during file transfer")
                        
                    f.write(data)
                    received += len(data)
                    progress.update(received)
                    
                except socket.error as e:
                    raise Exception(f"Network error during transfer: {e}")

        # Verify integrity
        ui.print_colored(ui.height - 6, 2, "🔍 Verifying file integrity...", 'warning')
        ui.stdscr.refresh()
        
        received_hash = calculate_file_hash(filepath)
        
        if received_hash == file_info['hash']:
            ui.show_message(f"✅ File received and verified: {filepath}", 'success')
        else:
            failed_validations.append({
                'file': filepath,
                'expected': file_info['hash'][:16] + '...',
                'received': received_hash[:16] + '...'
            })
            ui.show_message(f"⚠️ File received but integrity check failed: {filepath}", 'error')

        # Send completion acknowledgment
        client_socket.send(b'DONE')

    except Exception as e:
        ui.show_message(f"❌ Error receiving file: {e}", 'error')
        # Try to clean up partial file
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except:
            pass


def receive_directory(client_socket, dir_info, ui, failed_validations):
    """Receive directory with progress tracking"""
    download_dir = os.path.join(RECEIVED_DIR, dir_info['name'])
    ensure_directory(download_dir)

    ui.stdscr.clear()
    ui.draw_header(f"📁 Receiving Directory: {dir_info['name']}")
    ui.print_colored(4, 2, f"📊 {dir_info['total_files']} files, {format_size(dir_info['total_size'])}", 'info')
    ui.stdscr.refresh()

    try:
        # Send acknowledgment that metadata was received
        client_socket.send(b'ACK1')

        progress = ProgressTracker(dir_info['total_size'], f"📁 Receiving {dir_info['name']}", ui)
        received_total = 0

        for i, file_info in enumerate(dir_info['files'], 1):
            # Update current file info
            current_file_y = ui.height - 5
            ui.stdscr.move(current_file_y, 0)
            ui.stdscr.clrtoeol()
            ui.print_colored(current_file_y, 2, f"📄 [{i}/{dir_info['total_files']}] {file_info['path']}", 'special')
            ui.stdscr.refresh()

            file_path = os.path.join(download_dir, file_info['path'])
            ensure_directory(os.path.dirname(file_path))

            try:
                with open(file_path, 'wb') as f:
                    file_received = 0
                    file_size = file_info['size']

                    while file_received < file_size:
                        remaining = file_size - file_received
                        chunk_size = min(BUFFER_SIZE, remaining)
                        
                        try:
                            data = client_socket.recv(chunk_size)
                            if not data:
                                raise Exception(f"Connection lost during {file_info['path']} transfer")
                                
                            f.write(data)
                            file_received += len(data)
                            received_total += len(data)
                            progress.update(received_total)
                            
                        except socket.error as e:
                            raise Exception(f"Network error during {file_info['path']}: {e}")

                # Send acknowledgment for each file
                client_socket.send(b'ACK2')
                
            except Exception as e:
                ui.show_message(f"❌ Error receiving {file_info['path']}: {e}", 'error')
                # Try to clean up partial file
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
                raise

        # Send final completion acknowledgment
        client_socket.send(b'DONE')
        ui.show_message(f"✅ Directory received: {download_dir}", 'success')

    except Exception as e:
        ui.show_message(f"❌ Error receiving directory: {e}", 'error')


def show_validation_summary(ui, failed_validations):
    """Show summary of failed validations"""
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

    ui.print_colored(ui.height - 3, 2, "Press any key to continue...", 'highlight')
    ui.stdscr.refresh()
    ui.stdscr.getch()