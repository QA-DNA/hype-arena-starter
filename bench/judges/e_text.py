import numpy as np
from scipy.sparse import hstack, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_predict, StratifiedKFold

C = 0.5


def _fact_tokens(r):
    t = []
    for f in r["facts"]:
        v = f["value"]
        t += [f"S_{f['subject']}", f"A_{f['attribute']}", f"K_{v['kind']}", f"O_{v.get('op')}",
              f"AK_{f['attribute']}_{v['kind']}_{v.get('op')}"]
    return " ".join(x.replace(" ", "_") for x in t)


def _dense(rows):
    return csr_matrix(np.array([[len(r["facts"]), len(r["text"]) / 100, r["idx"] / 2000,
                                 int(r["date"][:4]) - 2025 + int(r["date"][5:7]) / 12] for r in rows]))


class Judge:
    """Text-cue logistic regression (word+char tf-idf, fact tokens, dense row features), Platt-calibrated out-of-fold."""
    name = "e_text"

    def _X(self, rows, fit=False):
        T = [r["text"] for r in rows]; F = [_fact_tokens(r) for r in rows]
        if fit:
            self.v = [TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                      TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True, max_features=30000),
                      TfidfVectorizer(token_pattern=r"\S+", lowercase=False, min_df=2)]
            ms = [self.v[0].fit_transform(T), self.v[1].fit_transform(T), self.v[2].fit_transform(F)]
        else:
            ms = [self.v[0].transform(T), self.v[1].transform(T), self.v[2].transform(F)]
        return hstack(ms + [_dense(rows)]).tocsr()

    def fit(self, train, unlabelled):
        tr = [r for r in train if r["label"] in ("true", "false")]
        y = np.array([r["label"] == "true" for r in tr])
        X = self._X(tr, fit=True)
        self.m = LogisticRegression(C=C, max_iter=2000)
        oof = cross_val_predict(self.m, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0), method="decision_function")
        self.cal = LogisticRegression(C=1e6).fit(oof[:, None], y)  # Platt
        self.m.fit(X, y)

    def predict(self, rows):
        s = self.m.decision_function(self._X(rows))
        return self.cal.predict_proba(s[:, None])[:, 1].tolist()


def text_features(rows_train, rows):
    """Stacking feature: p(true) per row of `rows` from a model fit on `rows_train`. For OOF on train, call per fold."""
    j = Judge(); j.fit(rows_train, rows)
    return np.array(j.predict(rows))
