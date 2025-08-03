#!/usr/bin/env python3
"""
LAN File Transfer Application
Direct laptop-to-laptop file transfer via Ethernet cable
"""

import socket
import os
import json
import threading
import time
import struct
import hashlib
import subprocess
import platform
from pathlib import Path
import netifaces
import sys
from datetime import datetime, timedelta

class ProgressBar:
    def __init__(self, total, description="Progress"):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.time()
        self.last_update = 0

        
    def update(self, current):
        self.current = current
        now = time.time()
        
        # Update every 0.1 seconds to avoid flickering
        if now - self.last_update < 0.1 and current < self.total:
            return
        self.last_update = now
        
        # Calculate progress
        percentage = (current / self.total) * 100 if self.total > 0 else 0
        elapsed = now - self.start_time
        
        # Calculate speed and ETA
        if elapsed > 0 and current > 0:
            speed = current / elapsed
            if speed > 0:
                eta_seconds = (self.total - current) / speed
                eta = str(timedelta(seconds=int(eta_seconds)))
            else:
                eta = "∞"
            
            # Format speed
            if speed > 1024*1024:
                speed_str = f"{speed/(1024*1024):.1f} MB/s"
            elif speed > 1024:
                speed_str = f"{speed/1024:.1f} KB/s"
            else:
                speed_str = f"{speed:.1f} B/s"
        else:
            speed_str = "0 B/s"
            eta = "∞"
        
        # Format file size
        def format_size(size):
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    return f"{size:.1f} {unit}"
                size /= 1024
            return f"{size:.1f} TB"
        
        # Create progress bar
        bar_length = 30
        filled_length = int(bar_length * current // self.total) if self.total > 0 else 0
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        # Format output
        current_str = format_size(current)
        total_str = format_size(self.total)
        
        print(f"\r{self.description}: |{bar}| {percentage:.1f}% "
              f"({current_str}/{total_str}) {speed_str} ETA: {eta}", end='', flush=True)
        
        if current >= self.total:
            print()  # New line when complete

class LANFileTransfer:
    def __init__(self):
        self.port = 8888
        self.discovery_port = 8889
        self.buffer_size = 32 * 1024  # 128KB chunks for better performance
        self.server_socket = None
        self.discovery_socket = None
        self.is_server_running = False
        self.is_discovery_running = False
        self.local_ip = None
        self.selected_interface_id = None
        
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
                                # Get interface name for display
                                display_name = self.get_interface_name(interface)
                                interfaces.append((display_name, ip, interface))
                except:
                    continue
        except:
            pass
        return interfaces
    
    def get_interface_name(self, interface_id):
        """Get human-readable interface name on Windows"""
        try:
            import subprocess
            import json
            
            # Try to get interface name using PowerShell on Windows
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
            
            # Fallback to shortened GUID
            return interface_id[:8] + "..."
        except:
            return interface_id[:8] + "..."
    
    def setup_direct_connection(self):
        """Setup direct laptop-to-laptop connection"""
        interfaces = self.get_ethernet_interfaces()
        
        if not interfaces:
            print("❌ No network interfaces with IP addresses found!")
            print("\n💡 Possible solutions:")
            print("   1. Make sure Ethernet cable is connected")
            print("   2. Check if network adapter is enabled")
            print("   3. Try setting static IP manually")
            
            return self.manual_ip_setup()
        
        print(f"\n🔌 Found {len(interfaces)} network interface(s):")
        for i, (name, ip, interface_id) in enumerate(interfaces, 1):
            print(f"  {i}. {name} - {ip}")
        
        # Auto-select best interface or let user choose
        if len(interfaces) == 1:
            selected = interfaces[0]
            self.local_ip = selected[1]
            self.selected_interface_id = selected[2]
            print(f"✅ Auto-selected: {selected[0]} ({self.local_ip})")
            return selected
        else:
            # Multiple interfaces - let user choose
            while True:
                try:
                    choice = input(f"\nSelect interface (1-{len(interfaces)}) or 'auto' for best: ").strip().lower()
                    
                    if choice == 'auto':
                        # Prefer non-link-local IPs
                        for name, ip, interface_id in interfaces:
                            if not ip.startswith('169.254'):
                                selected = (name, ip, interface_id)
                                break
                        else:
                            selected = interfaces[0]  # Use first if all are link-local
                        
                        self.local_ip = selected[1]
                        self.selected_interface_id = selected[2]
                        print(f"✅ Auto-selected: {selected[0]} ({self.local_ip})")
                        return selected
                    
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(interfaces):
                        selected = interfaces[choice_idx]
                        self.local_ip = selected[1]
                        self.selected_interface_id = selected[2]
                        print(f"✅ Selected: {selected[0]} ({self.local_ip})")
                        return selected
                    else:
                        print("Invalid choice. Please try again.")
                except ValueError:
                    print("Please enter a number or 'auto'.")
    
    def manual_ip_setup(self):
        """Manual IP configuration helper"""
        print("\n🔧 Manual Setup Required")
        
        # Try to detect if we have any network interfaces with IPs
        all_interfaces = self.get_ethernet_interfaces()
        
        if all_interfaces:
            print(f"📡 Found {len(all_interfaces)} interface(s) with IP addresses:")
            for name, ip, interface_id in all_interfaces:
                print(f"   - {name}: {ip}")
            
            print("\n💡 You can manually specify an IP from above, or set a custom one")
        
        manual_ip = input("\n🌐 Enter your laptop's IP address (e.g., 192.168.1.10): ").strip()
        
        if self.validate_ip(manual_ip):
            self.local_ip = manual_ip
            self.selected_interface_id = None  # Manual IP
            return ("manual", manual_ip, None)
        else:
            print("❌ Invalid IP address format")
            return None
    
    def validate_ip(self, ip):
        """Validate IP address format"""
        try:
            parts = ip.split('.')
            return len(parts) == 4 and all(0 <= int(part) <= 255 for part in parts)
        except:
            return False
    
    def discover_peers(self):
        """Discover other laptops on the network"""
        if not self.local_ip:
            return []
        
        print("🔍 Scanning for other laptops...")
        peers = []
        
        # Get network range
        ip_parts = self.local_ip.split('.')
        network_base = '.'.join(ip_parts[:3])
        
        # Scan common IP ranges
        scan_ranges = []
        
        if self.local_ip.startswith('192.168.1.'):
            scan_ranges = [f"192.168.1.{i}" for i in range(1, 20)]
        elif self.local_ip.startswith('192.168.0.'):
            scan_ranges = [f"192.168.0.{i}" for i in range(1, 20)]
        elif self.local_ip.startswith('169.254.'):
            # Link-local network
            scan_ranges = [f"169.254.{ip_parts[2]}.{i}" for i in range(1, 255)]
        else:
            scan_ranges = [f"{network_base}.{i}" for i in range(1, 255)]
        
        # Limit scan for performance
        scan_ranges = scan_ranges[:50]
        
        def check_peer(ip):
            if ip == self.local_ip:
                return
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((ip, self.port))
                sock.close()
                if result == 0:
                    peers.append(ip)
                    print(f"✅ Found peer: {ip}")
            except:
                pass
        
        # Multi-threaded scanning for speed
        threads = []
        for ip in scan_ranges:
            thread = threading.Thread(target=check_peer, args=(ip,))
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Wait for scans to complete
        for thread in threads:
            thread.join()
        
        if peers:
            print(f"🎯 Found {len(peers)} peer(s): {', '.join(peers)}")
        else:
            print("❌ No peers found. Make sure the other laptop is running this program in receive mode.")
        
        return peers
    
    def select_target(self):
        """Select target IP for file transfer"""
        peers = self.discover_peers()
        
        if peers:
            if len(peers) == 1:
                return peers[0]
            else:
                print("\n🎯 Multiple peers found:")
                for i, peer in enumerate(peers, 1):
                    print(f"  {i}. {peer}")
                
                while True:
                    try:
                        choice = int(input(f"\nSelect target (1-{len(peers)}): ")) - 1
                        if 0 <= choice < len(peers):
                            return peers[choice]
                        else:
                            print("Invalid choice. Please try again.")
                    except ValueError:
                        print("Please enter a valid number.")
        
        # Manual IP entry
        print("\n🔧 Manual IP Entry")
        target_ip = input("Enter target laptop IP: ").strip()
        if self.validate_ip(target_ip):
            return target_ip
        else:
            print("❌ Invalid IP address")
            return None
    
    def calculate_file_hash(self, filepath):
        """Calculate MD5 hash of file"""
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def send_file(self, filepath, target_ip):
        """Send a single file with beautiful progress"""
        if not os.path.exists(filepath):
            print(f"❌ File not found: {filepath}")
            return False
        
        filename = os.path.basename(filepath)
        file_size = os.path.getsize(filepath)
        
        print(f"\n📤 Preparing to send: {filename}")
        print(f"📏 Size: {self.format_size(file_size)}")
        
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.local_ip:
                sock.bind((self.local_ip, 0))
            
            print(f"🔗 Connecting to {target_ip}...")
            sock.connect((target_ip, self.port))
            
            # Calculate hash
            print("🔐 Calculating file hash...")
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
            progress = ProgressBar(file_size, f"📤 Sending {filename}")
            
            with open(filepath, 'rb') as f:
                sent = 0
                
                while sent < file_size:
                    chunk = f.read(self.buffer_size)
                    if not chunk:
                        break
                    
                    sock.send(chunk)
                    sent += len(chunk)
                    progress.update(sent)
            
            print("✅ File sent successfully!")
            sock.close()
            return True
            
        except Exception as e:
            print(f"❌ Error sending file: {e}")
            return False
    
    def send_directory(self, dir_path, target_ip):
        """Send entire directory with progress"""
        if not os.path.isdir(dir_path):
            print(f"❌ Directory not found: {dir_path}")
            return False
        
        dirname = os.path.basename(dir_path)
        print(f"\n📁 Preparing to send directory: {dirname}")
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if self.local_ip:
                sock.bind((self.local_ip, 0))
            
            print(f"🔗 Connecting to {target_ip}...")
            sock.connect((target_ip, self.port))
            
            # Collect files
            print("📋 Scanning directory...")
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
            
            print(f"📊 Found {len(files_info)} files, total size: {self.format_size(total_size)}")
            
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
            progress = ProgressBar(total_size, f"📁 Sending {dirname}")
            sent_total = 0
            
            for i, file_info in enumerate(files_info, 1):
                print(f"\n📄 [{i}/{len(files_info)}] {file_info['path']}")
                
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
            
            print("✅ Directory sent successfully!")
            sock.close()
            return True
            
        except Exception as e:
            print(f"❌ Error sending directory: {e}")
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
            
            print(f"🎯 Server listening on {self.local_ip or 'all interfaces'}:{self.port}")
            print("💡 Ready to receive files... (Press Enter to stop)")
            
            while self.is_server_running:
                try:
                    client_socket, addr = self.server_socket.accept()
                    print(f"\n📥 Connection from {addr[0]}")
                    
                    thread = threading.Thread(
                        target=self.handle_client, 
                        args=(client_socket,)
                    )
                    thread.daemon = True
                    thread.start()
                    
                except socket.error:
                    if self.is_server_running:
                        print("❌ Server error occurred")
                    break
                    
        except Exception as e:
            print(f"❌ Error starting server: {e}")
    
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
            print(f"❌ Error handling client: {e}")
        finally:
            client_socket.close()
    
    def receive_file(self, client_socket, file_info):
        """Receive a single file with beautiful progress"""
        download_dir = "received_files"
        os.makedirs(download_dir, exist_ok=True)
        
        filepath = os.path.join(download_dir, file_info['name'])
        
        print(f"\n📥 Receiving: {file_info['name']}")
        print(f"📏 Size: {self.format_size(file_info['size'])}")
        
        progress = ProgressBar(file_info['size'], f"📥 Receiving {file_info['name']}")
        
        with open(filepath, 'wb') as f:
            received = 0
            total_size = file_info['size']
            
            while received < total_size:
                chunk_size = min(self.buffer_size, total_size - received)
                data = client_socket.recv(chunk_size)
                if not data:
                    break
                
                f.write(data)
                received += len(data)
                progress.update(received)
        
        # Verify integrity
        print("🔐 Verifying file integrity...")
        received_hash = self.calculate_file_hash(filepath)
        
        if received_hash == file_info['hash']:
            print(f"✅ File received and verified: {filepath}")
        else:
            print(f"⚠  File received but integrity check failed: {filepath}")
    
    def receive_directory(self, client_socket, dir_info):
        """Receive directory with progress"""
        download_dir = os.path.join("received_files", dir_info['name'])
        os.makedirs(download_dir, exist_ok=True)
        
        print(f"\n📁 Receiving directory: {dir_info['name']}")
        print(f"📊 {dir_info['total_files']} files, {self.format_size(dir_info['total_size'])}")
        
        progress = ProgressBar(dir_info['total_size'], f"📁 Receiving {dir_info['name']}")
        received_total = 0
        
        for i, file_info in enumerate(dir_info['files'], 1):
            print(f"\n📄 [{i}/{dir_info['total_files']}] {file_info['path']}")
            
            file_path = os.path.join(download_dir, file_info['path'])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'wb') as f:
                file_received = 0
                file_size = file_info['size']
                
                while file_received < file_size:
                    chunk_size = min(self.buffer_size, file_size - file_received)
                    data = client_socket.recv(chunk_size)
                    if not data:
                        break
                    
                    f.write(data)
                    file_received += len(data)
                    received_total += len(data)
                    progress.update(received_total)
        
        print(f"✅ Directory received: {download_dir}")
    
    def format_size(self, size):
        """Format file size in human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    def stop_server(self):
        """Stop the server"""
        self.is_server_running = False
        if self.server_socket:
            self.server_socket.close()
    
    def main_menu(self):
        """Main application menu"""
        print("🔗 LAN File Transfer - Direct Laptop Connection")
        print("=" * 50)
        
        # Setup connection
        if not self.setup_direct_connection():
            print("❌ Failed to setup network connection")
            return
        
        while True:
            print(f"\n{'='*50}")
            print(f"📱 LOCAL IP: {self.local_ip}")
            print("📋 MAIN MENU")
            print("1. 📤 Send File")
            print("2. 📁 Send Directory/Folder")
            print("3. 📥 Start Receiving Mode")
            print("4. 🔍 Scan for Peers")
            print("5. 🔧 Change IP Settings")
            print("6. ❌ Exit")
            
            choice = input("\nSelect option (1-6): ").strip()
            
            if choice == '1':
                self.send_file_menu()
            elif choice == '2':
                self.send_directory_menu()
            elif choice == '3':
                self.receive_mode()
            elif choice == '4':
                self.discover_peers()
            elif choice == '5':
                if self.setup_direct_connection():
                    print(f"✅ Updated IP: {self.local_ip}")
            elif choice == '6':
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid option. Please try again.")
    
    def send_file_menu(self):
        """File sending menu"""
        target_ip = self.select_target()
        if not target_ip:
            return
        
        print(f"\n🎯 Target: {target_ip}")
        file_path = input("📄 Enter file path (or drag & drop): ").strip()
        
        # Clean up path (remove quotes)
        if file_path.startswith('"') and file_path.endswith('"'):
            file_path = file_path[1:-1]
        
        self.send_file(file_path, target_ip)
    
    def send_directory_menu(self):
        """Directory sending menu"""
        target_ip = self.select_target()
        if not target_ip:
            return
        
        print(f"\n🎯 Target: {target_ip}")
        dir_path = input("📁 Enter directory path (or drag & drop): ").strip()
        
        # Clean up path
        if dir_path.startswith('"') and dir_path.endswith('"'):
            dir_path = dir_path[1:-1]
        
        self.send_directory(dir_path, target_ip)
    
    def receive_mode(self):
        """Server mode for receiving files"""
        # Safety check for port attribute
        if not hasattr(self, 'port'):
            self.port = 8888
            
        print(f"\n🎯 Starting receive mode on {self.local_ip}:{self.port}")
        print("💾 Files will be saved in 'received_files' directory")
        print("🔗 Other laptop should use this IP as target")
        
        try:
            server_thread = threading.Thread(target=self.start_server)
            server_thread.daemon = True
            server_thread.start()
            
            input()  # Wait for Enter
            self.stop_server()
            print("🛑 Receive mode stopped")
            
        except KeyboardInterrupt:
            self.stop_server()
            print("\n🛑 Receive mode stopped")

if __name__ == "__main__":
    # Check dependencies
    try:
        import netifaces
    except ImportError:
        print("❌ Missing dependency: netifaces")
        print("📦 Install with: pip install netifaces")
        sys.exit(1)
    
    print("🚀 Initializing LAN File Transfer...")
    app = LANFileTransfer()
    
    try:
        app.main_menu()
    except KeyboardInterrupt:
        print("\n\n👋 Application terminated")
        app.stop_server()