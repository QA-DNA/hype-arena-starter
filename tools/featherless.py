"""Build-time client for Featherless (OpenAI-compatible). NEVER used by the submitted system (offline, no LLM allowed there).

Every call is priced from the model's published per-token rate, logged to tasks/llm_usage.jsonl (no key, no prompt text),
and refused once the running total reaches the cap in tasks/llm_budget.json (default 15 USD). Key: FEATHERLESS_API_KEY in .env.
    from tools.featherless import chat;  text = chat("meta-llama/Meta-Llama-3.1-8B-Instruct", [{"role":"user","content":"hi"}], purpose="test")
"""
import json, os, threading, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "tasks", "llm_usage.jsonl")
BUDGET = os.path.join(ROOT, "tasks", "llm_budget.json")
BASE = "https://api.featherless.ai/v1"
_lock = threading.Lock()
_prices = {}


class BudgetExceeded(RuntimeError):
    pass


def _key():
    for l in open(os.path.join(ROOT, ".env")):
        if l.startswith("FEATHERLESS_API_KEY="):
            return l.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("FEATHERLESS_API_KEY missing in .env")


def _req(path, body=None, auth=True):
    h = {"User-Agent": "hype-arena/0.1", "Content-Type": "application/json"}
    if auth:
        h["Authorization"] = "Bearer " + _key()
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=h)
    return json.load(urllib.request.urlopen(r, timeout=180))


def price(model):
    if not _prices:
        for m in _req("/models", auth=False)["data"]:
            _prices[m["id"]] = (float(m["pricing"]["prompt"]), float(m["pricing"]["completion"]))
    return _prices[model]


def spent():
    if not os.path.exists(LOG):
        return 0.0
    return sum(json.loads(l)["usd"] for l in open(LOG) if l.strip())


def cap():
    if os.path.exists(BUDGET):
        return float(json.load(open(BUDGET))["cap_usd"])
    json.dump({"cap_usd": 15.0}, open(BUDGET, "w"))
    return 15.0


def chat(model, messages, max_tokens=300, temperature=0.0, purpose="", retries=3):
    """Returns the reply text. Reserves a worst-case cost first, so parallel callers cannot overshoot the cap."""
    pi, po = price(model)
    est_in = sum(len(m["content"]) for m in messages) / 3.0           # generous: 3 chars per token
    worst = est_in * pi + max_tokens * po
    with _lock:
        if spent() + worst > cap():
            raise BudgetExceeded(f"spent ${spent():.3f}, cap ${cap():.2f}")
    for a in range(retries):
        try:
            d = _req("/chat/completions", {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature})
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and a < retries - 1:
                time.sleep(2 ** (a + 1)); continue
            raise RuntimeError(f"HTTP {e.code}: {e.read()[:200]!r}")
    u = d.get("usage", {})
    usd = u.get("prompt_tokens", est_in) * pi + u.get("completion_tokens", max_tokens) * po
    with _lock:
        with open(LOG, "a") as f:
            f.write(json.dumps({"t": int(time.time()), "model": model, "purpose": purpose, "in": u.get("prompt_tokens"),
                                "out": u.get("completion_tokens"), "usd": usd}) + "\n")
    return d["choices"][0]["message"]["content"]
