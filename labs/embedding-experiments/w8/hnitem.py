import json, sys, urllib.request, re, html
def strip(t): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',t or '')))
def walk(n, depth, out, maxc):
    if len(out)>=maxc: return
    if n.get('text'):
        out.append(('  '*depth)+f"[{n.get('author')}] "+strip(n['text'])[:700])
    for c in n.get('children',[]): walk(c, depth+1, out, maxc)
for iid in sys.argv[2:]:
    j=json.load(urllib.request.urlopen(f"https://hn.algolia.com/api/v1/items/{iid}", timeout=30))
    print("=====", j.get('title'), "| points", j.get('points'), "| id", iid)
    out=[]; walk(j,0,out,int(sys.argv[1]))
    print("\n".join(out))
