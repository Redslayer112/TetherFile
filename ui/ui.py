import curses
import time

class CursesUI:
    def __init__(self):
        self.stdscr = None
        self.colors = {}
        self.height = 0
        self.width = 0

    def init_colors(self):
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()

            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_BLUE, -1)
            curses.init_pair(5, curses.COLOR_CYAN, -1)
            curses.init_pair(6, curses.COLOR_MAGENTA, -1)
            curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)

            self.colors = {
                'success': curses.color_pair(1) | curses.A_BOLD,
                'error': curses.color_pair(2) | curses.A_BOLD,
                'warning': curses.color_pair(3) | curses.A_BOLD,
                'info': curses.color_pair(4),
                'highlight': curses.color_pair(5) | curses.A_BOLD,
                'special': curses.color_pair(6) | curses.A_BOLD,
                'header': curses.color_pair(7) | curses.A_BOLD,
                'normal': curses.A_NORMAL
            }

    def init_screen(self, stdscr):
        self.stdscr = stdscr
        curses.curs_set(0)
        self.stdscr.clear()
        self.height, self.width = self.stdscr.getmaxyx()
        self.init_colors()

    def clear_terminal_buffer(self):
        """Clear terminal including scrollback buffer"""
        import os
        if os.name == 'posix':  # Unix/Linux/macOS
            # Send escape sequence to clear scrollback buffer
            self.stdscr.addstr(0, 0, '\033[3J\033[2J\033[H')
        self.stdscr.erase()
        self.stdscr.refresh()

    def draw_header(self, title):
        # Use complete terminal clearing for headers
        self.clear_terminal_buffer()
        
        self.stdscr.attron(self.colors['header'])
        header_text = f" {title} "
        padding = (self.width - len(header_text)) // 2
        self.stdscr.addstr(0, 0, " " * self.width)
        self.stdscr.addstr(0, padding, header_text)
        self.stdscr.attroff(self.colors['header'])

        self.stdscr.attron(self.colors['highlight'])
        self.stdscr.addstr(1, 0, "═" * self.width)
        self.stdscr.attroff(self.colors['highlight'])

    def draw_box(self, y, x, height, width, title=""):
        # Clear the area
        for i in range(height):
            self.stdscr.addstr(y + i, x, " " * width)

        # Draw bold top bar with reversed highlight and centered title
        if title:
            title_text = f" {title.upper()} "
            title_x = x + (width - len(title_text)) // 2
            self.stdscr.attron(self.colors['highlight'] | curses.A_BOLD | curses.A_REVERSE)
            self.stdscr.addstr(y, x, " " * width)
            self.stdscr.addstr(y, title_x, title_text)
            self.stdscr.attroff(self.colors['highlight'] | curses.A_BOLD | curses.A_REVERSE)

        # Bold underline for separation
        if height > 2:
            self.stdscr.attron(curses.A_BOLD)
            self.stdscr.addstr(y + 1, x, "═" * width)
            self.stdscr.attroff(curses.A_BOLD)

    def draw_progress_bar(self, y, x, width, progress, title="", color='info'):
        """
        Draw a progress bar at position (y, x).
        
        Args:
            y, x   : Position to draw
            width  : Total width of the bar including borders
            progress : Float between 0.0 and 1.0
            title  : Optional title drawn above the bar
            color  : Color key from self.colors
        """
        # Clamp progress to [0, 1]
        progress = max(0.0, min(1.0, progress))

        # Ensure minimum width so percentage fits
        if width < 6:
            width = 6

        inner_width = width - 2  # account for [ ]
        filled = int(progress * inner_width)
        bar = "█" * filled + "░" * (inner_width - filled)

        # Draw title (if any)
        if title:
            self.stdscr.addstr(y - 1, x, title[:width])

        # Draw bar
        self.stdscr.attron(self.colors[color])
        self.stdscr.addstr(y, x, f"[{bar}]")
        self.stdscr.attroff(self.colors[color])

        # Draw percentage (right-aligned)
        percentage = f"{progress * 100:.1f}%"
        perc_x = max(x + width - len(percentage), x + 1)  # avoid overlap
        self.stdscr.addstr(y, perc_x, percentage)


    def print_colored(self, y, x, text, color='normal', max_width=None):
        if max_width:
            text = text[:max_width]

        if y >= 0 and y < self.height and x >= 0 and x + len(text) <= self.width:
            try:
                self.stdscr.attron(self.colors[color])
                self.stdscr.addstr(y, x, text)
                self.stdscr.attroff(self.colors[color])
            except curses.error:
                pass

    def get_input(self, y, x, prompt, color='info'):
        curses.curs_set(1)
        self.print_colored(y, x, prompt, color)
        self.stdscr.refresh()

        curses.echo()
        try:
            input_str = self.stdscr.getstr(y, x + len(prompt)).decode('utf-8')
        except:
            input_str = ""
        curses.noecho()
        curses.curs_set(0)

        return input_str

    def get_single_key(self, y, x, prompt, valid_keys=None, color='info'):
        """
        Get a single keypress without requiring Enter.

        Args:
            y, x       : Position to display the prompt
            prompt     : Text to show before waiting for input
            valid_keys : Optional list/set of accepted characters (printable ASCII only)
            color      : Color key from self.colors
        Returns:
            str representing the key pressed, e.g. "a", "1", "ESC", "ENTER"
        """
        # Print prompt
        self.print_colored(y, x, prompt, color)
        self.stdscr.refresh()

        # --- Clear input buffer ---
        self.stdscr.timeout(10)  # non-blocking
        while self.stdscr.getch() != -1:
            pass
        self.stdscr.timeout(-1)  # back to blocking

        while True:
            key = self.stdscr.getch()
            if key == -1:
                continue  # shouldn't happen in blocking mode, but safe

            # Printable ASCII
            if 32 <= key <= 126:
                char = chr(key)
                if valid_keys is None or char in valid_keys:
                    return char
                else:
                    # Optional: give user feedback for invalid key
                    curses.flash()
                    continue

            # Special keys
            if key in (10, 13):      # Enter (LF or CR)
                return "ENTER"
            elif key == 27:          # Escape
                return "ESC"
            elif key in (curses.KEY_BACKSPACE, 127):
                return "BACKSPACE"
            elif key == curses.KEY_DC:
                return "DELETE"
            elif key == curses.KEY_UP:
                return "UP"
            elif key == curses.KEY_DOWN:
                return "DOWN"
            elif key == curses.KEY_LEFT:
                return "LEFT"
            elif key == curses.KEY_RIGHT:
                return "RIGHT"
            # (expand if you want TAB, F1..F12, etc.)


    def show_message(self, message, color='info', duration=2):
        """
        Display a temporary message at the bottom of the screen.

        Args:
            message  : Text to display
            color    : Color key from self.colors
            duration : Seconds to display (0 = persistent until cleared)
        """
        msg_y = self.height - 3

        # Clear the line before drawing
        self.stdscr.move(msg_y, 0)
        self.stdscr.clrtoeol()

        # Truncate if message is wider than screen
        max_width = self.width - 4
        display_msg = message[:max_width]

        # Print colored message
        self.print_colored(msg_y, 2, display_msg, color)
        self.stdscr.refresh()

        # Auto-clear after duration
        if duration > 0:
            # Use non-blocking delay so UI doesn't freeze
            end_time = time.time() + duration
            while time.time() < end_time:
                time.sleep(0.05)  # lightweight check loop

            self.stdscr.move(msg_y, 0)
            self.stdscr.clrtoeol()
            self.stdscr.refresh()