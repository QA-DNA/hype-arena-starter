"""Emit probe job lines: tag|env|spec|params|track|k|extra"""
import sys, json
spec, params, tag = sys.argv[1], sys.argv[2], sys.argv[3]
R = sys.argv[4]
L = []
for k in range(5): L.append((f"{tag}-base-P80-{k}", "", "P80", k, ""))
for k in range(10): L.append((f"{tag}-base-P10-{k}", "", "P10", k, ""))
for t in ("Sdev-jt", "Sdev-jr"): L.append((f"{tag}-base-{t}", "", t, 0, ""))
for k in range(5): L.append((f"{tag}-hp-P80-{k}", f"KBC_PRACTICE_DIR={R}/hp/P80-{k} KBC_ROOT={R}/hp/root", "P80", k, ""))
for k in range(10): L.append((f"{tag}-hp-P10-{k}", f"KBC_PRACTICE_DIR={R}/hp/P10-{k} KBC_ROOT={R}/hp/root", "P10", k, ""))
for t in ("Sdev-jt", "Sdev-jr"): L.append((f"{tag}-hp-{t}", f"KBC_SUITE_DIR={R}/hp/suite KBC_ROOT={R}/hp/root", t, 0, ""))
for k in range(5): L.append((f"{tag}-sh-P80-{k}", "", "P80", k, "--shuffle 0"))
for k in range(10): L.append((f"{tag}-sh-P10-{k}", "", "P10", k, "--shuffle 0"))
for tg, env, t, k, ex in L:
    print("|".join([tg, env, spec, params, t, str(k), ex]))
