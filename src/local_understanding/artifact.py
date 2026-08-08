import joblib


def save_artifact(classifier, path, metadata):
    joblib.dump({"classifier": classifier, "metadata": metadata}, path, compress=3)


def load_artifact(path):
    return joblib.load(path)
