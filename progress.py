import time
from datetime import timedelta

class ProgressTracker:
    def __init__(self, total, description="Progress", ui=None):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.time()
        self.last_update = 0
        self.ui = ui
        self.completed = False

    def update(self, current):
        self.current = current
        now = time.time()

        if now - self.last_update < 0.05 and current < self.total:
            return
        self.last_update = now

        if self.ui and self.ui.stdscr:
            self.draw_progress()

        if current >= self.total:
            self.completed = True

    def draw_progress(self):
        if not self.ui or not self.ui.stdscr:
            return

        try:
            progress = self.current / self.total if self.total > 0 else 0
            elapsed = time.time() - self.start_time

            if elapsed > 0 and self.current > 0:
                speed = self.current / elapsed
                eta_seconds = (self.total - self.current) / speed if speed > 0 else float('inf')
                eta = str(timedelta(seconds=int(eta_seconds)))

                if speed > 1024*1024:
                    speed_str = f"{speed/(1024*1024):.1f} MB/s"
                elif speed > 1024:
                    speed_str = f"{speed/1024:.1f} KB/s"
                else:
                    speed_str = f"{speed:.1f} B/s"
            else:
                speed_str = "0 B/s"
                eta = "∞"

            current_str = self.format_size(self.current)
            total_str = self.format_size(self.total)

            bar_width = min(60, self.ui.width - 20)
            bar_y = self.ui.height // 2

            for i in range(5):
                self.ui.stdscr.move(bar_y - 2 + i, 0)
                self.ui.stdscr.clrtoeol()

            self.ui.print_colored(bar_y - 2, 2, self.description, 'highlight')
            self.ui.draw_progress_bar(bar_y, 2, bar_width, progress, '', 'success')
            stats = f"{current_str}/{total_str} | {speed_str} | ETA: {eta}"
            self.ui.print_colored(bar_y + 1, 2, stats, 'info')
            self.ui.stdscr.refresh()

        except Exception:
            pass

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
