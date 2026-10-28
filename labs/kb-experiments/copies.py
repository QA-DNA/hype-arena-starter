"""Synthetic copied evidence for the v12 stress test. Used only through the KB_COPY env hook in exp.py.
Scenarios: lie / control (pre-declared) and mixed (post-hoc) are TELL-CONFOUNDED: copies also exist for rows on
labelled pages, so in training "has a duplicate" correlates with the class (lie, control: perfectly; mixed: 50% false among
copied rows vs 8.6% elsewhere). The tell-free scenarios are hlie / hctrl, built per R10 split ('hlie:<seed>'): copies only
of rows on pages HIDDEN in that split, so no labelled row has a copy."""
import datetime as dt, random

OFFSETS = (1, 7, 30)  # days after the original row
SEED = 12345


def augment(rows, scen):
    """Append 3 copies (own new page each, same text/facts, date +1/+7/+30) of each false row ('lie') or of an
    equally sized random sample of true rows ('control'). Copies carry no label and are flagged copy=True."""
    scen, _, seed = scen.partition(':')
    nfalse = sum(r['label'] == 'false' for r in rows)
    if scen == 'lie':
        src = [r for r in rows if r['label'] == 'false']
    elif scen == 'control':
        src = random.Random(SEED).sample([r for r in rows if r['label'] == 'true'], nfalse)
    elif scen == 'mixed':  # post-hoc: half the false rows and an equal number of true rows, 50% false among copied rows vs 8.6% elsewhere, so it still carries a tell
        rng = random.Random(SEED); h = nfalse // 2
        src = rng.sample([r for r in rows if r['label'] == 'false'], h) + rng.sample([r for r in rows if r['label'] == 'true'], h)
        rng.shuffle(src)
    elif scen in ('hlie', 'hctrl'):  # same pages as exp.splits R10 seed `seed`: lab = Random(seed).sample(range(NP), round(0.1 NP))
        np0 = max(r['page'] for r in rows) + 1
        hidden = set(range(np0)) - set(random.Random(int(seed)).sample(range(np0), max(1, round(0.1 * np0))))
        hf = [r for r in rows if r['label'] == 'false' and r['page'] in hidden]
        src = hf if scen == 'hlie' else random.Random(SEED).sample([r for r in rows if r['label'] == 'true' and r['page'] in hidden], len(hf))
    else:
        raise ValueError(scen)
    page = max(r['page'] for r in rows) + 1
    out = list(rows)
    for r in src:
        for d in OFFSETS:
            date = r['date'] + d
            out.append(dict(id='cp%d-%s' % (d, r['id']), text=r['text'], date=date,
                            datestr=dt.date.fromordinal(date).isoformat(), label='', page=page,
                            facts=r['facts'], copy=True))
            page += 1
    assert len(out) - len(rows) == 3 * len(src)
    return out
