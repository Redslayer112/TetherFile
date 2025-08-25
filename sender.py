import json
import struct
import time
import os
import socket
from network import create_socket
from utils import calculate_file_hash, collect_directory_files, format_size
from progress import ProgressTracker
from config import BUFFER_SIZE, TRANSFER_TYPES


def send_file(filepath, target_ip, port, local_ip, ui):
    """Send a single file with progress tracking"""
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
        # Create socket with timeout
        sock = create_socket(local_ip)
        sock.settimeout(30)  # 30 second timeout
        
        ui.print_colored(7, 2, f"🔗 Connecting to {target_ip}...", 'warning')
        ui.stdscr.refresh()
        sock.connect((target_ip, port))

        # Calculate hash
        ui.print_colored(8, 2, "🔍 Calculating file hash...", 'warning')
        ui.stdscr.refresh()
        file_hash = calculate_file_hash(filepath)

        # Prepare metadata
        file_info = {
            'type': TRANSFER_TYPES['FILE'],
            'name': filename,
            'size': file_size,
            'hash': file_hash,
            'timestamp': time.time()
        }

        # Send metadata
        metadata = json.dumps(file_info).encode('utf-8')
        sock.send(struct.pack('!I', len(metadata)))
        sock.send(metadata)

        # Wait for acknowledgment
        ack = sock.recv(4)
        if ack != b'ACK1':
            raise Exception("Failed to receive metadata acknowledgment")

        # Send file with progress
        progress = ProgressTracker(file_size, f"📤 Sending {filename}", ui)
        
        with open(filepath, 'rb') as f:
            sent = 0
            while sent < file_size:
                remaining = file_size - sent
                chunk_size = min(BUFFER_SIZE, remaining)
                chunk = f.read(chunk_size)
                
                if not chunk:
                    break
                
                # Send chunk with error handling
                try:
                    sock.sendall(chunk)
                    sent += len(chunk)
                    progress.update(sent)
                except socket.error as e:
                    raise Exception(f"Connection lost during transfer: {e}")

        # Wait for completion acknowledgment
        final_ack = sock.recv(4)
        if final_ack != b'DONE':
            raise Exception("Failed to receive completion acknowledgment")

        ui.show_message("✅ File sent successfully!", 'success')
        return True

    except socket.timeout:
        ui.show_message("❌ Connection timeout - check if receiver is running", 'error')
        return False
    except ConnectionRefusedError:
        ui.show_message("❌ Connection refused - check IP and ensure receiver is running", 'error')
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
    """Send entire directory with progress tracking"""
    if not os.path.isdir(dir_path):
        ui.show_message(f"❌ Directory not found: {dir_path}", 'error')
        return False

    dirname = os.path.basename(dir_path)
    ui.stdscr.clear()
    ui.draw_header(f"📁 Sending Directory: {dirname}")

    sock = None
    try:
        sock = create_socket(local_ip)
        sock.settimeout(60)  # Longer timeout for directory operations
        
        ui.print_colored(4, 2, f"🔗 Connecting to {target_ip}...", 'warning')
        ui.stdscr.refresh()
        sock.connect((target_ip, port))

        # Collect files
        ui.print_colored(5, 2, "📋 Scanning directory...", 'warning')
        ui.stdscr.refresh()
        
        files_info, total_size = collect_directory_files(dir_path)
        
        if not files_info:
            ui.show_message("❌ No files found in directory", 'error')
            return False
        
        ui.print_colored(6, 2, f"📊 Found {len(files_info)} files, total size: {format_size(total_size)}", 'info')
        ui.stdscr.refresh()

        # Send directory metadata
        dir_info = {
            'type': TRANSFER_TYPES['DIRECTORY'],
            'name': dirname,
            'files': files_info,
            'total_files': len(files_info),
            'total_size': total_size,
            'timestamp': time.time()
        }

        metadata = json.dumps(dir_info).encode('utf-8')
        sock.send(struct.pack('!I', len(metadata)))
        sock.send(metadata)

        # Wait for acknowledgment
        ack = sock.recv(4)
        if ack != b'ACK1':
            raise Exception("Failed to receive metadata acknowledgment")

        # Send files with overall progress
        progress = ProgressTracker(total_size, f"📁 Sending {dirname}", ui)
        sent_total = 0

        for i, file_info in enumerate(files_info, 1):
            # Update current file info
            current_file_y = ui.height - 5
            ui.stdscr.move(current_file_y, 0)
            ui.stdscr.clrtoeol()
            ui.print_colored(current_file_y, 2, f"📄 [{i}/{len(files_info)}] {file_info['path']}", 'special')
            ui.stdscr.refresh()

            try:
                with open(file_info['full_path'], 'rb') as f:
                    file_sent = 0
                    file_size = file_info['size']
                    
                    while file_sent < file_size:
                        remaining = file_size - file_sent
                        chunk_size = min(BUFFER_SIZE, remaining)
                        chunk = f.read(chunk_size)
                        
                        if not chunk:
                            break
                        
                        sock.sendall(chunk)
                        file_sent += len(chunk)
                        sent_total += len(chunk)
                        progress.update(sent_total)
                        
                # Wait for file acknowledgment
                file_ack = sock.recv(4)
                if file_ack != b'ACK2':
                    raise Exception(f"Failed to receive acknowledgment for {file_info['path']}")
                        
            except Exception as e:
                raise Exception(f"Error sending file {file_info['path']}: {e}")

        # Wait for final completion acknowledgment
        final_ack = sock.recv(4)
        if final_ack != b'DONE':
            raise Exception("Failed to receive final completion acknowledgment")

        ui.show_message("✅ Directory sent successfully!", 'success')
        return True

    except socket.timeout:
        ui.show_message("❌ Connection timeout during directory transfer", 'error')
        return False
    except ConnectionRefusedError:
        ui.show_message("❌ Connection refused - check IP and ensure receiver is running", 'error')
        return False
    except Exception as e:
        ui.show_message(f"❌ Error sending directory: {e}", 'error')
        return False
    finally:
        if sock:
            try:
                sock.close()
            except:
                pass