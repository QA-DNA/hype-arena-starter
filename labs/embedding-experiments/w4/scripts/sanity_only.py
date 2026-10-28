import sys, time; sys.path.insert(0, '/tmp/veridyct-emb/w4/scripts')
import nli_run as N
t = time.time(); S = N.Scorer(sys.argv[1]); print('loaded', round(time.time() - t, 1), 's', S.params_m, 'M', S.lm, flush=True)
t = time.time(); print(S.sanity(), round(time.time() - t, 1), 's')
