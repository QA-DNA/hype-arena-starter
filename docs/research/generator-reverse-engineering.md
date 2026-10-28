<!-- Measured 2026-10-28 evening on data/practice.csv by an Opus analysis worker; scripts and raw outputs in labs/generator-reverse-engineering. Question: can the organizers' generator be reverse-engineered well enough to label rows near-perfectly? Short answer: the structure yes, the labels no; the label is a function of (key, date, universe), not of the sentence. -->

# How deterministic is the organizers' generator? Reverse-engineering practice.csv

Data: `practice.csv` (1,897 rows: 1,581 true, 277 false, 39 unsure; 291 pages; 2,402 gold facts in the `form` column),
`lexicon.json` (62 subjects, 13 events). All numbers below come from the scripts in [labs/generator-reverse-engineering](../../labs/generator-reverse-engineering/README.md)
(run each with `python -I <script>`; shared helpers in `rev_common.py`); raw outputs are in
`*_out.txt`. Scripts: `a1_templates.py`, `a2_lies.py`, `a3_unsure.py`, `a3b_voice.py`, `a4_pages.py`, `a5_keys.py`,
`a5b_conflicts.py`, `a5c_timeline.py`, `a6_claims.py`, `hyp.py`.
Gold forms (subject, attribute, typed value) are used wherever the analysis needs a row's fact; the templates use
`w7/values.py` (typed values) and its lexicon entity finder.

## 1. Template inventory (`a1_templates.py`, output `a1_out.txt`, list `templates.txt`)

Templating: gold subject mention -> `<SUBJ>`, other lexicon subject -> `<ENT>`, event -> `<EVENT>`, gold name value -> `<NAME>`,
every typed value values.py reads (not flagged `alt`, booleans skipped since they have no span) -> `<QTY>` `<MONEY>` `<DUR>`
`<PCT>` `<DATE>` `<VER>`. "Loose" adds lower-case, digits -> 0, punctuation dropped, whitespace collapsed. "Slots" keeps only
the placeholder sequence. Good-Turing P(unseen) = N1 / N (singleton templates over rows). Leave-page-out hit = share of rows
whose template also occurs on another page (what a template matcher learned on the other pages would cover).

| Normalisation | distinct | singletons | rows in a template seen >= 2x | Good-Turing P(new row is unseen) | leave-page-out hit |
|---|---|---|---|---|---|
| raw text | 1,879 | 1,863 | 34 | 0.982 | 0.018 |
| placeholder template | 1,782 | 1,696 | 201 | 0.894 | 0.092 |
| loose template | 1,757 | 1,663 | 234 | 0.877 | 0.111 |
| slot signature only | 220 | 119 | 1,778 | 0.063 | 0.937 |

Per attribute (1,467 single-fact rows, 303 attributes): median 4 rows and median 4 distinct placeholder templates per
attribute (mean 4.60 templates); in 267 of 303 attributes every row has its own template (256 under the loose form).
Sharing: 18 placeholder templates carry more than one attribute (47 rows), e.g. `<SUBJ> <VER>` (version, stable_version),
`<QTY> on <SUBJ>` (active_users, business_listings, monthly_active_users), `<SUBJ> serves <QTY>.`; the rest are
attribute-specific because the attribute is said in its own words (`The hinge of <SUBJ> is rated for <QTY>.`).

Top placeholder templates (full list with counts in `templates.txt`): 7 `<SUBJ> costs <MONEY>`; 5 `<SUBJ> <VER>`;
5 `<QTY> on <SUBJ>`; 4 `<SUBJ> has <QTY> each month.`; 4 `<SUBJ> has sold <QTY>`; 4 `<SUBJ> speaks <QTY>.`;
3 each: `<SUBJ> offers <QTY> for <MONEY>.`, `The hinge of <SUBJ> is rated for <QTY>.`, `The battery of the <SUBJ> holds <QTY>.`,
`<SUBJ>: <QTY> at <MONEY>`, `<QTY> supported`, `<SUBJ> <VER> release notes`, `<SUBJ> serves <QTY>.`, `<QTY>.`,
`<QTY> each month`, `<QTY> monthly`, `<SUBJ> costs <MONEY>, or <MONEY> when billed annually.`,
`<SUBJ> replies in <DUR> at the median.`; then 2 each: `<SUBJ> is generally available from <DATE> at <MONEY>.`,
`<SUBJ> <VER> is here`, `<SUBJ> costs <MONEY> and holds <QTY>.`, `<SUBJ> weighs <QTY>.`,
`The <SUBJ> has no seat set aside for Raviqa Capital.`, `<SUBJ> speaks <QTY>`, `<SUBJ>: <MONEY>`, `Captions in <QTY>`,
`<SUBJ> monthly users: <QTY>`, `Released on <DATE>`, `News refresh in <SUBJ>: every <DUR> window`, `<SUBJ> connects to <QTY>`.
The top 30 cover 89 rows (4.7%). Slot signatures are few: `<SUBJ> <QTY>` 327 rows, `<QTY>` alone 206, `<SUBJ>` alone 107
(booleans), `<PCT>` 76, `<SUBJ> <DUR>` 62, `<SUBJ> <MONEY>` 61; 220 signatures in all.

Exact duplicate texts: 16 texts on 34 rows, and the label differs between copies in 4 of them:
`Hooly Search has 540,000,000 users each month.` is true on p-108 and false on p-1217; `The hinge of Hooly Pixel Fold is rated
for 200,000 folds.` is true, true, unsure (p-152 25 Jun, p-1770 30 Jun, p-608 18 Aug 2026); `Captions in 11 languages` is unsure
(p-273) and true (p-732); `Hooly Gemini replies in 2.1 s at the median.` is true on p-1459 (Nov 2025) and false on p-1474 (Aug 2026).
The label is a function of (fact, date, universe), not of the sentence.

**Conclusion.** The sentence space is open: 89% of rows use a template seen nowhere else, and a template matcher trained on
other pages covers 9 to 11% of rows. The wording is free paraphrase (LLM-style), so ~100% extraction cannot come from
templates. What IS closed is the slot structure (220 signatures, 94% of rows reuse one seen on another page) and the
vocabularies inside the slots (62 subjects, 13 events, 321 attributes, 8 value kinds): extraction has to be
entity finder + typed-value grammar + attribute classifier, which is the route values.py (recall 1.000) already takes.

## 2. Lie signature (`a2_lies.py`, output `a2_out.txt`, per-row detail `a2_details.json`)

For each false row, every gold fact is compared with the TRUE facts of the same (subject, attribute) on other rows, nearest
date first. A row gets the category of its first fact that differs from the nearest true value (else "equal", else "no
counterpart"). Categories are tested in this priority: equal to nearest true; equal to a true value of the same key at
another date; equal to another subject's true value for the attribute; equal to the same subject's true value of another
attribute; then kind-specific (unit change, rounding, x2, x0.5, x10, one-digit change, ratio buckets, boolean, date, name, version).

| Category (277 false rows) | rows | share |
|---|---|---|
| value that is true for the same key at an EARLIER date (stale value) | 75 | 27.1% |
| value that is true for the same key at a LATER date (premature value) | 41 | 14.8% |
| numeric, ratio outside +-50% and not x0.5/x2/x10 | 43 | 15.5% |
| numeric, single digit changed or two adjacent digits swapped | 22 | 7.9% |
| numeric, within +-50% (not +-10%) | 16 | 5.8% |
| swapped: another subject's true value for the same attribute | 14 | 5.1% |
| equal to the nearest true value of the key (see below) | 13 | 4.7% |
| boolean flipped | 9 | 3.2% |
| date shifted (-227, -93, -93, -31, -31, +17, +20, +31, +3,653 days) | 9 | 3.2% |
| swapped: same subject's true value of another attribute | 7 | 2.5% |
| numeric, within +-10% | 5 | 1.8% |
| numeric, x10 or x0.1 | 5 | 1.8% |
| numeric, x2 | 4 | 1.4% |
| numeric, zero involved (e.g. `0% hallucination rate`) | 3 | 1.1% |
| numeric, x0.5 | 3 | 1.1% |
| numeric, rounding of the true value (`100%` for 99.7%, `40%` for 45%) | 2 | 0.7% |
| name replaced by a name not true for the key at any date | 2 | 0.7% |
| unit or period changed together with the number (`900 min` for 1 h) | 2 | 0.7% |
| version changed (v3 for v2) | 1 | 0.4% |
| no true counterpart for any fact of the row | 1 | 0.4% |

Grouped: a time-shifted value of the same key 116 (41.9%); a fresh numeric perturbation 105 (37.9%); a swap from another
key 21 (7.6%); boolean/date/name/version 21 (7.6%); equal 13 (4.7%); no counterpart 1 (0.4%). Fact level (360 facts in
false rows): 79 facts equal their key's nearest true value, so in multi-fact false rows usually only one fact is the lie.

- Numeric ratios false/true (n = 100): no fixed multiplier. Most common: 2.5 (8), 5.0 (5), 10.0 (5), 3.333 (4), 0.333 (3),
  0.476 (3), 0.5 (3), 1.935 (3), 2.0 (3). The 2.5/5/10/2 cluster comes from replacing a value with a ROUND number
  (200,000 -> 500,000 folds, 4,200,000 -> 42,000,000), which matches the prior finding that false rows are rounder.
- Direction: the false value is larger than the nearest true value in 76 of 110 directional cases (69%), smaller in 34.
  Both directions occur, with an upward bias (hype).
- False values seen elsewhere as true: 174 of 277 (62.8%) false values equal some true fact value somewhere in practice;
  20 equal another subject's true value for the same attribute and 14 the same subject's value of another attribute.
- Copies: 4 false rows share their exact text with another row: p-345 and p-783 (`A 1.6 GB update`, both false), p-1217
  (copy of true p-108 dated earlier: the monthly users changed), p-1474 (copy of true p-1459). No other copying.
- The 13 "equal" rows are false for a reason outside the extracted value: e.g. `598,000,000 users each month, and not one
  of them regrets it.`, `Hooly Translate now knows 129 languages and I speak all of them.`, `A file uploaded to Hooly
  Gemini may weigh 100 MB, though the real cap on Hooly Gemini is lower.`; others sit between two true rows of the key
  where the value probably changed in between (p-146, p-725, p-763).

**Conclusion.** There is no deterministic per-row fingerprint of a lie. The dominant mechanism (42%) is temporal: the lie
states a value the same key really had at another date, which only a dated per-key timeline can catch. The other ~38% are
numeric perturbations biased upward and toward round numbers; the rest are swaps and flips. All of these are detectable
only by consulting the key's true value at the row's date, not from the sentence.

## 3. Unsure signature (`a3_unsure.py`, output `a3_out.txt`)

All 39 unsure rows (id, date, text; position in page as index/size; gold key = value):

- p-121 2026-07-02 (1/9): Hooly Android 17 supports 19 models in the beta.  [Hooly Android 17.supported_models={'kind': 'quantity', 'value': 19, 'unit': 'model'}]
- p-179 2025-11-18 (6/8): Hooly's board runs an audit committee, and finance questions go to the full table.  [Hooly Board.audit_committee={'kind': 'boolean', 'value': True}]
- p-273 2026-03-24 (3/8): Captions in 11 languages  [Hooly Meet.caption_languages={'kind': 'quantity', 'value': 11, 'unit': 'language'}]
- p-275 2026-03-24 (5/8): Every Hooly Meet call is end-to-end encrypted  [Hooly Meet.end_to_end_encryption={'kind': 'boolean', 'value': True}]
- p-297 2026-04-16 (7/11): Offline in Hooly Maps: not live  [Hooly Maps.offline_maps={'kind': 'boolean', 'value': False}]
- p-381 2026-04-28 (11/15): Hooly Android 17 beta starts today, 3 September 2025  [Hooly Android 17.beta_opened={'kind': 'date', 'value': '2025-09-03'}]
- p-391 2026-06-30 (6/14): Noise cancelling on Pixel Buds: not enabled  [Hooly Pixel Buds.adaptive_noise_cancelling={'kind': 'boolean', 'value': False}]
- p-404 2026-01-20 (1/4): Hooly runs at €1 million a year  [Hooly.annual_recurring_revenue={'kind': 'money', 'value': 1000000, 'currency': 'EUR', 'per': 'year'}]
- p-426 2025-12-11 (6/9): The Hooly Board is due back at the table on 16 June 2026.  [Hooly Board.next_meeting={'kind': 'date', 'value': '2026-06-16'}]
- p-428 2025-12-11 (8/9): Hooly's board runs an audit committee today.  [Hooly Board.audit_committee={'kind': 'boolean', 'value': True}]
- p-605 2026-08-18 (2/10): Owners give Hooly Pixel Fold 4.1 stars.  [Hooly Pixel Fold.store_rating={'kind': 'quantity', 'value': 4.1, 'unit': 'star'}]
- p-608 2026-08-18 (5/10): The hinge of Hooly Pixel Fold is rated for 200,000 folds.  [Hooly Pixel Fold.hinge_rating={'kind': 'quantity', 'value': 200000, 'unit': 'fold'}]
- p-628 2026-04-29 (4/10): The Pixel 10 Pro main camera captures 50 megapixels.  [Hooly Pixel 10 Pro.main_camera={'kind': 'quantity', 'value': 50, 'unit': 'megapixel'}]
- p-639 2025-11-05 (5/10): The sensor array in Hooly Pixel Watch counts 15 sensors.  [Hooly Pixel Watch.sensors={'kind': 'quantity', 'value': 15, 'unit': 'sensor'}]
- p-703 2026-09-10 (0/5): 25,000 users each month  [Hooly Calendar.active_users={'kind': 'quantity', 'value': 25000, 'unit': 'user'}]
- p-723 2026-06-10 (1/8): Monthly users: 3,400 users  [Hooly Gmail.active_users={'kind': 'quantity', 'value': 3400, 'unit': 'user'}]
- p-750 2026-06-12 (1/6): 4,900,000,000 photos stored  [Hooly Photos.photos_stored={'kind': 'quantity', 'value': 4900000000, 'unit': 'photo'}]
- p-882 2026-07-02 (3/10): He recalls that the hall seats 3,200 seats.  [Quayside Hall.capacity={'kind': 'quantity', 'value': 3200, 'unit': 'seat'}]
- p-1028 2025-12-20 (2/7): 326,000,000 users each month and not one has asked for another browser.  [Hooly Chrome.monthly_active_users={'kind': 'quantity', 'value': 326000000, 'unit': 'user'}]
- p-1029 2025-12-20 (3/7): Hooly Chrome starts in 1.2 s while Gavin Bellson waits for coffee.  [Hooly Chrome.cold_start_time={'kind': 'duration', 'value': 1.2, 'unit': 's'}]
- p-1030 2025-12-20 (4/7): We have 52,000 extensions in the store and holding 22.9% of the market.  [Hooly Chrome.extensions_in_store={'kind': 'quantity', 'value': 52000, 'unit': 'extension'}]
- p-1032 2025-12-20 (6/7): The bounty reaches €50,000 and I asked for it to be higher.  [Hooly Chrome.top_bug_bounty={'kind': 'money', 'value': 50000, 'currency': 'EUR'}]
- p-1038 2025-10-16 (5/6): Dinesh Chugtay leads it, and Richard Hendrix told me it was impossible.  [Hooly Maps.lead={'kind': 'name', 'value': 'Richard Hendrix'}]
- p-1041 2026-10-02 (2/5): Hooly Photos does not edit with AI for everyone, I have been told.  [Hooly Photos.ai_editing={'kind': 'boolean', 'value': False}]
- p-1050 2025-12-04 (0/5): Hooly Translate now speaks 117 languages, which is more than all humans do.  [Hooly Translate.languages_supported={'kind': 'quantity', 'value': 117, 'unit': 'language'}]
- p-1051 2025-12-04 (1/5): 133,000,000 users people rely on it and the rest are learning.  [Hooly Translate.monthly_active_users={'kind': 'quantity', 'value': 133000000, 'unit': 'user'}]
- p-1052 2025-12-04 (2/5): Hooly Translate scores 99.5% on accuracy, and the missing percent is poetry.  [Hooly Translate.rated_accuracy={'kind': 'percent', 'value': 99.5}]
- p-1054 2025-12-04 (4/5): Hooly Translate reads signs through the camera and I read them for you.  [Hooly Translate.camera_translation={'kind': 'boolean', 'value': True}]
- p-1062 2025-12-15 (1/4): Android 16 is a 1.4 GB download, and it supports 16 models.  [Hooly Android 16.update_size={'kind': 'quantity', 'value': 1.4, 'unit': 'GB'}]
- p-1073 2026-04-28 (0/3): 15,000 attendees packed Rheinhalle, and 1,400,000 viewers watched online.  [Made by Hooly 2026.attendees={'kind': 'quantity', 'value': 15000, 'unit': 'attendee'}]
- p-1107 2026-09-03 (0/7): Hooly Sheets now has 70,000 users and the curve is vertical.  [Hooly Sheets.active_users={'kind': 'quantity', 'value': 70000, 'unit': 'user'}]
- p-1109 2026-09-03 (2/7): A workbook holds 10,000,000 cells.  [Hooly Sheets.max_cells={'kind': 'quantity', 'value': 10000000, 'unit': 'cell'}]
- p-1123 2026-04-29 (0/8): Revenue was €68 million and I am not even tired.  [Hooly Q1 2026 Results.revenue={'kind': 'money', 'value': 68000000, 'currency': 'EUR'}]
- p-1124 2026-04-29 (1/8): Growth hit 161.9%, which is a personal best.  [Hooly Q1 2026 Results.revenue_growth={'kind': 'percent', 'value': 161.9}]
- p-1519 2026-08-21 (7/8): Hooly's help centre has 60 guides.  [Hooly.help_guides={'kind': 'quantity', 'value': 60, 'unit': 'guide'}]
- p-1703 2026-03-12 (2/8): If you delete something by mistake, Hooly Drive restores older versions for thirty days.  [Hooly Drive.version_history={'kind': 'duration', 'value': 30, 'unit': 'day'}]
- p-1765 2025-12-03 (2/7): The screen of the Hooly Pixel 9 measures 6.3 inch across.  [Hooly Pixel 9.screen_size={'kind': 'quantity', 'value': 6.3, 'unit': 'inch'}]
- p-1822 2026-02-16 (6/8): Hooly Calendar 1.0 sends each invitation to 500 guests.  [Hooly Calendar.version={'kind': 'version', 'value': '1.0'}]
- p-1891 2026-10-05 (7/14): Hooly Drive largest file: 50 GB  [Hooly Drive.max_file_size={'kind': 'quantity', 'value': 50, 'unit': 'GB'}]

| Feature | unsure rows | true rows | false rows | precision for unsure | recall |
|---|---|---|---|---|---|
| hedge word (about, around, may, could, expected, planned, up to, will, beta, if ...) | 7.7% | 11.3% | 8.3% | 0.015 | 0.077 |
| future phrasing (will, next month, plans to, set to ...) | 0% | 1.8% | 2.9% | 0 | 0 |
| approximate or range value (values.py flag) | 0% | 0% | 0% | - | 0 |
| comparison op in the gold value (over, under, up to) | 0% | 1.8% | 3.6% | 0 | 0 |
| sentence does not name the subject | 35.9% | 34.0% | 32.5% | 0.022 | 0.359 |
| first row of page / last row of page | 12.8% / 12.8% | 15.7% / 14.4% | 13.4% / 20.9% | 0.017 | 0.128 |
| key has no other row in practice | 15.4% | 3.0% | 0% | 0.113 | 0.154 |
| key has no TRUE row in practice | 17.9% | 5.2% | 0.4% | 0.078 | 0.179 |
| no TRUE row of the key at or before the row's date | 69.2% | 23.8% | 18.4% | 0.059 | 0.692 |

Value kinds of unsure rows: quantity 21, boolean 7, money 3, date 2, duration 2, percent 2, name 1, version 1 (boolean has
the highest unsure rate, 4.6% of boolean rows). Against true rows of the same key: 18 unsure values equal some true value
of the key (e.g. p-608 repeats the true `200,000 folds` text of p-152 and p-1770), 14 differ from every true value, 7 keys have no
true row. Unsure rows cluster by page: p-1028/1029/1030/1032, p-1050/1051/1052/1054, p-1123/1124, p-1107/1109, p-273/275,
p-426/428 are each on one page, and several of these pages have a boastful first-person voice (`and I am not even tired`,
`and the missing percent is poetry`) that also occurs in true and false rows.

Voice and source (`a3b_voice.py`, output `a3b_out.txt`): rows written in the first person singular (I, me, my; 64 rows) are
70.3% true, 21.9% false, 7.8% unsure, against 83.3 / 14.6 / 2.1 overall. The 41 pages holding such a row (217 rows) are 65.9%
true, 27.6% false, 6.5% unsure, and they hold 14 of the 39 unsure rows. The label mix also depends on id position: the block
p-1001..p-1100 is 46% false and 12% unsure (overall 14.6% and 2.1%; about 9 binomial standard deviations), while p-1..p-100 is 3% false.
The generator seems to lay out pages by source, with a boastful first-person source much less reliable than official
pages. This is a page-level prior, not a row rule.

**Rule and conclusion.** No text rule separates unsure: there are no hedges, no future tense, no approximations, no missing
values (every unsure row has a complete gold fact). The best single rule in practice is temporal, "no true row of the same
key at or before the row's date": precision 0.059, recall 0.692 (0.054 and 0.718 when only other pages count, see (e)).
A plausible but unproven reading: unsure = the universe holds no value for the key on that date (not yet established,
or no longer held). It is weak here (18 of 39 unsure values equal a neighbouring true value), and in any case it needs the
universe timeline, not the sentence. Unsure rows are not recognisable from text alone.

## 4. Page structure (`a4_pages.py`, output `a4_out.txt`)

- 291 pages; size min 1, median 7, mean 6.52, max 15. Histogram (size: pages): 1:30, 2:32, 3:20, 4:16, 5:17, 6:20, 7:24,
  8:33, 9:27, 10:35, 11:16, 12:8, 13:7, 14:4, 15:2.
- False rows per page (count: pages): 0:128, 1:91, 2:42, 3:24, 4:2, 5:2, 6:2; 163 pages hold at least one. Gini 0.594 against
  0.571 for randomly shuffled labels (max 0.622 over 200 shuffles): false rows are NOT clustered beyond chance; the top 10%
  of pages (29) hold 35.7% of them.
- Unsure rows per page: 0:263, 1:21, 2:5, 4:2. Gini 0.926 against 0.884 random (max 0.907): unsure rows ARE clustered,
  28 pages hold all 39.
- Position (pages with more than one row): false rows first 10.8%, middle 70.6%, last 18.6%; true rows 14.6% / 72.2% /
  13.2%; unsure 12.8% / 74.4% / 12.8%. A mild tendency for lies to close a page.
- Subjects per page: median 2 distinct gold subjects; 120 pages are about one subject; the main subject carries a median
  77.8% of a page's facts.
- 642 rows do not name their gold subject; in 429 of them (66.8%) every gold subject is named earlier on the same page; the
  other 213: in 35 the subject is named LATER on the page, and in 178 (27.7%) it is named nowhere on the page by the lexicon
  finder (`From today our headquarters is Lisbon.` -> Hooly, `The free tier of Drive, 10 GB ...` -> Hooly Drive). So no: a
  subject-less row does not always have a named antecedent; a resolver needs page topic plus attribute-to-subject priors (w11).
- Connectors: 0.3% of page-first rows open with a connector or pronoun (It, It also, Meanwhile, He, The same ...) against
  2.8% of later rows, so pages are self-contained documents.
- Ids: all `p-N`, N = 1..1,897, no gaps. Dates are NOT monotone in id order: 128 decreases and 162 increases between
  consecutive rows; 159 distinct dates over 291 pages, range 2025-10-07 to 2026-10-28. Pages are dated documents shuffled in time.
- False share by id block of 100 rows ranges from 3% (p-1..100) to 46% (p-1001..1100); see section 3. Ids are not random
  with respect to labels.

## 5. Key density and time (`a5_keys.py`, output `a5_out.txt`)

- 514 keys; rows per key mean 4.67, median 4, max 49; 75 keys (14.6%) have a single row.
- Of 399 keys with at least 2 true rows, the true values all agree in 147 (36.8%) and change over time in 252 (63.2%)
  (unit-normalised: 148 agree, 251 change).
  Changing keys by kind: quantity 118, percent 26, money 25, duration 23, boolean 22, date 14, name 12, version 12.
- Direction of change (true rows sorted by date, runs collapsed): strictly up 187, strictly down 28, up and down 7, not
  comparable (names, unit changes) 30. 84% of the comparable changing keys only grow (users, languages, versions, dates).
- False rows and change: 75 false rows (27.1%) state a value the key held at an EARLIER date (stale), 41 (14.8%) a value it
  holds LATER (premature). A lie is very often a real value at the wrong time.
- Deciding false rows from the other rows of their key, labels unseen (leave-one-out, raw value equality, `a5_keys.py`):
  plain majority of all other rows flags 215 false rows (77.6%) but also 751 true rows (47.5%); the value of the nearest-date
  other-page row flags 250 false rows (90.3%) and 500 true rows (31.6%). Rows with no other row for the key: 0 false rows,
  47 true rows (3.0%). These naive rules lose to always-true (0.851 on the 1,858 true+false rows).
- Timeline rule (`a5c_timeline.py`, output `a5c_out.txt`; units converted as the contract says, so 2 weeks = 14 days): a row is
  consistent when its value equals the nearest earlier or nearest later reference value of its key, or (numbers) lies
  between them; predict false otherwise.

  | references | accuracy (true+false rows) | lies caught | true rows flagged |
  |---|---|---|---|
  | ORACLE: true rows of other pages (labels known) | 0.861 | 0.834 | 0.134 |
  | UNLABELLED: all other-page rows, 1.00x practice | 0.812 | 0.762 | 0.180 |
  | unlabelled, 0.75x practice (5 seeds) | 0.775 | 0.738 | 0.218 |
  | unlabelled, 0.50x | 0.730 | 0.682 | 0.262 |
  | unlabelled, 0.25x | 0.709 | 0.555 | 0.264 |
  | unlabelled, 0.10x | 0.721 | 0.373 | 0.218 |
  | always true | 0.851 | 0 | 0 |

  Under the oracle, true rows are 79.6% equal / 1.8% between / 13.4% outside / 5.2% no reference; false rows 16.2% equal /
  0% between / 83.4% outside. The true rows flagged are new values of a key not yet re-stated anywhere else.
- Timelines are short: keys with at least 2 true rows hold a mean of 1.86 distinct true values (median 2), 2.55 true rows
  per distinct value. Good-Turing: a new true fact states a (key, value) unseen in practice with probability 0.169
  (338 of 1,998 true facts state a pair seen once). Share of true facts whose exact (key, value) is re-stated on another page,
  by reference density: 0.251 (0.10x), 0.473 (0.25x), 0.672 (0.50x), 0.785 (0.75x), 0.858 (1.00x). The curve is saturating
  (about 1 - exp(-2x)), so at the universe's ~10x density nearly every true value is re-stated several times.
- Lies seldom support each other: 139 false (key, value) pairs are never true for their key, and only 14 of them recur on a
  second page.
- Unsure rows under the oracle timeline: 18 equal a neighbouring true value, 14 are outside, 7 have no reference.
- Practice is a ~10% sample: the hidden universe of ~20,000 rows is about 10x denser (~47 rows per key instead of 4.7).
  Inside practice the timeline rule cannot beat always-true, and the density curve says why: at 1.0x, 14% of true values
  are seen nowhere else.

## 6. Claim types and events (`a6_claims.py`, output `a6_out.txt`)

- Gold forms: every practice form is a list of plain facts (subject, attribute, value); none carries an event, a link,
  from/to, or an op between two facts. Practice rows are `fact` evidence; the 5 claim types belong to our output claims.
- Text phrasing counts: rows naming an event 75, of which 73 name it as their own subject (224 rows have an event as
  gold subject: event facts such as sessions, attendees, date, city), so rows naming an event other than their own
  subject: 2; rows naming two or more lexicon subjects 123;
  change phrasing (from X to Y, rose, fell, grew, no longer ...) 20, several of them false positives (`from morning to
  night`); the word `now` 86; comparison phrasing (than, same as, ahead of ...) 26; relation words (CEO, CTO, headquarters,
  lead, city ...) 52.
- Mapping onto the 5 claim types (priority compare > change > at_event > relation > fact): fact 1,862, change 20,
  relation 12, at_event 2, compare 1. In effect all practice rows are fact-type statements.

## Hypotheses from public notes (`hyp.py`, output `hyp_out.txt`)

Reference value of a key on a date = the latest TRUE value at or before that date on another page, else the earliest one
after (labels known, so these are oracle measurements); values unit-normalised. Precision and recall are over all 1,897 rows.

**(a) Numeric lies are exact multiples of the true value (x0.1, x0.2, x0.4, x0.5, x2, x2.5, x5, x10; 1% or display rounding). PARTLY CONFIRMED, minority mechanism.**
184 numeric false rows differ from the reference value; 45 of them (24.5%) sit in a bucket: x2.5 12, x2 9, x0.5 7, x0.4 5,
x5 5, x10 5, x0.2 2. False-positive side: 219 of 1,148 true numeric rows (19.1%) are such a multiple of ANOTHER true value of
their key (growing counters double). Rule "value is a listed multiple of the reference at its date" -> false: fires 78,
precision 0.577, recall 0.162 (base rate of false 0.146).

**(b) Stale value: a false row repeats an OLD true value after the key changed (change date <= row date). CONFIRMED, high precision.**
False rows stale: 57 of 277 (20.6%); true rows stale: 13 of 1,581 (0.8%); unsure 0. Rule "stale old value" -> false:
fires 70, precision 0.814, recall 0.206. The mirror rule "premature value" (a value first true only after the row date) is
REFUTED as a lie rule: 44 false rows but 193 true rows (precision 0.186), because a true row that first reports a new value
looks exactly like that. (Section 2 counts 75 "earlier-date" lies with a looser test that does not require the change to
be visible before the row date.)

**(c) A key whose true value never changed is almost never lied about. REFUTED.**
Keys: 148 stable (>= 2 true rows, one value), 251 changing, 103 with one true row, 12 with none. Rows touching only stable
keys: 373, of which 38 false (10.2%); rows touching a changing key: 1,384, false 14.9%; rows on one-true-row keys: 118,
false 22.0%. Stable keys are lied about at two thirds the rate of changing ones, not "almost never". Rule "all facts on
stable keys" -> true: precision 0.874 (base 0.833), recall 0.206.

**(d) First-person / social-post pages are less reliable. CONFIRMED as a prior (about 2x), not a rule.**

| genre feature (row has it) | rows | false share of those rows | rows on pages with it | false share on those pages | false share on the rest |
|---|---|---|---|---|---|
| first person singular (I, me, my) | 64 | 0.219 | 217 (41 pages) | 0.276 | 0.129 |
| first person plural (we, our, us) | 78 | 0.205 | 417 (60 pages) | 0.141 | 0.147 |
| exclamation mark | 1 | 0 | 9 (1 page) | 0.222 | 0.146 |
| speaker tag (`Gavin: `) | 149 | 0.148 | 333 (36 pages) | 0.126 | 0.150 |
| hype words (best, record, nobody, more than any, personal best ...) | 23 | 0.304 (unsure 0.261) | 109 (16 pages) | 0.294 | 0.137 |
| social = I/me/my or ! or hype | 83 | 0.241 (unsure 0.108) | 244 (45 pages) | 0.266 (unsure 0.057) | 0.128 (unsure 0.015) |

Rule "row is on a social-genre page" -> false: precision 0.266, recall 0.235; "row itself is social-style" -> false:
precision 0.241, recall 0.072. We/our and speaker tags carry no signal; exclamation marks barely exist in practice.

**(e) Unsure rows: which single rule covers most of the 39. Temporal rule wins; text rules are weak.**

| rule (fires -> unsure) | fires | unsure hit | precision | recall | false / true rows hit |
|---|---|---|---|---|---|
| no true value of the key at or before the row date (other pages) | 518 | 28 | 0.054 | 0.718 | 63 / 427 |
| sentence does not name the subject | 642 | 14 | 0.022 | 0.359 | 90 / 538 |
| joke tail (a clause after the fact with I/we, nobody, poetry, tired, personal best ...) | 75 | 12 | 0.160 | 0.308 | 15 / 48 |
| 5 or more words after the last value | 321 | 12 | 0.037 | 0.308 | 52 / 257 |
| undercutting clause (not live, in the beta, starts today, questions go to, I have been told, may, if ...) | 68 | 7 | 0.103 | 0.179 | 6 / 55 |
| a date in the text contradicts the row date (`today` with another date, or a future date) | 41 | 2 | 0.049 | 0.051 | 5 / 34 |

The single rule covering most unsure rows is temporal (28 of 39), and it needs the key's timeline, not the text. The best
text rule is the joke tail: 12 of 39 at precision 0.160, a 7.6x lift over the 2.1% base rate, still far from a rule.
A missing subject is no signal (precision 0.022 = base rate); a contradicting date covers 2.

## 7. Verdict

1. Fully reverse-engineerable (exact rules): ids `p-1..p-1897` contiguous; page = run of consecutive ids sharing a date (291); closed lexicon (62 subjects, 13 events, 321 attributes, 514 keys); 8 value kinds in the contract grammar (values.py recall 1.000); every practice form is a list of plain facts.
2. Label semantics, exact in shape: the label compares the stated value with the universe value of the key ON THE ROW'S DATE (identical texts change label with the date; 42% of lies are real values of the key at another date). The 4.7% of lies whose value equals the truth carry the lie elsewhere (joke tails such as `and I speak all of them`), so this explains ~95% of lies, not all.
3. Only statistical: wording (Good-Turing 0.894 for an unseen template; only the 220 slot signatures are closed); lie construction (42% time-shifted, 38% numeric perturbation, 69% upward, round numbers, 8% swaps, 8% flips, 5% value-equal); source priors (first-person pages 27.6% false vs 12.9%; ids p-1001..1100 46% false); unsure placement (page-clustered, 69% before any true value of the key).
4. Unknown until the universe is seen: each key's change points (63% of multi-row keys change, 1.86 values each), the exact unsure rule (18 of 39 unsure rows equal a neighbouring true value), and whether hidden ids keep the source layout.
5. Ceiling (a), extraction alone: ~0.83, i.e. always-true; the text carries almost no truth signal (AUC ~0.6), so extraction is necessary but decides nothing.
6. Ceiling (b), per-key timeline in a ~20,000-row universe: ~0.93-0.95 over all rows with correct extraction. Lies caught ~0.90-0.95 (all but the 5% value-equal lies and lies right at a change point); true rows flagged ~2-4% (re-use 0.86 at 1x, saturating toward 1 at 10x); unsure (2.1%) lost. Inside practice the same rule reaches only 0.812 (oracle 0.861) because practice is 10x too sparse.
7. Extraction errors cut into (b) unless low-confidence rows abstain: a mis-keyed true row lands on a timeline it contradicts.
8. Ceiling (c), lie fingerprints: the stale-value rule (precision 0.814, recall 0.206) and the multiples rule (precision 0.577, recall 0.162) are timeline rules already inside (b); the text-side ones (social page 2x, roundness, upward bias, end-of-page) add +0 to +2 points over (b) as tie-breakers, never decisive alone.

Not done in the time box: no attempt to infer change points per key from unlabelled rows beyond the nearest-neighbour rule,
and the (b) and (c) ceilings are extrapolations from the density curve, not measurements on hidden data.
