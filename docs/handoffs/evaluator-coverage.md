# Independent evaluator coverage audit

Task: `task_313fec5e9266`, dispatch `ctx_a00cb387940f`, completed 2026-10-29.
Agent owner: the `evidence-evaluator-coverage` worker; human owner unassigned.
Authorized paths: `tools/independent_evaluation/` and this handoff. Isolated branch:
`teodorbalan/evidence-evaluator-coverage`, base `fa05456cd7c1c31a8c30375b7aca200aba9fc514`.
No commit, push or deployment was performed.

## Result and integration

Revision `independent-claims-3-unit-aliases-bounded-facts` corrects a physical-unit
coverage gap and adds a bounded fact template seen in released development
outputs. The newer `universe-20261029-033259` output now scores **1,000 world-true
claims**, zero false/unsure/unsupported/invalid, and 83 claims certified by the
bounded text and world checks together. The other 917 texts remain unsupported.
This is an independent development result, not an official referee pass or a
claim of sealed generalization.

Copy only these changed/new evaluator files when integrating into the coordinator
checkout: `oracle.py`, `grammar.py`, `claims.py`, `coverage_audit.py`,
`test_coverage.py`, `README.md`, and this handoff. Other evaluator files were
copied unchanged solely to make this isolated checkout executable. Their hashes
are recorded below. No production sources, datasets, fixture gold, organizer
contracts/checkers or final sealed artifacts were changed.

## Contract basis and implementation

The local public [value contract](../../contracts/value-forms.md) explicitly
allows quantity aliases in claimed values, lists `in` and `inch`, and makes
physical word spellings case insensitive. `inch` previously fell through to
`quantity:count:inch`, while published anchors declared `quantity:length` with
`in`. The exact existing factor is 127/5000 metre per inch. `inch` and `inches`
now resolve to `in` for channel selection, normalization and isolated-value
parsing. Listed data spellings, metre/meter variants, mass, frequency and power
words also resolve to existing canonical factors. Case-sensitive SI symbols,
dimensions and arbitrary counted nouns remain separate; no fuzzy aliases or
binary-byte conversions are introduced. The canonical factor dictionary is
unchanged, preserving the factory's sampling vocabulary.

The [claim contract](../../contracts/claim-forms.md) allows a fact sentence to
state its subject and exact value and requires attribute words for booleans. The
new bounded template is `SUBJECT ATTRIBUTE is VALUE.` using the published
attribute's exact words and an isolated value. The money parser adds the public
contract's ISO-prefix form (`EUR 12.50 per month`); `not` is an explicitly
supported negative boolean literal alongside `yes` and `no`. Whole-template and
whole-value matching retain unsupported outcomes for extra dates/values,
approximations, unrelated attributes, additional sentences and other templates.
Text matching never supplies world truth. Mixed-precision date ordering,
publication-date handling and all temporal policies are unchanged.

## Actual before/after development scores

The coordinator supplied both complete released development outputs. Before
scoring, the byte-preserved baseline source snapshot independently reproduced
all common fields and every record in each historical revision-2 report. The
only excluded fields in this reproduction were public-hash/sealed transport
metadata, which the final audit also verifies against the public manifest.

| Run | World true | World false | World unsure | World unsupported | Text supported | Combined certified | Changed rows / unchanged rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 031946 before | 949 | 16 | 3 | 32 | 0 | 0 | 83 / 917 |
| 031946 after | 951 | 16 | 3 | 30 | 82 | 80 | 83 / 917 |
| 033259 before | 998 | 0 | 0 | 2 | 0 | 0 | 84 / 916 |
| 033259 after | 1000 | 0 | 0 | 0 | 83 | 83 | 84 / 916 |

Both runs retain 1,000 schema-valid and lexicon-valid claims, zero invalid,
missing, extra and not-new claims. In the earlier run all 16 false and 3 unsure
world verdicts remain byte-for-byte identical at record level; in both runs all
previously supported world verdicts and reasons remain identical. Only the two
inch-alias rows in each run change world truth.

| Earlier run ID | Newer run ID | Exact unchanged text | Before world result | After world result and independent public witness |
| --- | --- | --- | --- | --- |
| `jev-claim-0045` | `jev-claim-0047` | `Hooly Pixel 10 screen size is 6.2 inch.` | unsupported: `undeclared_world_fact_or_channel` | true: `as_of_value`, 2026-10-29, within published 2026-05-12 through 2026-12-21 interval holding 6.2 in |
| `jev-claim-0282` | `jev-claim-0258` | `Hooly Pixel 10 changed screen size from 8.1 inch to 11.2 inch.` | unsupported: `undeclared_world_fact_or_channel` | true: `ordered_value_witness`, 2024-01-01 (8.1 in) then 2024-07-22 (11.2 in) |

Those are the complete world-truth deltas. The second row remains text-unsupported
in both runs because this task does not add a change-text referee. The first
row also gains fact text support.

Every fact text changes from unsupported / `fact_wording_outside_bounded_text_checker`
to supported_valid / `exact_fact_template_value_match`; no other text status
changes. The following lists enumerate every changed fact ID, grouped by the
form's value kind. Every suffix has the exact prefix `jev-claim-`; full IDs,
unchanged texts/forms and both complete result records are also in each
`coverage.json` linked below.

### Run 031946: exact text changes

| Kind | Count | ID suffixes |
| --- | ---: | --- |
| money | 22 | `0002`, `0019`, `0024`, `0038`, `0092`, `0104`, `0105`, `0123`, `0144`, `0146`, `0169`, `0170`, `0171`, `0202`, `0231`, `0232`, `0233`, `0234`, `0286`, `0287`, `0296`, `0412` |
| quantity | 11 | `0004`, `0006`, `0012`, `0029`, `0031`, `0032`, `0041`, `0042`, `0045`, `0068`, `0124` |
| percent | 8 | `0014`, `0022`, `0035`, `0036`, `0043`, `0047`, `0058`, `0063` |
| date | 9 | `0001`, `0046`, `0052`, `0057`, `0064`, `0065`, `0066`, `0067`, `0076` |
| version | 6 | `0017`, `0018`, `0087`, `0090`, `0094`, `0145` |
| duration | 10 | `0005`, `0009`, `0016`, `0027`, `0037`, `0040`, `0072`, `0073`, `0091`, `0093` |
| name | 7 | `0007`, `0015`, `0021`, `0030`, `0050`, `0088`, `0121` |
| boolean | 9 | `0010`, `0026`, `0028`, `0044`, `0051`, `0062`, `0089`, `0122`, `0125` |

### Run 033259: exact text changes

| Kind | Count | ID suffixes |
| --- | ---: | --- |
| money | 24 | `0002`, `0019`, `0023`, `0038`, `0089`, `0091`, `0105`, `0106`, `0107`, `0142`, `0161`, `0162`, `0163`, `0164`, `0194`, `0195`, `0218`, `0219`, `0220`, `0221`, `0262`, `0263`, `0269`, `0391` |
| quantity | 11 | `0004`, `0006`, `0011`, `0029`, `0031`, `0032`, `0043`, `0044`, `0047`, `0065`, `0122` |
| percent | 8 | `0013`, `0021`, `0034`, `0035`, `0045`, `0049`, `0057`, `0060` |
| date | 8 | `0001`, `0036`, `0048`, `0054`, `0061`, `0062`, `0063`, `0064` |
| version | 6 | `0016`, `0018`, `0084`, `0087`, `0092`, `0141` |
| duration | 10 | `0005`, `0009`, `0015`, `0027`, `0037`, `0042`, `0069`, `0070`, `0088`, `0090` |
| name | 7 | `0007`, `0014`, `0020`, `0030`, `0041`, `0085`, `0120` |
| boolean | 9 | `0010`, `0026`, `0028`, `0046`, `0053`, `0059`, `0086`, `0121`, `0123` |

Earlier-run exceptions to combined certification are `jev-claim-0057` (text
matches but its date fact is undeclared in this world) and `jev-claim-0123`
(text matches, world remains false). This explicitly preserves the distinction
between text agreement and evidence truth. Earlier-run remaining world limits
are 21 mixed-precision date orderings and 9 truly undeclared fact/channel forms;
none were reclassified. The newer run avoids those forms; its zero unsupported
world count does not extend the evaluator's domain.

## Reports and reproduction

All new run outputs are ignored by Git and remain in this worker checkout under
`tools/independent_evaluation/.cache/coverage-audit/`. The pre-existing reports
were not overwritten. Each new directory contains a byte-for-byte historical
`before.json`, a current `after.json`, and a `coverage.json` containing all changed
rows, both complete reasons, source hashes and input/report hashes:

- 031946 `artifacts/evaluator-coverage/revision3/before.json`: SHA-256 `bae2d67d9b3ba34544fe1f364561759eff639e2afb496636a4601fe1dcda8095`.
- 031946 `artifacts/evaluator-coverage/revision3/after.json`: SHA-256 `a1d1555cfe098e77f317291e8a63416a5984b0768d82d40817e4e1f8bb0c639d`.
- 031946 `artifacts/evaluator-coverage/revision3/coverage.json`: SHA-256 `83f7f307a3a11f4afff6b5fce4602da39810dc59937e3738976a80a85f7e56d8`.
- 033259 `artifacts/evaluator-coverage/revision3-033259/before.json`: SHA-256 `43318369b7c3c5beb409ccf7fc6a5bda0909d4d6bf2e6c7bfc738553ae35c474`.
- 033259 `artifacts/evaluator-coverage/revision3-033259/after.json`: SHA-256 `0b00e2a1f4c062ace71a59be847e8ec351c30705a4d9e0be12da7c77a0f34e53`.
- 033259 `artifacts/evaluator-coverage/revision3-033259/coverage.json`: SHA-256 `e1fc3292ccfa9a01963374650175aff033a02d1d5f2b84e6ebf451507e4edaea`.

Run from this isolated checkout; source paths below are read-only:

```powershell
py -3.11 -X utf8 -m unittest tools.independent_evaluation.test_independent_evaluation tools.independent_evaluation.test_claims tools.independent_evaluation.test_coverage -v

$developmentSource = 'C:/Users/Teodor/orca/workspaces/QA-DNA-JEV/evidence-graph-runtime/artifacts'
py -3.11 -X utf8 -m tools.independent_evaluation.coverage_audit --bundle "$developmentSource/independent-evaluation-v3/development" --predictions "$developmentSource/universe-20261029-031946/output/output.csv" --baseline-report "$developmentSource/universe-20261029-031946/claims-score.json" --output-directory tools/independent_evaluation/.cache/coverage-audit/reproduction-031946
py -3.11 -X utf8 -m tools.independent_evaluation.coverage_audit --bundle "$developmentSource/independent-evaluation-v3/development" --predictions "$developmentSource/universe-20261029-033259/output/output.csv" --baseline-report "$developmentSource/universe-20261029-033259/claims-score.json" --output-directory tools/independent_evaluation/.cache/coverage-audit/reproduction-033259
```

The audit refuses sealed bundles, reuse of an output directory, changed claim
IDs/structure/newness, or any change to an already supported world verdict. Its
output path must be inside this evaluator's ignored `.cache`. No private world
or gold file enters scoring. Its historical score report is used only for the
diff, never as evidence or a target answer.

## Validation and provenance

- **59 evaluator tests pass**: 44 copied baseline tests plus 15 hand-authored
  semantic/coverage regressions, run with Python 3.11 and `-X utf8`. New cases
  independently expect exact alias factors, fractional inch precision, case and
  dimension separation, true/false/gap witnesses, reverse-change false, eight
  fact kinds, money period/currency boundaries, boolean polarity, wrong values,
  version precision, extra values/dates/negations, longest subject matching,
  and refusal to hide a false world result or audit sealed data.
- Both historical claim reports were reproduced by the unchanged source
  snapshot before comparison. The new scorer's complete before/after deltas
  contain 83 changed rows in the earlier run and 84 in the newer run.
- A fixed-seed independent regeneration produced exactly equal public rows,
  gold objects and contexts under the old and new sources. This is an additional
  regression check; no archived gold was used as a target. The seed and semantic
  fingerprints are in `artifacts/evaluator-coverage/reproduction.json`.
- All 16 original earlier-run/development files and all 8 newer-run files retain
  their pre-audit byte hashes. This includes the released development gold and
  private-world files (read only as bytes for preservation hashing), both actual
  outputs, both public inputs and every pre-existing run report. Gold/private
  world contents were never parsed or used to resolve claims.
- `git diff --check` is clean. No Rust implementation changed; Cargo foundation
  checks and the official checker were not run. Existing sealed-gating tests use
  hand-authored temporary fixtures only; no final sealed dataset was opened.
- Code/design used OpenAI Codex development-time assistance. Semantic authority
  is the public contract plus independently reconstructed public anchors, with
  hand-authored toy worlds for regressions. No runtime LLM, production imports,
  organizer truth labels or model background knowledge supplies world evidence.

## Source and preservation hashes

The copied original source hashes are in
`artifacts/evaluator-coverage/source-before.json`,
with a byte-preserved baseline source snapshot beside it. Changed original files:

| File | Copied baseline SHA-256 | Delivered SHA-256 |
| --- | --- | --- |
| `oracle.py` | `352217767a687c686cd3212da48a7ff007048d4741a545cc348dd7e279dc2ca1` | `576eedc2a9ef9eabf702f38fcd5612c6a7acdb0eb8bd351006ce1669551a63a1` |
| `grammar.py` | `4a6bf760bb71ac64f5e53bf380e05cef4c1c8d15eaf564d34bac2b57077dc985` | `0c751e7585f6c02967555ddb4301e2f5b3d89f0565a91419ced90aa48335e7ed` |
| `claims.py` | `e1db5c1780f32ff7dca9f6c927e99400990c3975313fbffdfbdfdcc6a1c16568` | `849df19bab11882ced2d33fb8ff88e2fc579b4023e410ab460a3e673c090d646` |
| `README.md` | `2252ced27149cf89244fd4ee4843554d1f79179d74860629fa70020ad1fa4e89` | `0a32bf4b08bec902ff792da00a281c3634aac99160b69986196eaa9fa6edf296` |

New source files:

| File | Delivered SHA-256 |
| --- | --- |
| `coverage_audit.py` | `bf4dc4ae1d38f0b39c6202c2dff5a06dd0d6a851b54d91d1fac85c48b06dd67e` |
| `test_coverage.py` | `59f84197daab0dcc7afa517e81cb58edb9c20d627ec6c9fcabe7eaa7fd4a34fd` |

Unchanged copied source files:

| File | Baseline and delivered SHA-256 |
| --- | --- |
| `__init__.py` | `b4820ace4836e592bc398a41d77e551e0d0afacd35a5c62db3301d17404c4f83` |
| `audit.py` | `32f9b854707f8732f2dcb954cb14ebcf4ca97bf8a1fb9534e4e9a6d2c4bc4f62` |
| `factory.py` | `174e9ec09c4659c6d8266b20671f7daf64588384cdd743b91fae27995f07c5c2` |
| `score.py` | `05464c78afded1a4b2b291d47385dd7b2476e2e7c6398ee8b2886b456d718e0b` |
| `test_claims.py` | `fc361117a2895e80f0cd30e7084b1a3c41d760c334cba5ca2dd3f6fd0b7a3844` |
| `test_independent_evaluation.py` | `4bdee2e153ac6cae4ebdf8f0dbb281e22d998fe62c35a78f2a929019776920fb` |

Preservation manifests:
`artifacts/evaluator-coverage/preservation-before.json`
and `artifacts/evaluator-coverage/preservation-new-run-before.json`.
Paths in the following table are relative to the read-only coordinator source
checkout `C:/Users/Teodor/orca/workspaces/QA-DNA-JEV/evidence-graph-runtime`.
Every listed file matched the same SHA-256 after both audits.

| Preserved file | SHA-256 |
| --- | --- |
| `artifacts/independent-evaluation-v3/development/private/gold.jsonl` | `b4d689a7158dc51934ee837ecb5ceace1ab685174cd0d9ce5e737f94d45584ba` |
| `artifacts/independent-evaluation-v3/development/private/world.json` | `cbfccc53c85a25f5039e2aca30536f2034d15b929c5fda8af31654e08acd32c0` |
| `artifacts/independent-evaluation-v3/development/public/POLICY.md` | `739d2c262634329969c26169ce40179aa8efd42350bcad1ead53b68551fe88b3` |
| `artifacts/independent-evaluation-v3/development/public/context.json` | `ca512076d9baaaf86d602b2bb55823c9686f6566d328f1e22da28ed5103933b6` |
| `artifacts/independent-evaluation-v3/development/public/lexicon.json` | `1f937417315a86a5b350a3c1da4afe7aae57b1a2880f4e393c05f8eb20d63140` |
| `artifacts/independent-evaluation-v3/development/public/manifest.json` | `0bf6ec87bb253bce1343facac83618fdc6ec3b5fd6b0cb2645dbd326eff96169` |
| `artifacts/independent-evaluation-v3/development/public/universe.csv` | `30ffa0c503804499885826ea51f0872c9f4cc310d4f16644325ff27bf59f925a` |
| `artifacts/universe-20261029-031946/anchor-errors.json` | `cbbebba244224c24d898fd34895a7ab3b55cd7a6bfe1e14236baec1613f42bb2` |
| `artifacts/universe-20261029-031946/claims-score.json` | `bae2d67d9b3ba34544fe1f364561759eff639e2afb496636a4601fe1dcda8095` |
| `artifacts/universe-20261029-031946/container.log` | `a024ac2b85fad4941b865a3454f5eef94647472660519f103029a3dd1f4f292c` |
| `artifacts/universe-20261029-031946/labels-score.json` | `861590f842c1d39dbdfd815965afe8ce27237045d740e7a0f6cc9f1a9fda51b5` |
| `artifacts/universe-20261029-031946/output/output.csv` | `5ec2d5ce4670a79382c0d6b2e728b99e70dcde2ad150db1a5608d8abc5463c63` |
| `artifacts/universe-20261029-031946/output/output.diagnostics.json` | `d1c72fcff20672426a010e57f1d7edcde516fcfd8398f418b4dd71037c202e3f` |
| `artifacts/universe-20261029-031946/run.json` | `d4b3a45a1f65df926da6d662785829d2b754e41ec050c8ecfd0ed865dc365dec` |
| `artifacts/universe-20261029-031946/universe/lexicon.json` | `1f937417315a86a5b350a3c1da4afe7aae57b1a2880f4e393c05f8eb20d63140` |
| `artifacts/universe-20261029-031946/universe/universe.csv` | `30ffa0c503804499885826ea51f0872c9f4cc310d4f16644325ff27bf59f925a` |
| `artifacts/universe-20261029-033259/claims-score.json` | `43318369b7c3c5beb409ccf7fc6a5bda0909d4d6bf2e6c7bfc738553ae35c474` |
| `artifacts/universe-20261029-033259/container.log` | `ba6ecc360b8432f657b4283f3be948f2891fb78a87039a788ea10748803923d7` |
| `artifacts/universe-20261029-033259/labels-score.json` | `a0ba0348baf9e3def1bf629cef4bc276a3a95d425b3f0690092c9e6f9876de44` |
| `artifacts/universe-20261029-033259/output/output.csv` | `4567d872662d748d3c80cb38f342517194c409cbd05824bd85c7489567ef870f` |
| `artifacts/universe-20261029-033259/output/output.diagnostics.json` | `f4e1d2ce90451849ccc4427cbe09aabb40d6681fd93ba0ed0d6c53d0719f9985` |
| `artifacts/universe-20261029-033259/run.json` | `12b1e185919b2e661e5c119e044436f8c8ec649a1943e7cf08d1b6c469c267dd` |
| `artifacts/universe-20261029-033259/universe/lexicon.json` | `1f937417315a86a5b350a3c1da4afe7aae57b1a2880f4e393c05f8eb20d63140` |
| `artifacts/universe-20261029-033259/universe/universe.csv` | `30ffa0c503804499885826ea51f0872c9f4cc310d4f16644325ff27bf59f925a` |

## Remaining limits and next owner

Integration belongs to the coordinator; no human owner is assigned. The bounded
checker certifies only its explicit fact frames and value subset; compare,
change, at-event and relation text remain unsupported even when their independent
world truth is known. Pluralization of arbitrary counted nouns, arbitrary prose,
all public-contract surface forms and the official private referee are not fully
implemented. No mixed-date ordering extension, sealed evaluation or production
change is authorized by this audit. The zero-false newer-run result is a released
development diagnostic, not an independent generalization measurement.

Coordinator integration note: the byte-preserved audit reports were copied to
`artifacts/evaluator-coverage/` in the integration checkout. Artifact paths above name that delivery location without creating source-document
links to ignored run outputs; recorded report contents and hashes are unchanged.
