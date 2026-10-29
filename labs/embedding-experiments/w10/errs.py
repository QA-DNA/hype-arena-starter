import sys; sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H
import numpy as np, json
rows, lex = H.load(); PR = H.same_key_pairs(rows)
key = sys.argv[1]; P = np.load(f'/tmp/veridyct-emb/w10/probs_conflict_{key}.npy'); pc = P[:, 2]
y = np.array([0 if s else 1 for _, _, s in PR])
fp = [k for k in np.argsort(-pc) if y[k] == 0][:7]; fn = [k for k in np.argsort(pc) if y[k] == 1][:7]
def show(k): i, j, s = PR[k]; print(f'  pc={pc[k]:.3f} same={s} kind={rows[i]["facts"][0]["value"]["kind"]}\n    i: {rows[i]["text"]}  [{json.dumps(rows[i]["facts"][0]["value"])}]\n    j: {rows[j]["text"]}  [{json.dumps(rows[j]["facts"][0]["value"])}]')
print('FALSE POSITIVES (same value, high p_contra)'); [show(k) for k in fp]
print('FALSE NEGATIVES (different value, low p_contra)'); [show(k) for k in fn]
print('share of diff-value pairs with pc<0.5:', float(((pc < .5) & (y == 1)).sum() / (y == 1).sum()), ' same-value pairs with pc>=0.5:', float(((pc >= .5) & (y == 0)).sum() / (y == 0).sum()))
