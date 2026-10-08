"""Long tasks run in the background of the local server (ENF-PER-04).

A job runs in a thread; its progress is what it has stored in the project, so a job
stopped with the server (or by an error) is resumed by starting it again: the use
cases are written to continue where they stopped (collections resume after their
last stored page, enrichment skips the references already checked).
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

__all__ = ["BackgroundJobs"]

_LOGGER = logging.getLogger(__name__)


@dataclass
class BackgroundJobs:
    """At most one running job per key; the message of the last failure is kept."""

    _threads: dict[str, threading.Thread] = field(default_factory=dict)
    _errors: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self, key: str, work: Callable[[], object]) -> bool:
        """Start ``work`` unless a job with this key is running; False if it is."""
        with self._lock:
            if self.running(key):
                return False
            self._errors.pop(key, None)

            def run() -> None:
                try:
                    work()
                except Exception as error:  # reported on the page, never raised further
                    _LOGGER.warning("background job %s failed: %s", key, type(error).__name__)
                    with self._lock:
                        self._errors[key] = str(error)

            thread = threading.Thread(target=run, name=f"job-{key}", daemon=True)
            self._threads[key] = thread
            thread.start()
            return True

    def running(self, key: str) -> bool:
        thread = self._threads.get(key)
        return thread is not None and thread.is_alive()

    def keys(self) -> list[str]:
        """Keys of the jobs started so far, oldest first."""
        return list(self._threads)

    def error(self, key: str) -> str | None:
        return self._errors.get(key)

    def wait(self, key: str, timeout: float | None = None) -> None:
        """Wait for a job to end (tests)."""
        thread = self._threads.get(key)
        if thread is not None:
            thread.join(timeout)
