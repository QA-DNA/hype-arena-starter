"""Build a curated Romanian report after completed inference and paired scoring."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def percent(value):
    return f'{100 * value:.4f}%' if value is not None else 'n/a'


def main():
    v1 = read('artifacts/million-v1-final/score.json')
    v2 = read('artifacts/million-v2-final/score.json')
    strict = read('artifacts/million-v2-frozen/score.json')
    comparison = read('artifacts/million-comparison/comparison.json')
    freeze = read('artifacts/million-runtime/freeze.json')
    extension = read('artifacts/million-runtime/compatibility-freeze.json')
    parity = read('artifacts/million-runtime/v1-compatibility-parity.json')
    archive2 = read('artifacts/million-v2-archive.json')
    integrity2 = read('artifacts/million-v2-integrity-receipt.json')
    source_report2 = read('artifacts/million-input-v2/dataset/report.json')
    cache = read('artifacts/million-v2-final/extraction-cache.json')
    diagnosis = read('artifacts/million-v2-final/error-causes.json')
    tables = []

    def table(headers, records):
        return '\n'.join(['| ' + ' | '.join(headers) + ' |',
                          '| ' + ' | '.join(['---'] * len(headers)) + ' |',
                          *['| ' + ' | '.join(map(str, row)) + ' |' for row in records]])

    rows = []
    for title, result in [('V1, gramatica V1', v1), ('V2, transfer strict V1', strict), ('V2, compatibilitate declarată', v2)]:
        for cohort, name in [('all', 'întregul pool'), ('provided', 'note furnizate'), ('pilot', 'pilot păstrat în protocolul original')]:
            m = result['metrics'][cohort]
            rows.append([title, name, m['counts']['rows'], m['counts']['label_rows'], m['counts']['correct'],
                         percent(m['accuracy']), percent(m['macro_f1']), percent(m['majority_baseline'])])
    tables.append(table(['Rulare', 'Subset', 'Rânduri', 'Etichete de adevăr', 'Corecte', 'Accuracy', 'Macro-F1', 'Majoritatea globală a subsetului'], rows))
    family_rows = []
    for group, versions in comparison['strata'].items():
        if not group.startswith('original_family:'):
            continue
        a, b = versions['v1'], versions['v2']
        family_rows.append([group.removeprefix('original_family:'), a['counts']['rows'], percent(a['accuracy']), percent(b['accuracy']),
                            f"{100 * (b['accuracy'] - a['accuracy']):+.4f}" if a['accuracy'] is not None else 'n/a'])
    tables.append(table(['Familia/grupul V1 original', 'Rânduri pereche', 'V1 accuracy', 'V2 compatibil accuracy', 'Diferență, puncte procentuale'], family_rows))
    label_rows = []
    for version, result in [('V1', v1), ('V2 compatibil', v2)]:
        for cohort in ['provided', 'pilot']:
            for label, values in result['metrics'][cohort]['per_label'].items():
                label_rows.append([version, cohort, label, values['support'], percent(values['precision']), percent(values['recall']), percent(values['f1'])])
    tables.append(table(['Rulare', 'Subset', 'Clasă', 'Suport', 'Precision', 'Recall', 'F1'], label_rows))
    parsing_rows = []
    for name, result in [('V1', v1), ('V2 strict', strict), ('V2 compatibil', v2)]:
        p = result['parsing']
        parsing_rows.append([name, p['provided_rows'], p['provided_protocol_parsed'], percent(p['provided_protocol_parsed'] / p['provided_rows']),
                             p['provided_exact_ast'], percent(p['provided_exact_ast'] / p['provided_rows']),
                             p['pilot_assertion_rows'], p['pilot_assertion_exact_context'], percent(p['pilot_assertion_exact_context'] / p['pilot_assertion_rows'])])
    tables.append(table(['Rulare', 'Cereri note', 'Gramatica acceptată', 'Acoperire gramaticală', 'AST proiectat exact', 'AST exact %', 'Pilot assertions', 'Pilot assertions exacte cu context', 'Pilot exact %'], parsing_rows))
    runtime_rows = []
    runtime_details = {}
    for folder, name in [('million-v1-final', 'V1'), ('million-v2-final', 'V2 compatibil')]:
        prep = read(f'artifacts/{folder}/preparation.json')
        planning = read(f'artifacts/{folder}/planning.json')
        result = read(f'artifacts/{folder}/score.json')
        parse = read(f'artifacts/{folder}/parse-run.json')
        compare = read(f'artifacts/{folder}/compare-run.json')
        text = (ROOT / f'artifacts/{folder}/parse-container.log').read_text(encoding='utf-8')
        runtime_details[name] = next(json.loads(line) for line in text.splitlines() if line.startswith('{') and 'neural_requests' in line)
        peak = re.search(r'BENCH_MEMORY_PEAK=(\d+)', text)
        runtime_rows.append([name, prep['counts']['rows'], prep['requests'], planning['typed_pairs'],
                             f"{prep['seconds']:.2f}", f"{parse['wall_seconds']:.2f}", f"{planning['seconds']:.2f}",
                             f"{compare['wall_seconds']:.2f}", f"{result['seconds_scoring']:.2f}",
                             f"{int(peak[1]) / 2**20:.2f}" if peak else 'n/a'])
    tables.append(table(['Rulare', 'Rânduri', 'Extrageri distincte totale', 'Perechi tipizate distincte', 'Pregătire s', 'Parsare Docker s', 'Planificare s', 'Comparații Docker s', 'Scoring s', 'Vârf cgroup parsare MiB'], runtime_rows))
    paired = comparison['counts']
    overlap = comparison['exact_public_input_overlap']
    majority_by_profile = sum(max(sum(m['confusion'][label].values()) for label in ('true', 'false', 'unsure'))
                              for name, m in v1['metrics'].items() if name.startswith('profile:') and name != 'profile:pilot')
    majority_by_profile /= v1['metrics']['provided']['counts']['label_rows']
    hashes = [
        ['Arhiva V1', '17194179b1e17cca148ba42c21a7c155c5556423938d352e8bda90ac0b8f852c'],
        ['Arhiva V2', archive2['sha256']], ['Model ONNX', freeze['model_sha256']],
        ['Verificator GBT', freeze['verifier_sha256']], ['Imagine Docker', freeze['image']],
    ]
    for name, value in freeze['files'].items():
        hashes.append([name.replace('\\', '/'), value])
    for name, value in extension['files'].items():
        hashes.append([name.replace('\\', '/'), value])
    hash_table = table(['Artefact', 'SHA-256 / identificator'], hashes)
    vocabulary_lf_hash = hashlib.sha256((ROOT / 'tools/million_evaluation/v2-language.json').read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    failures = []
    for key in ('fixed', 'regressed', 'still_wrong'):
        failures.append('### ' + {'fixed': 'Exemple corectate de rescriere/interfață', 'regressed': 'Exemple care regresează', 'still_wrong': 'Exemple încă greșite'}[key])
        for item in comparison['examples'][key][:3]:
            failures.append(f"\n- `{item['id']}` ({item['original_family']}): gold `{item['label']}`, V1 `{item['v1_prediction']}`, V2 `{item['v2_prediction']}`.\n  - V1: {item['v1_text']}\n  - V2: {item['v2_text']}")
    report = f'''# VERIDYCT: evaluare integrală million V1 și V2

Data: 29 octombrie 2026. Raport de dezvoltare, cu rezultate măsurate pe toate rândurile.
Soluția publicată înainte de testare: [main e6f687c](https://github.com/teodorbalan/VERIDYCT/commit/e6f687c95e018a3948b0a970325007523190cb43).

## Ce demonstrează rezultatele

Am procesat câte 1.000.000 de rânduri din fiecare arhivă. Pentru fiecare pool există
999.603 etichete de adevăr și 397 de cazuri numai pentru parsare, excluse explicit
din numitorul accuracy. Am validat și toate rețetele/proveniența folosind checkerele
originale ale fiecărei arhive, fără modificarea datelor sau a testelor.

V1: **{percent(v1['metrics']['all']['accuracy'])} agregat**, dar
**{percent(v1['metrics']['pilot']['accuracy'])} pe pilotul complet** și
**{percent(v1['metrics']['provided']['accuracy'])} pe logica sintetică a notelor furnizate**.
V2 cu extensia de limbaj declarată: **{percent(v2['metrics']['all']['accuracy'])} agregat**,
**{percent(v2['metrics']['provided']['accuracy'])} pe noul protocol de note**.

Acestea sunt scoruri ale unui **evaluator adaptat protocolului public**, cu modelele
înghețate; nu sunt accuracy a CLI-ului original pe un milion de afirmații independente.
Gramatica rendererului este cunoscută, sursele sunt derivate din practice, iar toate
rândurile sunt train-eligible și nesplitate. Nu am antrenat greutăți pe aceste pooluri.
Validarea umană de către Mihai rămâne neefectuată.

## Trei rulări distincte

{tables[0]}

Rularea strictă V1 pe V2 este păstrată: **{percent(strict['metrics']['all']['accuracy'])}**
agregat și **zero cereri rescrise recunoscute gramatical**. Adaptorul vechi se abține
la limbajul nou. Extensia compatibilă este o schimbare declarată a interfeței de
limbaj, nu transfer spontan al rețelei și nu dovada generalizării în engleză liberă.

Ponderea clasei majoritare diferă între profile. Pe tierul mare V1, un baseline care
știe profilul și alege clasa lui majoritară obține {percent(majority_by_profile)};
baseline-ul global singur nu descrie întreaga dificultate. Profilul nu este feature
al evaluatorului nostru.

## Ce schimbă V2

- {paired['changed_input_at_same_id']:,} intrări diferite la același ID; {paired['changed_target']:,} targeturi
  structurale schimbate; {paired['changed_ast']:,} AST-uri schimbate; **{paired['changed_label']} etichete de adevăr schimbate**.
- {paired['same_case_key']:,} grupuri de caz păstrate la aceleași ID-uri.
- Suprapunere exactă prin SHA-256 al întregului input public: **{overlap['rows']:,}**.
  Pe acestea: {overlap.get('changed_label', 0)} etichete și {overlap.get('changed_prediction', 0)} predicții schimbate.
- Rânduri cu label nenul: {paired['both_correct']:,} corecte în ambele,
  {paired['fixed']:,} corectate în V2, {paired['regressed']:,} regresii,
  {paired['both_wrong']:,} greșite în ambele.
- Schimbări de schemă: `{json.dumps(comparison['schema_transitions'], ensure_ascii=False)}`.

Numărul mediu de cuvinte scade de la {source_report2['mean_claim_words_before']:.2f}
la {source_report2['mean_claim_words_after']:.2f}, iar contextul mediu de la
{source_report2['mean_context_turns_before']:.2f} la {source_report2['mean_context_turns_after']:.2f} elemente.
V2 elimină wrapperul constant, repetările masive, contraste numerice nerealiste și
unele comparații între metrici fără legătură; schimbă și AST-ul acolo unde înlocuiește
întrebarea. ID egal nu înseamnă propoziție cu aceeași semnificație.

Pilotul complet V1 are 17.176 rânduri. În V2, 7.277 exemple temporale/comparații
trec la protocolul de note; rămân 9.899 în protocolul vechi, dintre care 9.502 cu
label nenul. De aceea procentele brute «pilot V1» și «pilot V2» nu compară același
subset. Tabelul următor păstrează familia originală și perechile de ID-uri.

{tables[1]}

## Erori, abținere și clase

{tables[2]}

În raportul JSON, `coverage` înseamnă proporția răspunsurilor definitive true/false,
nu proporția datelor procesate. `unsure` este o clasă validă și este verificată
față de eticheta așteptată. O abținere pe un true/false este o eroare în accuracy.
Probabilitățile GBT nu au fost calibrate pe acest set; accuracy mare nu le certifică.

### Regresia concretă: versiunea produsului și versiunea API

Am verificat structural **toate cele {diagnosis['counts']['error_rows']:,} erori** din
subsetul V2 de note. În {diagnosis['counts'].get('api_version_as_version', 0):,} dintre
ele, targetul cere `api_version`, iar textul a fost legat la atributul `version`.
Acest lucru include toate cele {diagnosis['definitive_counts']['error_rows']} erori
definitive; celelalte 1.870 sunt abțineri. Scorurile de mai sus sunt păstrate intacte.

Exemplu verificat: `p-1454`, 14 noiembrie 2025, spune «Hooly Gemini speaks version 1
of the interface» și are `api_version = 1`. În aceeași zi, `p-1452` descrie versiunea
produsului `1.0`. V2 poate formula ambele ca «Hooly Gemini runs version ...», fără
«API» sau «interface». În `million-13-022926`, ambele note sunt în context.
Adaptorul declară că versiunea necalificată denotă `version`; targetul cere însă
`api_version` pentru una dintre clauze. Problema este la distincția atributelor,
nu la ordonarea sau aritmetica versiunilor.

Acesta este un diagnostic verificabil al nepotrivirii text/atribut. Pentru următoarea
revizie trebuie păstrat explicit «API/interface version» și măsurat din nou;
alternativ, parserul poate reține candidații ambigui și rezolva numai când contextul
îi deosebește. Nu recomand o regulă memorată «1 = API, 1.0 = produs». Nu am rescris
arhiva și nu am reparat parserul după scor pentru a prezenta artificial 100%.

ID-urile celor nouă erori definitive: `{', '.join(diagnosis['definitive_ids'])}`.
Reproducere: `py -3.14 tools/million_evaluation/diagnose.py --run artifacts/million-v2-final`.

Comparat global, accuracy crește, dar macro-F1 scade de la
{percent(v1['metrics']['all']['macro_f1'])} la {percent(v2['metrics']['all']['macro_f1'])}.
V2 nu îmbunătățește uniform toate clasele și familiile. Pe subsetul identic de
inputuri nu se schimbă nicio predicție; modelele sunt aceleași.

## Parsare

{tables[3]}

AST-ul proiectat verifică tipurile de nod, ordinea, operatorii, subiectul,
atributul, data, valoarea tipizată și legăturile source ID. Nu verifică offseturile
caracterelor/reference spans. Pentru pilot se verifică numai subsetul plat
`assertions`, nu se pretinde suport complet pentru toate structurile sale.
Identificatorul unei surse numite poate lipsi din input dacă nota este reținută;
evaluatorul nu inventează sursa din audit. V1 are și literaluri de nume implauzibile
precum «Hooly's headquarters is Hooly», la care parserul conservator se abține.

V1, pilot: fără context {percent(v1['metrics']['pilot_no_context']['accuracy'])},
cu ultimele trei texte explicit furnizate {percent(v1['metrics']['pilot']['accuracy'])}.
Contextul este o ablație declarată, nu adjacency presupusă din CSV. Encoderul
înghețat are propriile limite de tokeni; trei texte nu garantează acces la orice
antecedent îndepărtat.

## Algoritmul folosit efectiv

1. Parser de protocol limitat: all/any/not, nume/date explicite, declarații ordinal
   «note one». Extensia V2 recunoaște propoziții/fragmente și precedența frazelor
   specifice în fața celor generice. Vocabularul public și proveniența sunt versionate.
2. Extracție tipizată: modelul CharCNN/BiLSTM ONNX selected-v2 + binderul Rust.
   Literalurile canonice rezolvate complet folosesc direct gramatica existentă.
   Notele care corespund practice la aceeași dată pot reutiliza formele publice;
   lookup-ul normalizează NFKC, literele mari/mici și spațiile.
3. Indexarea fiecărui input: numai notele `role=evidence` furnizate acelui rând sunt
   disponibile. Cache-ul unui alt rând nu introduce o dovadă lipsă.
4. Comparații exacte: recorded = egalitate literală cu metadate; compare = aritmetică
   exactă și conversii compatibile. Datele parțiale ca valori au adaptor de intervale
   separat de semantica predicatelor temporale din aplicația de producție.
   V1 permite și magnitudini din metrici diferite, cu metadate compatibile; respectăm
   contractul sintetic, fără a pretinde comparabilitate economică. V2 înlocuiește
   o parte dintre aceste întrebări cu afirmații separate despre surse.
5. Logică cu trei valori și short-circuit: false AND unknown = false;
   true OR unknown = true. Lipsa dovezii nu se transformă automat în false.
6. Pilotul vechi folosește clasificatorul GBT de producție pe extragerile parserului,
   cu variante fără context/cu context. Nu am introdus un nou clasificator antrenat.

Nu rulează un LLM, un GNN nou sau un serviciu extern. Python este harness de
dezvoltare pentru protocolul extins, nu aplicația Rust trimisă în competiție.
Taskul 2 de generare nu este ținta acestor pooluri: nu există aici un milion de
cereri pentru generarea celor 1.000 de afirmații. Checkerul Docker de format al
soluției integrate a trecut separat; acest benchmark nu măsoară calitatea lui Task 2.

## Înghețare și prevenirea contaminării

- V1 înghețat la `{freeze['frozen_at_utc']}`, înaintea scorului complet.
- Extensia V2 înghețată la `{extension['frozen_at_utc']}`, după probe numai pe input
  și înaintea scorului complet compatibil; scorul V1 era deja cunoscut. Adaptare de
  dezvoltare declarată, fără afirmație de test lingvistic blind.
- Toate fișierele înghețate V1 au rămas identice. Extensia produce exact aceleași
  cereri, planuri decomprimate și practice CSV pe toate cele 1.000.000 de intrări V1.
- Targets/metadata/audit sunt separate în `scoring/`; containerul de inferență
  primește exclusiv `features/`, datele practice publice și modelele înghețate.
- Fără bank/oracle/target montate în inferență. Oracle-ul arhivei este folosit doar
  de testul diferențial separat și de checkerul original al datelor.
- Reutilizare V2: {cache['cached_extraction']:,} extrageri identice, {cache['new_extraction']:,}
  cereri noi, din {cache['total']:,} totale distincte. Cheia: mode + text complet +
  dată + contextul anterior complet. Nu se reutilizează disponibilitatea dovezii.

## Resurse și durate

Host: AMD Ryzen 9 6900HS, 8 nuclee/16 fire; Docker Linux x86_64, 16 vCPU vizibile,
7.919.030.272 bytes memorie VM. Inferență: release Rust, Rust 1.90, două CPU,
maximum șase GiB, UID 10001, rețea oprită, filesystem root read-only.

{tables[4]}

Parsarea V2 măsoară numai cererile noi, cele identice fiind preluate din cache.
V1 a executat {runtime_details['V1']['neural_requests']:,} cereri neuronale distincte.
V2 a avut {runtime_details['V2 compatibil']['requests']:,} cereri noi și
{runtime_details['V2 compatibil']['neural_requests']} execuții neuronale noi: gramatica
tipizată existentă le-a rezolvat complet. Restul sunt extrageri identice reutilizate,
nu un model neural devenit mai bun fără antrenare.
Duratele de pregătire/scoring sunt pe host; verificarea arhivei și alte operații
au rulat concomitent. Acestea sunt măsurători de rulare, nu benchmark izolat de
latență. Cache-ul face accesibile un milion de combinații cu mult mai puține
extrageri distincte; nu susțin un milion de inferențe neuronale în acest timp.
Verificarea integrală V2 a ieșit cu cod {integrity2['exit_code']} în
{integrity2['seconds']:.2f} secunde, incluzând pornirea/downloadul inițial al imaginii.

## Verificări și limite păstrate

| Verificare | Rezultat |
| --- | --- |
| Main înainte de arhive | 79 teste workspace, Clippy, checksumuri organizer, checker Docker real: trecute |
| Replay original V1 | 1.000.000/1.000.000, hashuri/registru/oracle/rețete: trecute |
| Replay original V2 | 1.000.000/1.000.000, rescrieri/oracle/hashuri/registru: trecute |
| Teste generator/oracle V1 | 16/16 trecute |
| Teste generator/oracle V2 | 16/16 trecute |
| Teste revizie V2 | 8/8 trecute, cu căile publice REVIEW_BANK/REVIEW_SAMPLE configurate |
| Teste pilot legacy, ambele arhive | 12/13: volumul așteptat 20.000 diferă de 17.176 livrate |
| Teste adaptor | 12/12 trecute |
| Kernel vs oracle, numai test | 20.723 comparații, zero neconcordanțe |
| Bridge Rust | Clippy all-targets cu -D warnings și testul date-range: trecute |
| Paritate adaptor extins pe V1 | Toate planurile și cererile identice |
| Review uman Mihai | Neefectuat; reviewul editorial din V2 este făcut de Codex |

Pe Windows, checkerul V1 cere modulul Unix `resource`; validarea reală s-a rulat în
Linux. Testele V2 au căi implicite către calculatorul autorului; au fost folosite
variabilele suportate, fără editarea testelor. Eșecul legacy de volum nu a fost
ascuns prin modificarea fixturelor. Cele 397 de labeluri null rămân cazuri de parsare.

Tierul mare folosește 457 de rânduri-sursă originale, cu o observație canonică
duplicată, 51 de subiecte și 224 de sloturi; pilotul extinde totalul la 62 de
subiecte și 514 sloturi. Un split random pe rânduri ar scurge surse, șabloane și
cazuri înrudite. Scorurile de mai sus nu înlocuiesc evaluarea independentă deja
măsurată a candidatului și nu promit scorul ascuns al competiției.
Pentru aplicația completă, referința anterioară rămâne 87,74% pe 5.000 și 87,58%
pe 20.000 de ținte din lumi independente înghețate, tot în limbaj controlat; vezi
`docs/handoffs/evidence-graph-runtime.md`. Nu înlocuiesc acele măsurători cu scorul
mai mare al adaptorului specializat de aici.

## Exemple pereche pentru diagnostic

{chr(10).join(failures)}

## Ce merită îmbunătățit în continuare

Prioritatea este suportul nativ pentru structurile de comparație și observațiile
temporale ale pilotului, plus rezolvarea antecedentelor îndepărtate cu limite de
document explicite. Etapa neurală de extracție și tipurile pe care le poate produce
rămân mai relevante pentru competiție decât memorarea gramaticii acestui pool.
Un test nou ar trebui separat pe surse/documente și familii înainte de generare,
cu parafraze umane independente și review efectiv. Perfecționarea pe aceste erori
devine dezvoltare și trebuie măsurată ulterior pe alt set păstrat separat.

## Proveniență și reproducere

Arhive locale: `Downloads/veridyct-million.zip` și
`Downloads/veridyct-million-v2.zip`. Fișiere citite: README-urile lor,
`dataset/manifest.json`, `dataset/report.json`, poolul complet, checkerele originale,
vocabularul public, lexiconul și datele practice. Rezultatele evaluatorului provin
din fișierele ignorate `artifacts/million-v1-final/score.json`,
`artifacts/million-v2-frozen/score.json`, `artifacts/million-v2-final/score.json`
și `artifacts/million-comparison/comparison.json` din checkout-ul de evaluare.
Rapoartele, freeze receipts, logurile și predicțiile per rând sunt păstrate local;
arhivele, greutățile și binarele nu intră în Git.

Comenzile de reproducere sunt în `tools/million_evaluation/README.md`.
Sursa implementării de bază este commitul main e6f687c; adaptorul și raportul sunt
livrate prin commitul separat al acestei sarcini. Docker image și binarele exacte
folosite sunt identificate mai jos; sursa finală a bridge-ului reproduce ambele
comenzi, cu extensia date-value descrisă explicit.

{hash_table}

Hashul cererilor V1 este `{parity['requests.jsonl']['v1_sha256']}`;
hashul planurilor decomprimate V1 este `{parity['plans.jsonl.gz']['v1_sha256']}`.
Lexiconul, practice CSV și render-contract sunt identice între arhive.
Hashurile sursei descriu bytes locali la înghețare. `v2-language.json` avea CRLF
pe Windows; Git normalizează acest text la LF, fără schimbarea JSON-ului sau a
regulilor. SHA-256 cu LF pentru reproducere din Git: `{vocabulary_lf_hash}`.
'''
    output = ROOT / 'docs/research/million-v1-v2.md'
    output.write_text(report, encoding='utf-8')
    print(output)
    print('bytes', len(report.encode('utf-8')))


if __name__ == '__main__':
    main()
