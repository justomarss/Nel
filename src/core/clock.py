import threading
import time


class Clock:

    def __init__(self, interval, callback):
        self.interval = interval
        self.callback = callback
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while self.running:
            time.sleep(self.interval)
            self.callback()

    def stop(self):
        self.running = False