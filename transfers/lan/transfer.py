import transfers.lan.sender as sender
import transfers.lan.network as network
import transfers.lan.receiver as receiver
from core.utils import clean_path
import threading
import json
import time
import os

CONFIG = json.load(open('config.json'))
PORT = CONFIG['PORT']
BUFFER_SIZE = CONFIG['BUFFER_SIZE']
RECEIVED_DIR = CONFIG['RECEIVED_DIR']

class LANFileTransfer:
    def __init__(self, ui):
        self.port = PORT
        self.buffer_size = BUFFER_SIZE
        self.local_ip = None
        self.selected_interface_id = None
        self.ui = ui  # Use the passed UI instance
        self.server_control = None  # Will hold server control dictionary
    
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
                choice = self.ui.get_single_key(box_y + box_height + 1, 2, "Select option (1-5)", ['1', '2', '3', '4', '5'])

                if choice == '1':
                    self.send_file_menu()
                elif choice == '2':
                    self.send_directory_menu()
                elif choice == '3':
                    self.receive_mode()
                    continue  # return to menu after receiving
                elif choice == '4':
                    result = self.setup_direct_connection()
                    if result:
                        self.local_ip, self.selected_interface_id = result
                        self.ui.show_message(f"✅ Updated IP: {self.local_ip}", 'success')
                elif choice == '5':
                    break
                else:
                    self.ui.show_message("❌ Invalid option. Please try again.", 'error', 1)

            except KeyboardInterrupt:
                break
    
    def setup_direct_connection(self):
        """Setup LAN connection by selecting network interface"""
        interfaces = network.get_all_network_interfaces()
        
        if not interfaces:
            self.ui.show_message("❌ No network interfaces found!", 'error')
            return None
        
        self.ui.stdscr.clear()
        self.ui.draw_header("🔗 LAN Connection Setup")
        
        box_height = min(len(interfaces) + 4, self.ui.height - 10)
        box_y = 4
        self.ui.draw_box(box_y, 2, box_height, self.ui.width - 4, "SELECT NETWORK INTERFACE")
        
        # Display interfaces
        for i, (desc, adapter, ip, iface_id) in enumerate(interfaces):
            y_pos = box_y + 2 + i
            if y_pos >= box_y + box_height - 2:
                break
            self.ui.print_colored(y_pos, 4, f"{i+1}. {desc} - {ip}", 'highlight')
        
        self.ui.stdscr.refresh()
        
        # Get user selection
        valid_choices = [str(i+1) for i in range(len(interfaces))]
        choice = self.ui.get_single_key(box_y + box_height + 1, 2, "Select interface (or ESC to cancel)", valid_choices + ['ESC'])
        
        if choice == 'ESC':
            return None
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(interfaces):
                desc, adapter, ip, iface_id = interfaces[idx]
                return ip, iface_id
        except ValueError:
            pass
        
        return None
    
    def get_target_ip(self):
        """Get target IP from user"""
        self.ui.stdscr.clear()
        self.ui.draw_header("🎯 Target IP Address")
        
        target_ip = self.ui.get_input(4, 2, "Enter receiver IP address: ")
        
        if not target_ip or not network.validate_ip(target_ip):
            self.ui.show_message("❌ Invalid IP address format", 'error')
            return None
        
        return target_ip
    
    def send_file_menu(self):
        """File sending menu"""
        if not self.local_ip:
            self.ui.show_message("❌ Please set up IP settings first (option 4)", 'error')
            return
            
        target_ip = self.get_target_ip()
        if not target_ip:
            return
        
        self.ui.stdscr.clear()
        self.ui.draw_header("📤 Send File")
        
        self.ui.print_colored(4, 2, f"🎯 Target: {target_ip}", 'success')
        file_path = self.ui.get_input(6, 2, "📄 Enter file path (or drag & drop): ")
        
        file_path = clean_path(file_path)
        
        if file_path:
            if not os.path.isfile(file_path):
                self.ui.show_message("❌ Not a valid file path!", 'error')
                return
            
            success = sender.send_file(file_path, target_ip, self.port, self.local_ip, self.ui)
            
            if success:
                self.ui.show_message("✅ File sent successfully!", 'success')
            else:
                self.ui.show_message("❌ File sending failed", 'error')
                
            # Wait for user acknowledgment
            self.ui.print_colored(self.ui.height - 3, 2, "Press any key to continue...", 'highlight')
            self.ui.stdscr.refresh()
            self._wait_for_keypress()
    
    def send_directory_menu(self):
        """Directory sending menu"""
        if not self.local_ip:
            self.ui.show_message("❌ Please set up IP settings first (option 4)", 'error')
            return
            
        target_ip = self.get_target_ip()
        if not target_ip:
            return
        
        self.ui.stdscr.clear()
        self.ui.draw_header("📁 Send Directory")
        
        self.ui.print_colored(4, 2, f"🎯 Target: {target_ip}", 'success')
        dir_path = self.ui.get_input(6, 2, "📁 Enter directory path (or drag & drop): ")
        
        dir_path = clean_path(dir_path)
        
        if dir_path:
            if not os.path.isdir(dir_path):
                self.ui.show_message("❌ Not a valid directory path!", 'error')
                return
            
            success = sender.send_directory(dir_path, target_ip, self.port, self.local_ip, self.ui)
            
            if success:
                self.ui.show_message("✅ Directory sent successfully!", 'success')
            else:
                self.ui.show_message("❌ Directory sending failed", 'error')
                
            # Wait for user acknowledgment
            self.ui.print_colored(self.ui.height - 3, 2, "Press any key to continue...", 'highlight')
            self.ui.stdscr.refresh()
            self._wait_for_keypress()
    
    def receive_mode(self):
        """Start receiving mode with proper server control"""
        if not self.local_ip:
            self.ui.show_message("❌ Please set up IP settings first (option 4)", 'error')
            return
            
        # Initialize server control dictionary
        self.server_control = {
            'running': False,
            'socket': None
        }
        
        self.ui.stdscr.clear()
        self.ui.draw_header("📥 Receive Mode Active")

        self.ui.print_colored(4, 2, f"🎯 Listening on {self.local_ip}:{self.port}", 'info')
        self.ui.print_colored(5, 2, f"💾 Files will be saved in {RECEIVED_DIR} folder.", 'info')
        self.ui.print_colored(6, 2, "🔗 Ensure sender uses this IP to connect.", 'warning')
        self.ui.print_colored(8, 2, "🟢 Starting server... Press 'Q' to stop.", 'highlight')
        self.ui.stdscr.refresh()

        # Create a server thread
        server_thread = threading.Thread(
            target=receiver.start_server,
            args=(self.local_ip, self.port, self.ui, self.server_control),
            daemon=True
        )
        server_thread.start()

        # Give the server a moment to start
        time.sleep(0.5)
        
        # Check if server started successfully
        if not self.server_control.get('running', False):
            self.ui.show_message("❌ Failed to start server. Check IP settings and port availability.", 'error')
            return

        try:
            # Wait for user input to stop server
            while self.server_control.get('running', False):
                self.ui.stdscr.timeout(300)  # 300ms timeout for getch()
                key = self.ui.stdscr.getch()
                if key in (ord('q'), ord('Q')):
                    break
                elif key == -1:  # Timeout occurred, continue loop
                    continue
                    
        except KeyboardInterrupt:
            pass
        finally:
            # Properly stop the server
            if self.server_control:
                receiver.stop_server(self.server_control)
                
                # Wait a moment for clean shutdown
                shutdown_timeout = 3.0
                start_time = time.time()
                while (self.server_control.get('running', False) and 
                       time.time() - start_time < shutdown_timeout):
                    time.sleep(0.1)
                    
            self.ui.show_message("🛑 Receive mode stopped.", 'warning')
            
            # Wait for user acknowledgment before returning to menu
            self.ui.print_colored(self.ui.height - 3, 2, "Press any key to return to main menu...", 'highlight')
            self.ui.stdscr.refresh()
            self._wait_for_keypress()
    
    def _wait_for_keypress(self):
        """Wait for user keypress with timeout to prevent hanging"""
        self.ui.stdscr.timeout(5000)  # 5 second timeout
        try:
            key = self.ui.stdscr.getch()
            if key == -1:  # Timeout occurred
                pass  # Continue anyway
        except:
            pass
        finally:
            self.ui.stdscr.timeout(-1)  # Restore blocking mode
    
    def cleanup(self):
        """Clean up resources when exiting"""
        if self.server_control and self.server_control.get('running', False):
            receiver.stop_server(self.server_control)
    
    def run(self):
        """Main entry point for the application"""
        try:
            # Initialize network settings if not set
            if not self.local_ip:
                result = self.setup_direct_connection()
                if result:
                    self.local_ip, self.selected_interface_id = result
                else:
                    self.ui.show_message("❌ Network setup required. Please configure your IP settings.", 'error')
                    return
            
            # Start main menu
            self.main_menu()
            
        except KeyboardInterrupt:
            self.ui.show_message("👋 Goodbye!", 'info')
        except Exception as e:
            self.ui.show_message(f"❌ Unexpected error: {e}", 'error')
        finally:
            self.cleanup()