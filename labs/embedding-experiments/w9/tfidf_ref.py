"""Reference numbers from the harness itself (TF-IDF), for the report: attr buckets and false-vs-rest."""
import sys; sys.path.insert(0, '/tmp/veridyct-emb/common')
import harness as H; H.set_threads(2)
rows, lex = H.load()
B = H.tfidf_baseline(rows, lex)
print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in B['attr'].items()})
print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in B['false'].items()})
