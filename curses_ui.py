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

    def draw_header(self, title):
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
        filled = int(progress * (width - 2))
        bar = "█" * filled + "░" * (width - 2 - filled)

        self.stdscr.attron(self.colors[color])
        self.stdscr.addstr(y, x, f"[{bar}]")
        self.stdscr.attroff(self.colors[color])

        if title:
            self.stdscr.addstr(y - 1, x, title[:width])

        percentage = f"{progress * 100:.1f}%"
        perc_x = x + width - len(percentage)
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

    def show_message(self, message, color='info', duration=2):
        msg_y = self.height - 3
        self.stdscr.move(msg_y, 0)
        self.stdscr.clrtoeol()
        self.print_colored(msg_y, 2, message, color)
        self.stdscr.refresh()
        if duration > 0:
            time.sleep(duration)
