"""Compare baseline vs hidden-gold-deranged predictions (must be identical on every row)."""
import sys, glob, numpy as np
tag = sys.argv[1]
bad = 0; n = 0
for b in sorted(glob.glob(f"out/{tag}-base-*.npz")):
    h = b.replace("-base-", "-hp-")
    x, y = np.load(b), np.load(h)
    same_l = (x["labels"] == y["labels"]).all()
    same_c = np.array_equal(x["conf"], y["conf"], equal_nan=True)
    gold_changed = (x["gold"] != y["gold"]).mean()
    n += 1; bad += not (same_l and same_c)
    print(b.split("/")[-1][len(tag) + 6:-4], "labels identical", same_l, "conf identical", same_c, "share of scored gold changed", round(gold_changed, 3))
print(f"{tag}: {n - bad}/{n} identical")
