"""D: near-duplicate retrieval + label propagation from text and date only (ignores r['facts'])."""
import re, datetime
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import HistGradientBoostingClassifier
from scipy.sparse import hstack

NUM = re.compile(r"\d[\d.,]*")
CAP = re.compile(r"(?<!^)(?<![.!?] )\b[A-Z][a-zA-Z]+")
K = 4
NF = 6 * K + 8


def day(d):
    return datetime.date.fromisoformat(d[:10]).toordinal()


def toks(t):
    nums = {n.rstrip(".,") for n in NUM.findall(t)}
    return nums, {c.lower() for c in CAP.findall(t)}


class Judge:
    name = "d_knn"

    def fit(self, train, unlabelled):
        tr = [r for r in train if r["label"] in ("true", "false")]
        self.tr = tr
        self.y = np.array([r["label"] == "true" for r in tr], float)
        self.days = np.array([day(r["date"]) for r in tr])
        self.nt = [toks(r["text"]) for r in tr]
        self.dates = np.array([r["date"] for r in tr])
        self.w = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), token_pattern=r"[A-Za-z0-9.%$]+", sublinear_tf=True)
        self.c = TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2)
        txt = [r["text"] for r in tr] + [r["text"] for r in unlabelled]
        self.w.fit(txt); self.c.fit(txt)
        self.X = self.mat([r["text"] for r in tr])
        # unseen-date regime if held-out dates barely overlap train dates
        td = set(self.dates)
        ud = [r["date"] for r in unlabelled]
        self.excl_same = bool(ud) and np.mean([d in td for d in ud]) < 0.3
        F = self.feats(tr, self.X, self_idx=True)
        self.m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.03, max_iter=120,
                                                min_samples_leaf=60, l2_regularization=10.0, random_state=0)
        self.m.fit(F, self.y)

    def mat(self, txt):
        a, b = self.w.transform(txt), self.c.transform(txt)
        from sklearn.preprocessing import normalize
        return normalize(hstack([a, b]).tocsr())

    def feats(self, rows, X, self_idx=False):
        S = (X @ self.X.T).toarray()
        out = np.zeros((len(rows), NF))
        for i, r in enumerate(rows):
            s = S[i].copy()
            d0 = day(r["date"])
            if self_idx:
                s[i] = -1
            if self.excl_same:
                s[self.dates == r["date"]] = -1
            top = np.argpartition(-s, K)[:K]
            top = top[np.argsort(-s[top])]
            qn, qc = toks(r["text"])
            f = []
            agree = [0.0, 0.0]; dis = [0.0, 0.0]
            for j in top:
                nn, nc = self.nt[j]
                same = float(nn == qn)
                nj = len(nn | qn)
                jac = len(nn & qn) / nj if nj else 1.0
                cj = len(nc | qc)
                cjac = len(nc & qc) / cj if cj else 1.0
                lab = self.y[j] * 2 - 1
                gap = abs(self.days[j] - d0)
                f += [s[j], same, jac, cjac, lab, np.log1p(gap)]
                if s[j] > 0.5:
                    wgt = s[j] * np.exp(-gap / 90)
                    if same: agree[0] += wgt * lab; agree[1] += wgt
                    else: dis[0] += wgt * lab; dis[1] += wgt
            f += [agree[0], agree[1], dis[0], dis[1], agree[0] / (agree[1] + 1e-6), dis[0] / (dis[1] + 1e-6),
                  s[top[0]], float(len(qn))]
            out[i] = f
        return out

    def predict(self, rows):
        F = self.feats(rows, self.mat([r["text"] for r in rows]))
        self.last_F = F
        return list(np.clip(self.m.predict_proba(F)[:, 1], 0.01, 0.99))
