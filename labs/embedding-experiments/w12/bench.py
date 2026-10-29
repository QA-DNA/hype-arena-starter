"""VERIDYCT speed bench, run inside the competition-style container (read-only root, /tmp tmpfs 128m, /output mount).
Driver mode (default): one child process per model so ru_maxrss is per model; results -> /output/bench.json after each model.
Child mode: --child KEY. Workload: the 1,897 practice texts tiled to N, shuffled (seed 0); pairs = (text, other text)."""
import argparse, csv, json, os, random, resource, subprocess, sys, time
from importlib import metadata

T_START = time.time()
THREADS = int(os.environ.get('OMP_NUM_THREADS', '2'))
BS = 32
MODELS = {  # key (= /app/models/<key>) -> (requested HF id, kind); cheapest first so a cut run keeps the most results
    'potion-base-8M': ('minishlab/potion-base-8M', 'static'),
    'static-similarity-mrl-multilingual-v1': ('sentence-transformers/static-similarity-mrl-multilingual-v1', 'st'),
    'all-MiniLM-L6-v2': ('sentence-transformers/all-MiniLM-L6-v2', 'st'),
    'mxbai-embed-xsmall-v1': ('mixedbread-ai/mxbai-embed-xsmall-v1', 'st'),
    'all-MiniLM-L12-v2': ('sentence-transformers/all-MiniLM-L12-v2', 'st'),
    'bge-small-en-v1.5': ('BAAI/bge-small-en-v1.5', 'st'),
    'ms-marco-MiniLM-L-6-v2': ('cross-encoder/ms-marco-MiniLM-L-6-v2', 'ce'),
    'nli-deberta-v3-xsmall': ('cross-encoder/nli-deberta-v3-xsmall', 'ce'),
}

def log(*a): print(f'[{time.time() - T_START:7.1f}s]', *a, file=sys.stderr, flush=True)
def rd(path):
    try: return open(path).read().strip()
    except OSError: return None
def rss_mb(peak=True):
    if peak: return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # KB on Linux
    return next(int(l.split()[1]) for l in open('/proc/self/status') if l.startswith('VmRSS:')) / 1024
def cg_stat():
    return {k: int(v) for k, _, v in (l.partition(' ') for l in (rd('/sys/fs/cgroup/cpu.stat') or '').splitlines())}
def cpu_model():
    return next((l.split(':', 1)[1].strip() for l in open('/proc/cpuinfo') if l.startswith('model name')), None)

def workload(n):
    with open('/app/practice.csv', newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    base = [r['text'] for r in rows]
    texts = (base * (n // len(base) + 1))[:n]
    rng = random.Random(0)
    rng.shuffle(texts)
    other = texts[:]
    rng.shuffle(other)
    for i in range(n):  # a pair is two different texts
        while other[i] == texts[i]:
            other[i] = base[rng.randrange(len(base))]
    return rows, base, texts, list(zip(texts, other))

def tok_stats(fn):  # best effort: token-length mean/p95/max, only to explain throughput
    try:
        L = sorted(len(x) for x in fn()['input_ids'])
        return dict(mean=round(sum(L) / len(L), 2), p95=L[int(.95 * len(L))], max=L[-1])
    except Exception as e:
        return f'n/a ({type(e).__name__})'

# ---------------------------------------------------------------- child: one model
def child(key, n):
    import numpy as np
    hf_id, kind = MODELS[key]
    path = f'/app/models/{key}'
    _, base, texts, pairs = workload(n)
    r = dict(key=key, hf_id=hf_id, kind=kind, n=n, batch=BS, omp_env=os.environ.get('OMP_NUM_THREADS'))
    if kind != 'static':  # model2vec is numpy-only: keep torch out of its RSS
        import torch
        torch.set_num_threads(THREADS)
        r.update(torch_threads=torch.get_num_threads(), torch_interop_threads=torch.get_num_interop_threads(), torch=torch.__version__, parallel_info=torch.__config__.parallel_info())
    r['rss_after_imports_mb'] = rss_mb(False)
    log(f'{key}: start torch_threads={r.get("torch_threads")}')
    t0 = time.perf_counter()
    if kind == 'static':
        from model2vec import StaticModel
        m = StaticModel.from_pretrained(path)
        r['dtype_loaded'] = str(m.embedding.dtype)
        if m.embedding.dtype != np.float32: m.embedding = m.embedding.astype(np.float32)
        r['params'], r['dim'] = int(m.embedding.size), int(m.embedding.shape[1])
        fn = lambda xs: m.encode(xs, batch_size=BS, show_progress_bar=False, use_multiprocessing=False)  # no process pool: 2-CPU box
        r['tokens'] = tok_stats(lambda: dict(input_ids=m.tokenize(base)))
    elif kind == 'st':
        from sentence_transformers import SentenceTransformer
        m = SentenceTransformer(path, device='cpu')
        r['dtype_loaded'] = str(next(m.parameters()).dtype)
        m.float()
        r['params'], r['dim'], r['max_seq_length'] = sum(p.numel() for p in m.parameters()), m.get_sentence_embedding_dimension(), getattr(m, 'max_seq_length', None)
        fn = lambda xs: m.encode(xs, batch_size=BS, show_progress_bar=False, convert_to_numpy=True)
        r['tokens'] = tok_stats(lambda: m.tokenizer(base))
    else:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(path)
        m = AutoModelForSequenceClassification.from_pretrained(path)
        r['dtype_loaded'] = str(next(m.parameters()).dtype)
        m = m.float().eval()
        r['params'], r['dim'] = sum(p.numel() for p in m.parameters()), int(m.config.num_labels)
        def fn(batch):
            enc = tok([a for a, _ in batch], [b for _, b in batch], padding=True, truncation=True, max_length=512, return_tensors='pt')
            with torch.inference_mode():
                return m(**enc).logits.float().numpy()
        r['tokens'] = tok_stats(lambda: tok([a for a, _ in pairs[:2000]], [b for _, b in pairs[:2000]]))
    r['load_s'] = time.perf_counter() - t0
    r['rss_after_load_mb'] = rss_mb(False)
    work = sorted(pairs if kind == 'ce' else texts, key=(lambda p: -(len(p[0]) + len(p[1]))) if kind == 'ce' else (lambda s: -len(s)))
    batches = [work[i:i + BS] for i in range(0, len(work), BS)]
    t = time.perf_counter(); fn(batches[0]); r['warmup_s'] = time.perf_counter() - t  # longest batch, excluded from the timed pass
    c0, p0, w0, marks = cg_stat(), time.process_time(), time.perf_counter(), []
    step = max(1, len(batches) // 10)
    for i, b in enumerate(batches):
        fn(b)
        if (i + 1) % step == 0 or i + 1 == len(batches):
            marks.append(round(time.perf_counter() - w0, 2)); log(f'{key}: {i + 1}/{len(batches)} batches {marks[-1]}s')
    wall, cpu, c1 = time.perf_counter() - w0, time.process_time() - p0, cg_stat()
    r.update(run_s=wall, items_per_s=n / wall, cpu_util=cpu / wall, progress_s=marks, peak_rss_mb=rss_mb(),
             nr_throttled=c1.get('nr_throttled', 0) - c0.get('nr_throttled', 0), throttled_s=(c1.get('throttled_usec', 0) - c0.get('throttled_usec', 0)) / 1e6)
    dl = os.environ.get('ARENA_DEADLINE'); r['deadline_left_s'] = int(dl) - time.time() if dl else None
    print('RESULT ' + json.dumps(r), flush=True)

# ---------------------------------------------------------------- child: TF-IDF + LinearSVC + LSA
def tfidf_child(n):
    import warnings; warnings.filterwarnings('ignore')
    import numpy as np
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import make_union
    from sklearn.svm import LinearSVC
    rows, base, texts, _ = workload(n)
    attr = [json.loads(r['form'])[0]['attribute'] for r in rows]  # first fact's attribute, all 1,897 rows
    truth = [r['label'] for r in rows]
    def T(f):
        t = time.perf_counter(); out = f(); return out, time.perf_counter() - t
    r = dict(key='tfidf', n=n, n_train=len(base), attr_classes=len(set(attr)), rss_after_imports_mb=rss_mb(False))
    u = make_union(TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 5)), TfidfVectorizer(ngram_range=(1, 2)))  # as harness._tfidf
    Xtr, r['vec_fit_s'] = T(lambda: u.fit_transform(base))
    r['n_features'] = Xtr.shape[1]
    svc, r['svc_attr_fit_s'] = T(lambda: LinearSVC(C=3).fit(Xtr, attr))
    Xte, r['transform_20k_s'] = T(lambda: u.transform(texts))
    _, r['svc_attr_predict_20k_s'] = T(lambda: svc.predict(Xte))
    svc3, r['svc_truth3_fit_s'] = T(lambda: LinearSVC(C=3).fit(Xtr, truth))
    _, r['svc_truth3_predict_20k_s'] = T(lambda: svc3.predict(Xte))
    svd, r['lsa300_fit_s'] = T(lambda: TruncatedSVD(300, random_state=0).fit(Xtr))
    Z, r['lsa300_transform_20k_s'] = T(lambda: svd.transform(Xte))
    r['lsa_shape'] = list(Z.shape)
    r['attr_pipeline_total_s'] = r['vec_fit_s'] + r['svc_attr_fit_s'] + r['transform_20k_s'] + r['svc_attr_predict_20k_s']
    r['lsa_pipeline_total_s'] = r['vec_fit_s'] + r['transform_20k_s'] + r['lsa300_fit_s'] + r['lsa300_transform_20k_s']
    r['peak_rss_mb'] = rss_mb()
    print('RESULT ' + json.dumps(r), flush=True)

# ---------------------------------------------------------------- driver
def env_info():
    return dict(cpu_model=cpu_model(), os_cpu_count=os.cpu_count(), affinity_cpus=len(os.sched_getaffinity(0)), uid=os.getuid(),
                cgroup_cpu_max=rd('/sys/fs/cgroup/cpu.max'), cgroup_memory_max=rd('/sys/fs/cgroup/memory.max'), cgroup_swap_max=rd('/sys/fs/cgroup/memory.swap.max'),
                cgroup_pids_max=rd('/sys/fs/cgroup/pids.max'), loadavg_host=rd('/proc/loadavg'), arena_deadline=os.environ.get('ARENA_DEADLINE'),
                threads_env={k: os.environ.get(k) for k in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'RAYON_NUM_THREADS', 'TOKENIZERS_PARALLELISM', 'HF_HUB_OFFLINE')},
                versions={p: metadata.version(p) for p in ('torch', 'transformers', 'sentence-transformers', 'model2vec', 'scikit-learn', 'numpy', 'scipy', 'tokenizers', 'huggingface_hub')},
                python=sys.version.split()[0])

def driver(n, only):
    out_dir = '/output' if os.path.isdir('/output') else '/tmp'
    out = dict(n=n, batch=BS, threads=THREADS, env=env_info(), tfidf=None, models=[])
    log('env', json.dumps(out['env']))
    def flush():
        out['elapsed_s'] = time.time() - T_START
        out['cgroup_memory_peak_mb'] = (int(rd('/sys/fs/cgroup/memory.peak') or 0)) / 2**20
        json.dump(out, open(f'{out_dir}/bench.json.tmp', 'w'), indent=1); os.replace(f'{out_dir}/bench.json.tmp', f'{out_dir}/bench.json')
    def spawn(*args):
        p = subprocess.run([sys.executable, __file__, *args], stdout=subprocess.PIPE, text=True)  # stderr inherited -> docker logs
        line = next((l for l in p.stdout.splitlines() if l.startswith('RESULT ')), None)
        if p.returncode or not line: return dict(key=args[1], error=f'exit {p.returncode}', stdout_tail=p.stdout[-500:])
        return json.loads(line[7:])
    if not only or 'tfidf' in only:
        out['tfidf'] = spawn('--child', 'tfidf', '--n', str(n)); flush(); log('tfidf', json.dumps(out['tfidf']))
    for key in MODELS:
        if only and key not in only: continue
        res = spawn('--child', key, '--n', str(n)); out['models'].append(res); flush()
        log(key, 'ERROR ' + res['error'] if 'error' in res else f'load {res["load_s"]:.1f}s run {res["run_s"]:.1f}s {res["items_per_s"]:.0f}/s peak {res["peak_rss_mb"]:.0f}MB')
    log('done'); flush()

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=20000)
    ap.add_argument('--child')
    ap.add_argument('--only', default='', help='comma list of model keys (and tfidf)')
    a = ap.parse_args()
    if a.child == 'tfidf': tfidf_child(a.n)
    elif a.child: child(a.child, a.n)
    else: driver(a.n, set(filter(None, a.only.split(','))))
