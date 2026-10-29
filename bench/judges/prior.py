class Judge:
    """Everything is true at the training prior."""
    name = "prior"

    def fit(self, train, unlabelled):
        lab = [r["label"] == "true" for r in train if r["label"] in ("true", "false")]
        self.p = sum(lab) / len(lab)

    def predict(self, rows):
        return [self.p] * len(rows)
