from dataclasses import dataclass

from .features import FeatureContext


@dataclass
class ShadowLocalUnderstanding:
    classifier: object
    last_prediction: object = None

    def predict(self, current, *, previous_user="", previous_assistant="", previous_kind="none", has_incomplete_exchange=False):
        self.last_prediction = self.classifier.predict_one(FeatureContext(current, previous_user, previous_assistant, previous_kind, has_incomplete_exchange))
        return self.last_prediction
