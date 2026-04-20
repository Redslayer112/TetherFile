import signal

from ui.textual_transfer_app import run_textual_transfer_app


def handle_sigint(signum, frame):
    raise KeyboardInterrupt


signal.signal(signal.SIGINT, handle_sigint)


def main():
    try:
        run_textual_transfer_app()
        print("\nApplication terminated gracefully")
    except KeyboardInterrupt:
        print("\nApplication terminated")
    except Exception as e:
        print(f"\nApplication error: {e}")


if __name__ == "__main__":
    main()