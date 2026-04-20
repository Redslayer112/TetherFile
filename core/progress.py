import time
from datetime import timedelta
from core import CONFIG
from core.utils import format_size

PROGRESS_UPDATE_INTERVAL = CONFIG['PROGRESS_UPDATE_INTERVAL']
# Bytes-since-last-update throttle: prevents call_from_thread spam on
# fast/large transfers even when the time-based throttle hasn't tripped yet.
PROGRESS_BYTES_INTERVAL = max(1, int(CONFIG.get('PROGRESS_BYTES_INTERVAL', 1024 * 1024)))


class ProgressTracker:
    """Throttled progress tracker for the Textual UI adapter.

    Updates are gated by BOTH a minimum elapsed time AND a minimum number
    of bytes since the last emitted frame, so the UI thread is never
    flooded on multi-GB / many-chunk transfers. The final frame at 100 %
    is always emitted.
    """

    def __init__(self, total, description="Progress", ui=None):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.monotonic()
        self.last_update = 0.0
        self.last_update_bytes = 0
        self.ui = ui
        self.completed = False

    def update(self, current):
        self.current = current

        # Always emit the final frame so the bar lands at 100 %.
        if current < self.total:
            now = time.monotonic()
            if now - self.last_update < PROGRESS_UPDATE_INTERVAL:
                return
            if current - self.last_update_bytes < PROGRESS_BYTES_INTERVAL:
                return
            self.last_update = now
        else:
            self.last_update = time.monotonic()

        self.last_update_bytes = current

        if self.ui is not None:
            self._emit()

        if current >= self.total:
            self.completed = True

    def _emit(self):
        try:
            progress = self.current / self.total if self.total > 0 else 0.0
            elapsed = time.monotonic() - self.start_time

            if elapsed > 0 and self.current > 0:
                speed = self.current / elapsed
                eta_seconds = (self.total - self.current) / speed if speed > 0 else float('inf')
                eta = str(timedelta(seconds=int(eta_seconds))) if eta_seconds != float('inf') else "∞"

                if speed > 1024 * 1024:
                    speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
                elif speed > 1024:
                    speed_str = f"{speed / 1024:.1f} KB/s"
                else:
                    speed_str = f"{speed:.1f} B/s"
            else:
                speed_str = "0 B/s"
                eta = "∞"

            try:
                self.ui.draw_progress_bar(0, 0, 0, progress, '', 'success')
            except Exception:
                pass

            try:
                stats = (
                    f"{self.description} | {format_size(self.current)}/"
                    f"{format_size(self.total)} | {speed_str} | ETA: {eta}"
                )
                self.ui.print_colored(0, 0, stats, 'info')
            except Exception:
                pass
        except Exception:
            pass

    # Backwards-compatible alias (older code paths called draw_progress directly).
    def draw_progress(self):
        self._emit()