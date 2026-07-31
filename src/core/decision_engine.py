from datetime import datetime, timedelta


class DecisionEngine:

    def __init__(self):
        self.last_thought = datetime.now()

    def should_think(self):

        now = datetime.now()

        if now - self.last_thought > timedelta(seconds=30):
            self.last_thought = now
            return True

        return False