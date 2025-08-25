from ui import CursesUI
from config import PORT, BUFFER_SIZE, RECEIVED_DIR
import sender
import network
import receiver

import threading

class LANFileTransfer:
    def __init__(self):
        self.port = PORT
        self.buffer_size = BUFFER_SIZE
        self.local_ip = None
        self.selected_interface_id = None
        self.ui = CursesUI()
    
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
                    result = network.setup_direct_connection(self.ui)
                    if result:
                        self.local_ip, self.selected_interface_id = result
                        self.ui.show_message(f"✅ Updated IP: {self.local_ip}", 'success')
                elif choice == '5':
                    break
                else:
                    self.ui.show_message("❌ Invalid option. Please try again.", 'error', 1)

            except KeyboardInterrupt:
                break
    
    def send_file_menu(self):
        """File sending menu"""
        target_ip = network.get_target_ip(self.ui)
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
            sender.send_file(self.ui, self.local_ip, self.buffer_size, file_path, target_ip, self.port)
            
            # Wait for user acknowledgment
            self.ui.print_colored(self.ui.height - 3, 2, "Press any key to continue...", 'highlight')
            self.ui.stdscr.refresh()
            self.ui.stdscr.getch()
    
    def send_directory_menu(self):
        """Directory sending menu"""
        target_ip = network.get_target_ip(self.ui)
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
            sender.send_directory(self.ui, self.local_ip, self.buffer_size, dir_path, target_ip, self.port)
            
            # Wait for user acknowledgment
            self.ui.print_colored(self.ui.height - 3, 2, "Press any key to continue...", 'highlight')
            self.ui.stdscr.refresh()
            self.ui.stdscr.getch()
    
    def receive_mode(self):
        self.ui.stdscr.clear()
        self.ui.draw_header("📥 Receive Mode Active")

        self.ui.print_colored(4, 2, f"🎯 Listening on {self.local_ip}:{self.port}", 'info')
        self.ui.print_colored(5, 2, f"💾 Files will be saved in {receiver.RECEIVED_DIR} folder.", 'info')
        self.ui.print_colored(6, 2, "🔗 Ensure sender uses this IP to connect.", 'warning')
        self.ui.print_colored(8, 2, "🔛 Starting server... Press 'Q' to stop.", 'highlight')
        self.ui.stdscr.refresh()

        # Create a server socket in a background thread
        server_thread = threading.Thread(
            target=receiver.start_server,
            args=(self.ui, self.local_ip, self.port, self.buffer_size),
            daemon=True
        )
        server_thread.start()

        try:
            while True:
                self.ui.stdscr.timeout(300)
                key = self.ui.stdscr.getch()
                if key in (ord('q'), ord('Q')):
                    break
        finally:
            receiver.stop_server()
            self.ui.show_message("🛑 Receive mode stopped.", 'warning')
