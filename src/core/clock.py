import logging
import threading


logger = logging.getLogger(__name__)


class Clock:
    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._stop_event.clear()
            self.running = True
            self._thread = threading.Thread(
                target=self.loop,
                name="nel-clock",
                daemon=True,
            )
            self._thread.start()

    def loop(self):
        try:
            while not self._stop_event.wait(self.interval):
                try:
                    self.callback()
                except Exception as exc:
                    logger.error(
                        "Clock callback failed (%s).",
                        type(exc).__name__,
                    )
        finally:
            with self._lock:
                self.running = False
                if self._thread is threading.current_thread():
                    self._thread = None

    def stop(self):
        with self._lock:
            self.running = False
            self._stop_event.set()
            thread = self._thread

        if thread is not None and thread is not threading.current_thread():
            thread.join()

        with self._lock:
            if self._thread is thread:
                self._thread = None
