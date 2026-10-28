import json, sys, urllib.request, urllib.parse
def get(m):
    u = f"https://huggingface.co/api/models/{m}"
    try:
        with urllib.request.urlopen(u, timeout=20) as r:
            return json.load(r)
    except Exception as e:
        return {'error': str(e)}
for m in sys.argv[1:]:
    j = get(m)
    if 'error' in j:
        print(m, 'ERR', j['error']); continue
    cfg = j.get('config') or {}
    cd = j.get('cardData') or {}
    st = j.get('safetensors') or {}
    tags = j.get('tags') or []
    bm = [t for t in tags if t.startswith('base_model:')]
    cc = 'custom_code' in tags
    print(f"{m} | type={cfg.get('model_type')} | arch={cfg.get('architectures')} | params={st.get('total')} | lic={cd.get('license')} | created={str(j.get('createdAt'))[:10]} | dl={j.get('downloads')} | custom_code={cc} | base={bm}")
