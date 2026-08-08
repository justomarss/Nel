from dataclasses import dataclass
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.svm import LinearSVC

from .features import FeatureContext, build_feature_text
from .rejection import safety_accept


@dataclass(frozen=True)
class Prediction:
    intent: str | None
    top_score: float
    margin: float
    rejected: bool


class LocalUnderstandingClassifier:
    def __init__(self, *, word_ngram_range=(1, 2), char_ngram_range=(3, 5), c=1.0):
        self.config = {"word_ngram_range": word_ngram_range, "char_ngram_range": char_ngram_range, "c": c}
        self.features = FeatureUnion((
            ("word", TfidfVectorizer(ngram_range=word_ngram_range, sublinear_tf=True, min_df=1)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=char_ngram_range, sublinear_tf=True, min_df=1)),
        ))
        self.model = LinearSVC(C=c)
        self.thresholds = {}
        self.margin_thresholds = {}

    def fit(self, contexts, labels):
        self.model.fit(self.features.fit_transform([build_feature_text(item) for item in contexts]), labels)
        return self

    def predict_one(self, context: FeatureContext) -> Prediction:
        scores = self.model.decision_function(self.features.transform([build_feature_text(context)]))[0]
        order = np.argsort(scores)
        index = int(order[-1]); label = self.model.classes_[index]
        top = float(scores[index]); margin = float(top - scores[order[-2]])
        rejected = (top < self.thresholds.get(label, float("-inf")) or
                    margin < self.margin_thresholds.get(label, 0.0) or
                    not safety_accept(label, context.current))
        return Prediction(None if rejected else label, top, margin, rejected)
