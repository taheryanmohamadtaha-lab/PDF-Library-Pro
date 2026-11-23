"""Background tasks so the UI never blocks."""
import logging
import traceback

from PySide6.QtCore import QThread, Signal

log = logging.getLogger("pdflp.workers")


class Task(QThread):
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def cancelled(self) -> bool:
        return self._cancel

    def run(self):
        try:
            res = self.fn(lambda a, b, msg="": self.progress.emit(a, b, msg), self.cancelled)
            self.done.emit(res)
        except Exception as e:
            log.error("task failed: %s", traceback.format_exc())
            self.failed.emit(str(e))
