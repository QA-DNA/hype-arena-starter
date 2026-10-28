"""Synthetic copied evidence for the v12 stress test. Used only through the KB_COPY env hook in exp.py."""
import datetime as dt, random

OFFSETS = (1, 7, 30)  # days after the original row
SEED = 12345


def augment(rows, scen):
    """Append 3 copies (own new page each, same text/facts, date +1/+7/+30) of each false row ('lie') or of an
    equally sized random sample of true rows ('control'). Copies carry no label and are flagged copy=True."""
    nfalse = sum(r['label'] == 'false' for r in rows)
    if scen == 'lie':
        src = [r for r in rows if r['label'] == 'false']
    elif scen == 'control':
        src = random.Random(SEED).sample([r for r in rows if r['label'] == 'true'], nfalse)
    elif scen == 'mixed':  # post-hoc: half the false rows and an equal number of true rows, so copy presence is not a label tell
        rng = random.Random(SEED); h = nfalse // 2
        src = rng.sample([r for r in rows if r['label'] == 'false'], h) + rng.sample([r for r in rows if r['label'] == 'true'], h)
        rng.shuffle(src)
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
    assert len(out) - len(rows) == 3 * (nfalse if scen != 'mixed' else 2 * (nfalse // 2))
    return out
