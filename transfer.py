from curses_ui import CursesUI
from progress import ProgressTracker
import socket
import os
import json
import struct
import hashlib
import threading
import time
import platform
import subprocess
import signal
import netifaces
from pathlib import Path
from datetime import datetime

class LANFileTransfer:
    def __init__(self):
        self.port = 8888
        self.buffer_size = 32 * 1024
        self.server_socket = None
        self.is_server_running = False
        self.local_ip = None
        self.selected_interface_id = None
        self.ui = CursesUI()
        self.failed_validations = []  # Track failed file validations
        
    def get_ethernet_interfaces(self):
        """Get available Ethernet interfaces with their IPs"""
        interfaces = []
        try:
            for interface in netifaces.interfaces():
                try:
                    addrs = netifaces.ifaddresses(interface)
                    if netifaces.AF_INET in addrs:
                        for addr_info in addrs[netifaces.AF_INET]:
                            ip = addr_info.get('addr', '')
                            # Skip loopback and invalid IPs
                            if ip and ip != '127.0.0.1' and not ip.startswith('127.'):
                                display_name = self.get_interface_name(interface)
                                interfaces.append((display_name, ip, interface))
                except:
                    continue
        except:
            pass
        return interfaces
    
    def get_interface_name(self, interface_id):
        """Get human-readable interface name"""
        try:
            if platform.system() == "Windows":
                try:
                    cmd = f'powershell "Get-NetAdapter | Where-Object {{$_.InterfaceGuid -eq \\"{interface_id}\\"}} | Select-Object Name, InterfaceDescription | ConvertTo-Json"'
                    result = subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=5)
                    if result.returncode == 0 and result.stdout.strip():
                        data = json.loads(result.stdout.strip())
                        if isinstance(data, dict):
                            return f"{data.get('Name', interface_id[:8])} ({data.get('InterfaceDescription', 'Network Adapter')[:30]})"
                        elif isinstance(data, list) and len(data) > 0:
                            return f"{data[0].get('Name', interface_id[:8])} ({data[0].get('InterfaceDescription', 'Network Adapter')[:30]})"
                except:
                    pass
            
            return interface_id[:8] + "..."
        except:
            return interface_id[:8] + "..."
    
    def setup_direct_connection(self):
        """Setup direct laptop-to-laptop connection"""
        self.ui.stdscr.clear()
        self.ui.draw_header("🔌 Network Interface Selection")
        
        interfaces = self.get_ethernet_interfaces()
        
        if not interfaces:
            self.ui.print_colored(4, 2, "❌ No network interfaces with IP addresses found!", 'error')
            self.ui.print_colored(6, 2, "💡 Possible solutions:", 'warning')
            self.ui.print_colored(7, 4, "1. Make sure Ethernet cable is connected", 'info')
            self.ui.print_colored(8, 4, "2. Check if network adapter is enabled", 'info')
            self.ui.print_colored(9, 4, "3. Try setting static IP manually", 'info')
            
            return self.ip_setup()
        
        # Display interfaces
        self.ui.print_colored(4, 2, f"🔌 Found {len(interfaces)} network interface(s):", 'success')
        
        for i, (name, ip, interface_id) in enumerate(interfaces, 1):
            self.ui.print_colored(5 + i, 4, f"{i}. {name} - {ip}", 'info')
        
        # Select interface
        while True:
            try:
                choice = self.ui.get_input(7 + len(interfaces), 2, f"Select interface (1-{len(interfaces)}): ")
                
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(interfaces):
                    selected = interfaces[choice_idx]
                    self.local_ip = selected[1]
                    self.selected_interface_id = selected[2]
                    self.ui.show_message(f"✅ Selected: {selected[0]} ({self.local_ip})", 'success')
                    return True
                else:
                    self.ui.show_message("Invalid choice. Please try again.", 'error', 1)
            except ValueError:
                self.ui.show_message("Please enter a number or 'auto'.", 'error', 1)
    
    def ip_setup(self):
        """Manual IP configuration helper"""
        self.ui.print_colored(12, 2, "🔧 Manual Setup Required", 'warning')
        
        all_interfaces = self.get_ethernet_interfaces()
        
        if all_interfaces:
            self.ui.print_colored(14, 2, f"📡 Found {len(all_interfaces)} interface(s) with IP addresses:", 'info')
            for i, (name, ip, interface_id) in enumerate(all_interfaces):
                self.ui.print_colored(15 + i, 4, f"- {name}: {ip}", 'info')
            
            self.ui.print_colored(17 + len(all_interfaces), 2, "💡 You can manually specify an IP from above, or set a custom one", 'info')
        
        manual_ip = self.ui.get_input(19 + len(all_interfaces), 2, "🌐 Enter your laptop's IP address (e.g., 192.168.1.10): ")
        
        if self.validate_ip(manual_ip):
            self.local_ip = manual_ip
            self.selected_interface_id = None
            self.ui.show_message(f"✅ Manual IP set: {manual_ip}", 'success')
            return True
        else:
            self.ui.show_message("❌ Invalid IP address format", 'error')
            return False
    
    def validate_ip(self, ip):
        """Validate IP address format"""
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except:
            return False
    
    def calculate_file_hash(self, filepath):
        """Calculate SHA-256 hash of file"""
        hash_sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def send_file(self, filepath, target_ip):
        """Send a single file with beautiful progress"""
        if not os.path.exists(filepath):
            self.ui.show_message(f"❌ File not found: {filepath}", 'error')
            return False
        
        filename = os.path.basename(filepath)
        file_size = os.path.getsize(filepath)
        
        self.ui.stdscr.clear()
        self.ui.draw_header(f"📤 Sending File: {filename}")
        
        self.ui.print_colored(4, 2, f"📏 Size: {self.format_size(file_size)}", 'info')
        self.ui.print_colored(5, 2, f"🎯 Target: {target_ip}", 'info')
        
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.local_ip:
                sock.bind((self.local_ip, 0))
            
            self.ui.print_colored(7, 2, f"🔗 Connecting to {target_ip}...", 'warning')
            self.ui.stdscr.refresh()
            sock.connect((target_ip, self.port))
            
            # Calculate hash
            self.ui.print_colored(8, 2, "🔐 Calculating file hash...", 'warning')
            self.ui.stdscr.refresh()
            file_hash = self.calculate_file_hash(filepath)
            
            # Prepare metadata
            file_info = {
                'type': 'file',
                'name': filename,
                'size': file_size,
                'hash': file_hash,
                'timestamp': time.time()
            }
            
            # Send metadata
            metadata = json.dumps(file_info).encode()
            sock.send(struct.pack('!I', len(metadata)))
            sock.send(metadata)
            
            # Send file with progress
            progress = ProgressTracker(file_size, f"📤 Sending {filename}", self.ui)
            
            with open(filepath, 'rb') as f:
                sent = 0
                
                while sent < file_size:
                    chunk = f.read(self.buffer_size)
                    if not chunk:
                        break
                    
                    sock.send(chunk)
                    sent += len(chunk)
                    progress.update(sent)
            
            self.ui.show_message("✅ File sent successfully!", 'success')
            sock.close()
            return True
            
        except Exception as e:
            self.ui.show_message(f"❌ Error sending file: {e}", 'error')
            return False
    
    def send_directory(self, dir_path, target_ip):
        """Send entire directory with progress"""
        if not os.path.isdir(dir_path):
            self.ui.show_message(f"❌ Directory not found: {dir_path}", 'error')
            return False
        
        dirname = os.path.basename(dir_path)
        
        self.ui.stdscr.clear()
        self.ui.draw_header(f"📁 Sending Directory: {dirname}")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.local_ip:
                sock.bind((self.local_ip, 0))
            
            self.ui.print_colored(4, 2, f"🔗 Connecting to {target_ip}...", 'warning')
            self.ui.stdscr.refresh()
            sock.connect((target_ip, self.port))
            
            # Collect files
            self.ui.print_colored(5, 2, "📋 Scanning directory...", 'warning')
            self.ui.stdscr.refresh()
            
            files_info = []
            total_size = 0
            base_path = Path(dir_path)
            
            for file_path in base_path.rglob('*'):
                if file_path.is_file():
                    rel_path = file_path.relative_to(base_path)
                    size = file_path.stat().st_size
                    files_info.append({
                        'path': str(rel_path),
                        'full_path': str(file_path),
                        'size': size
                    })
                    total_size += size
            
            self.ui.print_colored(6, 2, f"📊 Found {len(files_info)} files, total size: {self.format_size(total_size)}", 'info')
            self.ui.stdscr.refresh()
            
            # Send directory metadata
            dir_info = {
                'type': 'directory',
                'name': dirname,
                'files': files_info,
                'total_files': len(files_info),
                'total_size': total_size,
                'timestamp': time.time()
            }
            
            metadata = json.dumps(dir_info).encode()
            sock.send(struct.pack('!I', len(metadata)))
            sock.send(metadata)
            
            # Send files with overall progress
            progress = ProgressTracker(total_size, f"📁 Sending {dirname}", self.ui)
            sent_total = 0
            
            for i, file_info in enumerate(files_info, 1):
                # Update current file info
                current_file_y = self.ui.height - 5
                self.ui.stdscr.move(current_file_y, 0)
                self.ui.stdscr.clrtoeol()
                self.ui.print_colored(current_file_y, 2, f"📄 [{i}/{len(files_info)}] {file_info['path']}", 'special')
                
                with open(file_info['full_path'], 'rb') as f:
                    file_sent = 0
                    file_size = file_info['size']
                    
                    while file_sent < file_size:
                        chunk = f.read(self.buffer_size)
                        if not chunk:
                            break
                        
                        sock.send(chunk)
                        file_sent += len(chunk)
                        sent_total += len(chunk)
                        progress.update(sent_total)
            
            self.ui.show_message("✅ Directory sent successfully!", 'success')
            sock.close()
            return True
            
        except Exception as e:
            self.ui.show_message(f"❌ Error sending directory: {e}", 'error')
            return False
    
    def start_server(self):
        """Start receiving server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if self.local_ip:
                self.server_socket.bind((self.local_ip, self.port))
            else:
                self.server_socket.bind(('', self.port))
            
            self.server_socket.listen(5)
            self.is_server_running = True
            
            self.ui.stdscr.clear()
            self.ui.draw_header("📥 Receive Mode Active")
            
            self.ui.print_colored(4, 2, f"🎯 Server listening on {self.local_ip or 'all interfaces'}:{self.port}", 'success')
            self.ui.print_colored(5, 2, "💾 Files will be saved in 'received_files' directory", 'info')
            self.ui.print_colored(6, 2, "🔗 Other laptop should use this IP as target", 'info')
            self.ui.print_colored(8, 2, "💡 Ready to receive files... (Press 'q' to stop)", 'highlight')
            self.ui.stdscr.refresh()
            
            while self.is_server_running:
                try:
                    self.server_socket.settimeout(1.0)  # Allow checking for stop condition
                    client_socket, addr = self.server_socket.accept()
                    
                    self.ui.print_colored(10, 2, f"📥 Connection from {addr[0]}", 'success')
                    self.ui.stdscr.refresh()
                    
                    thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket,)
                    )
                    thread.daemon = True
                    thread.start()
                    
                except socket.timeout:
                    continue
                except socket.error:
                    if self.is_server_running:
                        self.ui.show_message("❌ Server error occurred", 'error')
                    break
                    
        except Exception as e:
            self.ui.show_message(f"❌ Error starting server: {e}", 'error')
    
    def handle_client(self, client_socket):
        """Handle incoming file transfer"""
        try:
            # Receive metadata
            metadata_size = struct.unpack('!I', client_socket.recv(4))[0]
            metadata = json.loads(client_socket.recv(metadata_size).decode())
            
            if metadata['type'] == 'file':
                self.receive_file(client_socket, metadata)
            elif metadata['type'] == 'directory':
                self.receive_directory(client_socket, metadata)
                
        except Exception as e:
            self.ui.show_message(f"❌ Error handling client: {e}", 'error')
        finally:
            client_socket.close()
    
    def receive_file(self, client_socket, file_info):
        """Receive a single file with beautiful progress"""
        download_dir = "received_files"
        os.makedirs(download_dir, exist_ok=True)
        
        filepath = os.path.join(download_dir, file_info['name'])
        
        self.ui.stdscr.clear()
        self.ui.draw_header(f"📥 Receiving: {file_info['name']}")
        
        self.ui.print_colored(4, 2, f"📏 Size: {self.format_size(file_info['size'])}", 'info')
        self.ui.stdscr.refresh()
        
        progress = ProgressTracker(file_info['size'], f"📥 Receiving {file_info['name']}", self.ui)
        
        with open(filepath, 'wb') as f:
            received = 0
            total_size = file_info['size']
            
            while received < total_size:
                try:
                    chunk_size = min(self.buffer_size, total_size - received)
                    data = client_socket.recv(chunk_size)
                    if not data:
                        break
                    
                    f.write(data)
                    received += len(data)
                    progress.update(received)
                except socket.error:
                    break
        
        # Verify integrity
        self.ui.print_colored(self.ui.height - 6, 2, "🔐 Verifying file integrity...", 'warning')
        self.ui.stdscr.refresh()
        
        received_hash = self.calculate_file_hash(filepath)
        
        if received_hash == file_info['hash']:
            self.ui.show_message(f"✅ File received and verified: {filepath}", 'success')
        else:
            self.failed_validations.append({
                'file': filepath,
                'expected': file_info['hash'][:16] + '...',
                'received': received_hash[:16] + '...'
            })
            self.ui.show_message(f"⚠️ File received but integrity check failed: {filepath}", 'error')
    
    def receive_directory(self, client_socket, dir_info):
        """Receive directory with progress"""
        download_dir = os.path.join("received_files", dir_info['name'])
        os.makedirs(download_dir, exist_ok=True)
        
        self.ui.stdscr.clear()
        self.ui.draw_header(f"📁 Receiving Directory: {dir_info['name']}")
        
        self.ui.print_colored(4, 2, f"📊 {dir_info['total_files']} files, {self.format_size(dir_info['total_size'])}", 'info')
        self.ui.stdscr.refresh()
        
        progress = ProgressTracker(dir_info['total_size'], f"📁 Receiving {dir_info['name']}", self.ui)
        received_total = 0
        
        for i, file_info in enumerate(dir_info['files'], 1):
            # Update current file info
            current_file_y = self.ui.height - 5
            self.ui.stdscr.move(current_file_y, 0)
            self.ui.stdscr.clrtoeol()
            self.ui.print_colored(current_file_y, 2, f"📄 [{i}/{dir_info['total_files']}] {file_info['path']}", 'special')
            
            file_path = os.path.join(download_dir, file_info['path'])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'wb') as f:
                file_received = 0
                file_size = file_info['size']
                
                while file_received < file_size:
                    try:
                        chunk_size = min(self.buffer_size, file_size - file_received)
                        data = client_socket.recv(chunk_size)
                        if not data:
                            break
                        
                        f.write(data)
                        file_received += len(data)
                        received_total += len(data)
                        progress.update(received_total)
                    except socket.error:
                        break
        
        self.ui.show_message(f"✅ Directory received: {download_dir}", 'success')
        
        # Show validation summary if there were failures
        if self.failed_validations:
            self.show_validation_summary()
    
    def show_validation_summary(self):
        """Show summary of failed validations"""
        self.ui.stdscr.clear()
        self.ui.draw_header("⚠️ File Validation Summary")
        
        self.ui.print_colored(4, 2, f"❌ {len(self.failed_validations)} file(s) failed integrity check:", 'error')
        
        y_pos = 6
        for i, failure in enumerate(self.failed_validations):
            if y_pos >= self.ui.height - 4:
                self.ui.print_colored(y_pos, 2, "... (more failures not shown)", 'warning')
                break
                
            self.ui.print_colored(y_pos, 4, f"• {failure['file']}", 'error')
            self.ui.print_colored(y_pos + 1, 6, f"Expected: {failure['expected']}", 'info')
            self.ui.print_colored(y_pos + 2, 6, f"Received: {failure['received']}", 'info')
            y_pos += 4
        
        self.ui.print_colored(self.ui.height - 3, 2, "Press any key to continue...", 'highlight')
        self.ui.stdscr.refresh()
        self.ui.stdscr.getch()
        
        # Clear the list for next transfer
        self.failed_validations = []
    
    def format_size(self, size):
        """Convert a file size in bytes to a human-readable string."""
        if size <= 0:
            return "0 B"

        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        for unit in units:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} EB"

    
    def stop_server(self):
        """Stop the server"""
        self.is_server_running = False
        if self.server_socket:
            self.server_socket.close()
    
    def main_menu(self):
        """Main application menu"""
        while True:
            self.ui.stdscr.clear()
            self.ui.draw_header("🔗 LAN File Transfer - Direct Laptop Connection")
            self.ui.print_colored(self.ui.height - 2, 0, "═" * (self.ui.width - 1), 'highlight')

            # Display local IP
            if self.local_ip:
                self.ui.print_colored(4, 2, f"📱 LOCAL IP: {self.local_ip}", 'success')

            # Menu options
            box_height = 9
            box_y = 6
            self.ui.draw_box(box_y, 2, box_height, self.ui.width - 4, "📋 MAIN MENU")

            menu_items = [
                "1. 📤 Send File",
                "2. 📁 Send Directory/Folder",
                "3. 📥 Start Receiving Mode",
                "4. 🔧 Change IP Settings",
                "5. ❌ Exit"
            ]

            for i, item in enumerate(menu_items):
                color = 'highlight' if i < 3 else 'info'
                self.ui.print_colored(box_y + 2 + i, 4, item, color)

            self.ui.stdscr.refresh()

            try:
                choice = self.ui.get_input(box_y + box_height + 1, 2, "Select option (1-5): ")

                if choice == '1':
                    self.send_file_menu()
                elif choice == '2':
                    self.send_directory_menu()
                elif choice == '3':
                    self.receive_mode()
                    continue  # return to menu after receiving
                elif choice == '4':
                    if self.setup_direct_connection():
                        self.ui.show_message(f"✅ Updated IP: {self.local_ip}", 'success')
                elif choice == '5':
                    break
                else:
                    self.ui.show_message("❌ Invalid option. Please try again.", 'error', 1)

            except KeyboardInterrupt:
                break
    
    def get_target_ip(self):
        """Get target IP from user"""
        self.ui.stdscr.clear()
        self.ui.draw_header("🎯 Target Selection")
        
        self.ui.print_colored(4, 2, "Enter the IP address of the target laptop:", 'info')
        self.ui.print_colored(5, 2, "Make sure the other laptop is running this program in receive mode.", 'warning')
        
        while True:
            target_ip = self.ui.get_input(7, 2, "🌐 Target IP: ")
            
            if self.validate_ip(target_ip):
                return target_ip
            else:
                self.ui.show_message("❌ Invalid IP address format. Please try again.", 'error', 1)
    
    def send_file_menu(self):
        """File sending menu"""
        target_ip = self.get_target_ip()
        if not target_ip:
            return
        
        self.ui.stdscr.clear()
        self.ui.draw_header("📤 Send File")
        
        self.ui.print_colored(4, 2, f"🎯 Target: {target_ip}", 'success')
        file_path = self.ui.get_input(6, 2, "📄 Enter file path (or drag & drop): ")
        
        # Clean up path (remove quotes)
        if file_path.startswith('"') and file_path.endswith('"'):
            file_path = file_path[1:-1]
        
        if file_path:
            self.send_file(file_path, target_ip)
            
            # Wait for user acknowledgment
            self.ui.print_colored(self.ui.height - 3, 2, "Press any key to continue...", 'highlight')
            self.ui.stdscr.refresh()
            self.ui.stdscr.getch()
    
    def send_directory_menu(self):
        """Directory sending menu"""
        target_ip = self.get_target_ip()
        if not target_ip:
            return
        
        self.ui.stdscr.clear()
        self.ui.draw_header("📁 Send Directory")
        
        self.ui.print_colored(4, 2, f"🎯 Target: {target_ip}", 'success')
        dir_path = self.ui.get_input(6, 2, "📁 Enter directory path (or drag & drop): ")
        
        # Clean up path
        if dir_path.startswith('"') and dir_path.endswith('"'):
            dir_path = dir_path[1:-1]
        
        if dir_path:
            self.send_directory(dir_path, target_ip)
            
            # Wait for user acknowledgment
            self.ui.print_colored(self.ui.height - 3, 2, "Press any key to continue...", 'highlight')
            self.ui.stdscr.refresh()
            self.ui.stdscr.getch()
    
    def receive_mode(self):
        """Server mode for receiving files"""
        self.ui.stdscr.clear()
        self.ui.draw_header("📥 Receive Mode Active")

        self.ui.print_colored(4, 2, f"🎯 Listening on {self.local_ip}:{self.port}", 'info')
        self.ui.print_colored(5, 2, "💾 Files will be saved in the 'received_files' folder.", 'info')
        self.ui.print_colored(6, 2, "🔗 Ensure sender uses this IP to connect.", 'warning')
        self.ui.print_colored(8, 2, "🔛 Starting server... Press 'Q' to stop.", 'highlight')
        self.ui.stdscr.refresh()

        def signal_handler(signum, frame):
            self.stop_server()

        signal.signal(signal.SIGINT, signal_handler)

        server_thread = threading.Thread(target=self.start_server, daemon=True)
        server_thread.start()

        try:
            while self.is_server_running:
                self.ui.stdscr.timeout(300)
                key = self.ui.stdscr.getch()
                if key in (ord('q'), ord('Q')):
                    break
        finally:
            self.stop_server()
            self.ui.show_message("🛑 Receive mode stopped.", 'warning')
