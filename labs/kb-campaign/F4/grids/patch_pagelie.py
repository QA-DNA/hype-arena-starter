"""Patch (apply between runs): page_lie plugin uses soft evidence only (matches test pages, which are never
labelled); the label-observing version stays available as page_lie_lab."""
p = __file__.rsplit("/", 2)[0] + "/f4graph.py"
s = open(p).read()
rep = [
("def page_em(world, q_fact, iters=40):", "def page_em(world, q_fact, iters=40, labels=True):"),
("    lab = world.labelled & np.isin(world.label, [\"true\", \"false\"])\n    base =",
 "    lab0 = world.labelled & np.isin(world.label, [\"true\", \"false\"])\n    lab = lab0 if labels else np.zeros(world.n, bool)\n    base ="),
("    base = float(np.clip(np.mean(world.label[lab] == \"false\") if lab.any() else 0.15, 0.02, 0.5))",
 "    base = float(np.clip(np.mean(world.label[lab0] == \"false\") if lab0.any() else 0.15, 0.02, 0.5))"),
("    use = (lab | (~world.labelled & has)).astype(float)", "    use = (lab | (~lab & has)).astype(float)"),
('''def page_lie(world, role=None):
    """3 columns per fact: P(page lies | other rows of the page), expected page false rate, log lift over base."""
    q = 1 - _base(world, role)[:, 6]
    post, rate, prm = page_em(world, q)''',
'''def page_lie(world, role=None, labels=False):
    """3 columns per fact: P(page lies | other rows of the page), expected page false rate, log lift over base.
    Soft evidence only (labels=False): every row speaks through its propagated (out-of-fold) fact scores, as on a
    test page, which is never labelled."""
    q = 1 - _base(world, role)[:, 6]
    post, rate, prm = page_em(world, q, labels=labels)'''),
('''def blame_feats(world, role=None):''', '''def page_lie_lab(world, role=None):
    """page_lie with the labelled rows of the page observed (train/test mismatch: kept for the comparison)."""
    return page_lie(world, role, labels=True)


def blame_feats(world, role=None):'''),
]
rep.append(("            post, rate, prm = page_em(world, 1 - pt)", "            post, rate, prm = page_em(world, 1 - pt, labels=False)"))
for a, b in rep:
    assert a in s, a
    s = s.replace(a, b)
open(p, "w").write(s)
print("patched")
