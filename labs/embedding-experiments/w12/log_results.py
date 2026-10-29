"""Turn out2/bench.json (--cpus 2) and out1/bench.json (--cpus 1) into one JSONL 'speed' line per model via the harness ResultWriter."""
import json, os, sys
sys.path.insert(0, '/tmp/veridyct-emb/common'); import harness as H

IMAGE_SIZE_MB = float(sys.argv[1])      # docker image inspect .Size / 1e6
IMAGE_UNPACKED_MB = float(sys.argv[2])  # du of the unpacked rootfs
W = H.ResultWriter(H.results_path('w12'))
FLAGS = ('docker run --platform linux/amd64 --network none --read-only --user 10001:10001 --cpus {c} --memory 6g --memory-swap 6g --pids-limit 256 '
         '--cap-drop ALL --security-opt no-new-privileges --tmpfs /tmp:rw,size=128m,mode=1777 -v out:/output -e ARENA_DEADLINE')
n_lines = 0
for cpus, variant in ((2, 'docker_x86_2cpu'), (1, 'docker_x86_1cpu')):
    p = f'/tmp/veridyct-emb/w12/out{cpus}/bench.json'
    if not os.path.exists(p): continue
    b = json.load(open(p)); env = b['env']
    base = dict(cpu_model=env['cpu_model'], cpus=cpus)
    common_notes = (f'{FLAGS.format(c=cpus)}; threads OMP/MKL={env["threads_env"]["OMP_NUM_THREADS"]}; fp32; bs 32; longest-first; 1 warm-up batch excluded; '
                    f'tokenization included; one child process per model (peak RSS per model); host loadavg at start {env["loadavg_host"].split()[0]}; '
                    f'server also ran the other-cpu-count bench concurrently and a Supabase stack; torch {env["versions"]["torch"]}, transformers {env["versions"]["transformers"]}, '
                    f'sentence-transformers {env["versions"]["sentence-transformers"]}, model2vec {env["versions"]["model2vec"]}')
    for m in b['models']:
        if 'error' in m:
            W.add('w12', m['key'], 'speed', variant, {}, n=b['n'], notes=f'FAILED: {m["error"]} {m.get("stdout_tail", "")[:200]}', **base); n_lines += 1; continue
        k = 'pairs_20k_s' if m['kind'] == 'ce' else 'encode_20k_s'
        metrics = dict(load_s=m['load_s'], **{k: m['run_s']}, items_per_s=m['items_per_s'], peak_rss_mb=m['peak_rss_mb'], image_size_mb=IMAGE_SIZE_MB, **base)
        W.add('w12', m['hf_id'], 'speed', variant, metrics, n=m['n'], notes=common_notes + ('; pairs = random (text, other text); ms-marco repo renamed to cross-encoder/ms-marco-MiniLM-L6-v2' if m['kind'] == 'ce' else '')
              + ('; checkpoint loaded as float16 by sentence-transformers, cast to fp32 before timing' if m.get('dtype_loaded') == 'torch.float16' else ''),
              kind=m['kind'], params=m['params'], dim=m['dim'], threads=m.get('torch_threads') or env['threads_env']['OMP_NUM_THREADS'], batch=m['batch'],
              warmup_s=m['warmup_s'], cpu_util=m['cpu_util'], throttled_s=m['throttled_s'], nr_throttled=m['nr_throttled'], rss_after_imports_mb=m['rss_after_imports_mb'],
              rss_after_load_mb=m['rss_after_load_mb'], tokens=m['tokens'], dtype_loaded=m['dtype_loaded'], image_unpacked_mb=IMAGE_UNPACKED_MB, progress_s=m['progress_s']); n_lines += 1
    t = b['tfidf']
    if t and 'error' not in t:
        svc = dict(vec_fit_s=t['vec_fit_s'], svc_fit_s=t['svc_attr_fit_s'], fit_1897_s=t['vec_fit_s'] + t['svc_attr_fit_s'], transform_20k_s=t['transform_20k_s'],
                   svc_predict_20k_s=t['svc_attr_predict_20k_s'], predict_20k_s=t['transform_20k_s'] + t['svc_attr_predict_20k_s'], total_s=t['attr_pipeline_total_s'],
                   svc3_fit_s=t['svc_truth3_fit_s'], svc3_predict_20k_s=t['svc_truth3_predict_20k_s'], peak_rss_mb=t['peak_rss_mb'], image_size_mb=IMAGE_SIZE_MB, **base)
        W.add('w12', 'tfidf(char_wb2-5+word1-2)+LinearSVC(C=3)', 'speed', variant, svc, n=t['n'], notes=common_notes + f'; fit on 1,897 rows, label = first fact attribute ({t["attr_classes"]} classes, one-vs-rest), {t["n_features"]} features; svc3 = 3-class truth label',
              kind='sklearn', threads=1, n_features=t['n_features'], n_train=t['n_train']); n_lines += 1
        lsa = dict(vec_fit_s=t['vec_fit_s'], lsa_fit_s=t['lsa300_fit_s'], tfidf_transform_20k_s=t['transform_20k_s'], lsa_transform_20k_s=t['lsa300_transform_20k_s'],
                   total_transform_20k_s=t['transform_20k_s'] + t['lsa300_transform_20k_s'], total_s=t['lsa_pipeline_total_s'], peak_rss_mb=t['peak_rss_mb'], image_size_mb=IMAGE_SIZE_MB, **base)
        W.add('w12', 'tfidf(char_wb2-5+word1-2)+LSA300', 'speed', variant, lsa, n=t['n'], notes=common_notes + '; TruncatedSVD(300) fit on the 1,897 TF-IDF rows, transform of 20,000',
              kind='sklearn', threads=1, n_features=t['n_features'], lsa_shape=t['lsa_shape']); n_lines += 1
print('wrote', n_lines, 'lines to', H.results_path('w12'))

# ---- two extra single-model checks, logged under their own variant names so the main variants stay clean
for d, variant, note in (('out-recheck', 'docker_x86_2cpu_standalone_recheck', 'standalone re-run (no other bench container running) to bound cross-talk with the concurrent 1-CPU run; compare with variant docker_x86_2cpu'),
                         ('out-diag16', 'docker_x86_2cpu_16threads_diag', 'DIAGNOSTIC: OMP/MKL threads=16 under --cpus 2 (what a library that sizes its pool from the 16 visible CPUs would do); n=2000 only; CFS throttling dominates')):
    p = f'/tmp/veridyct-emb/w12/{d}/bench.json'
    b = json.load(open(p)); env = b['env']; m = b['models'][0]
    metrics = dict(load_s=m['load_s'], **{f'encode_{b["n"]}_s': m['run_s']}, items_per_s=m['items_per_s'], peak_rss_mb=m['peak_rss_mb'], image_size_mb=IMAGE_SIZE_MB, cpu_model=env['cpu_model'], cpus=2)
    W.add('w12', m['hf_id'], 'speed', variant, metrics, n=m['n'], notes=note + f'; torch threads {m["torch_threads"]}; host loadavg at start {env["loadavg_host"].split()[0]}',
          kind=m['kind'], params=m['params'], dim=m['dim'], threads=m['torch_threads'], batch=m['batch'], warmup_s=m['warmup_s'], cpu_util=m['cpu_util'],
          throttled_s=m['throttled_s'], nr_throttled=m['nr_throttled'], image_unpacked_mb=IMAGE_UNPACKED_MB); n_lines += 1
print('wrote', n_lines, 'lines total')
