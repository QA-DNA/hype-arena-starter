"""Out-of-fold parse = base parser + hype.numeric + hype.booleans. Writes bench/parsed_<split>_nb.json.  python -m bench.combined_parse [date|row]"""
import json, sys, warnings
warnings.filterwarnings("ignore")
from hype import numeric as N, booleans as B
from bench.eval_component import evaluate
from bench import common

kinds = {"quantity", "money", "duration", "percent", "version", "boolean", "name", "date"}
def train(rows, lex): return (N.train(rows, lex), B.train(rows, lex))
def apply(m, test, lex, f, h, allr):
    return B.apply(m[1], test, lex, N.apply(m[0], test, lex, f, h, allr), h, allr)

if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "date"
    new = evaluate("numeric+booleans", train, apply, kinds, split)
    json.dump(new, open(common.PARSED[split].replace(".json", "_nb.json"), "w"))
