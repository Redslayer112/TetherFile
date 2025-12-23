import curses
import signal
import json
from ui.ui import CursesUI

# Load configuration
CONFIG = json.load(open('config.json'))

# Global signal handling
def handle_sigint(signum, frame):
    raise KeyboardInterrupt

signal.signal(signal.SIGINT, handle_sigint)


def main():
    def run_app(stdscr):
        ui = CursesUI()
        ui.init_screen(stdscr)
        
        # Select connection type
        connection_type = select_connection_type(ui)
        
        if not connection_type:
            ui.show_message("❌ No connection type selected, exiting", 'error')
            return
        
        # Import and run the selected connection
        if connection_type == 'lan':
            from transfers.lan.transfer import LANFileTransfer
            app = LANFileTransfer(ui)
            app.run()
        elif connection_type == 'bluetooth':
            ui.show_message("Bluetooth not yet implemented", 'warning')
        elif connection_type == 'usb':
            ui.show_message("USB not yet implemented", 'warning')

    try:
        curses.wrapper(run_app)
        print("\nApplication terminated gracefully")
    except KeyboardInterrupt:
        print("\nApplication terminated")
    except Exception as e:
        print(f"\nApplication error: {e}")


def select_connection_type(ui):
    """Let user select connection type - returns 'lan', 'bluetooth', 'usb', or None"""
    ui.draw_header("Connection Type Selection")
    
    box_height = 8
    box_y = 6
    ui.draw_box(box_y, 2, box_height, ui.width - 4, "SELECT CONNECTION TYPE")
    
    connection_types = [
        ("1", "LAN/WiFi Connection", "lan", True),
        ("2", "Bluetooth Connection", "bluetooth", False),
        ("3", "USB Wire Connection", "usb", False)
    ]
    
    for i, (key, name, _, available) in enumerate(connection_types):
        y_pos = box_y + 2 + i
        if available:
            ui.print_colored(y_pos, 4, f"{key}. {name}", 'highlight')
        else:
            ui.print_colored(y_pos, 4, f"{key}. {name} (Coming Soon)", 'info')
    
    ui.print_colored(box_y + 2 + len(connection_types) + 1, 4, "Q. Quit", 'warning')
    ui.stdscr.refresh()
    
    valid_choices = ['1', '2', '3', 'q', 'Q']
    choice = ui.get_single_key(box_y + box_height + 1, 2, "Select connection type", valid_choices)
    
    if choice in ['q', 'Q']:
        return None
    
    for key, name, conn_type, available in connection_types:
        if choice == key:
            if not available:
                ui.show_message(f"{name} not yet implemented", 'warning')
                import time
                time.sleep(2)
                return select_connection_type(ui)
            return conn_type
    
    return None


if __name__ == "__main__":
    main()