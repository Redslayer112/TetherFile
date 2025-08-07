from curses_ui import CursesUI
from transfer import LANFileTransfer
import curses
import sys


def main():
    try:
        import netifaces
    except ImportError:
        print("❌ Missing dependency: netifaces")
        print("📦 Install with: pip install netifaces")
        sys.exit(1)

    def run_app(stdscr):
        app = LANFileTransfer()
        app.ui.init_screen(stdscr)

        if not app.setup_direct_connection():
            app.ui.show_message("❌ Failed to setup network connection", 'error')
            return

        try:
            app.main_menu()
        except KeyboardInterrupt:
            pass
        finally:
            app.stop_server()

    try:
        curses.wrapper(run_app)
        print("\n👋 Application terminated gracefully")
    except KeyboardInterrupt:
        print("\n👋 Application terminated")
    except Exception as e:
        print(f"\n❌ Application error: {e}")


if __name__ == "__main__":
    main()
