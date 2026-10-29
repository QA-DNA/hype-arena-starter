# VERIDYCT: evaluare integrală million V1 și V2

Data: 29 octombrie 2026. Raport de dezvoltare, cu rezultate măsurate pe toate rândurile.
Soluția publicată înainte de testare: [main e6f687c](https://github.com/teodorbalan/VERIDYCT/commit/e6f687c95e018a3948b0a970325007523190cb43).

## Ce demonstrează rezultatele

Am procesat câte 1.000.000 de rânduri din fiecare arhivă. Pentru fiecare pool există
999.603 etichete de adevăr și 397 de cazuri numai pentru parsare, excluse explicit
din numitorul accuracy. Am validat și toate rețetele/proveniența folosind checkerele
originale ale fiecărei arhive, fără modificarea datelor sau a testelor.

V1: **99.5419% agregat**, dar
**74.3250% pe pilotul complet** și
**99.9724% pe logica sintetică a notelor furnizate**.
V2 cu extensia de limbaj declarată: **99.7458% agregat**,
**99.8102% pe noul protocol de note**.

Acestea sunt scoruri ale unui **evaluator adaptat protocolului public**, cu modelele
înghețate; nu sunt accuracy a CLI-ului original pe un milion de afirmații independente.
Gramatica rendererului este cunoscută, sursele sunt derivate din practice, iar toate
rândurile sunt train-eligible și nesplitate. Nu am antrenat greutăți pe aceste pooluri.
Validarea umană de către Mihai rămâne neefectuată.

## Trei rulări distincte

| Rulare | Subset | Rânduri | Etichete de adevăr | Corecte | Accuracy | Macro-F1 | Majoritatea globală a subsetului |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V1, gramatica V1 | întregul pool | 1000000 | 999603 | 995024 | 99.5419% | 99.5737% | 49.3552% |
| V1, gramatica V1 | note furnizate | 982824 | 982824 | 982553 | 99.9724% | 99.9270% | 49.2206% |
| V1, gramatica V1 | pilot păstrat în protocolul original | 17176 | 16779 | 12471 | 74.3250% | 60.3034% | 57.2382% |
| V2, transfer strict V1 | întregul pool | 1000000 | 999603 | 80795 | 8.0827% | 5.7406% | 49.3552% |
| V2, transfer strict V1 | note furnizate | 990101 | 990101 | 71955 | 7.2674% | 4.5167% | 49.1811% |
| V2, transfer strict V1 | pilot păstrat în protocolul original | 9899 | 9502 | 8840 | 93.0330% | 74.5005% | 67.4911% |
| V2, compatibilitate declarată | întregul pool | 1000000 | 999603 | 997062 | 99.7458% | 99.4227% | 49.3552% |
| V2, compatibilitate declarată | note furnizate | 990101 | 990101 | 988222 | 99.8102% | 99.5045% | 49.1811% |
| V2, compatibilitate declarată | pilot păstrat în protocolul original | 9899 | 9502 | 8840 | 93.0330% | 74.5005% | 67.4911% |

Rularea strictă V1 pe V2 este păstrată: **8.0827%**
agregat și **zero cereri rescrise recunoscute gramatical**. Adaptorul vechi se abține
la limbajul nou. Extensia compatibilă este o schimbare declarată a interfeței de
limbaj, nu transfer spontan al rețelei și nu dovada generalizării în engleză liberă.

Ponderea clasei majoritare diferă între profile. Pe tierul mare V1, un baseline care
știe profilul și alege clasa lui majoritară obține 73.6941%;
baseline-ul global singur nu descrie întreaga dificultate. Profilul nu este feature
al evaluatorului nostru.

## Ce schimbă V2

- 990,101 intrări diferite la același ID; 827,042 targeturi
  structurale schimbate; 445,023 AST-uri schimbate; **0 etichete de adevăr schimbate**.
- 1,000,000 grupuri de caz păstrate la aceleași ID-uri.
- Suprapunere exactă prin SHA-256 al întregului input public: **9,899**.
  Pe acestea: 0 etichete și 0 predicții schimbate.
- Rânduri cu label nenul: 993,148 corecte în ambele,
  3,914 corectate în V2, 1,876 regresii,
  665 greșite în ambele.
- Schimbări de schemă: `{"annotated_practice_v1 -> annotated_practice_v1": 9899, "annotated_practice_v1 -> provided_notes_logic_v2": 7277, "provided_notes_logic_v1 -> provided_notes_logic_v2": 982824}`.

Numărul mediu de cuvinte scade de la 74.18
la 56.41, iar contextul mediu de la
8.74 la 5.03 elemente.
V2 elimină wrapperul constant, repetările masive, contraste numerice nerealiste și
unele comparații între metrici fără legătură; schimbă și AST-ul acolo unde înlocuiește
întrebarea. ID egal nu înseamnă propoziție cu aceeași semnificație.

Pilotul complet V1 are 17.176 rânduri. În V2, 7.277 exemple temporale/comparații
trec la protocolul de note; rămân 9.899 în protocolul vechi, dintre care 9.502 cu
label nenul. De aceea procentele brute «pilot V1» și «pilot V2» nu compară același
subset. Tabelul următor păstrează familia originală și perechile de ID-uri.

| Familia/grupul V1 original | Rânduri pereche | V1 accuracy | V2 compatibil accuracy | Diferență, puncte procentuale |
| --- | --- | --- | --- | --- |
| bundles | 3805 | 88.4888% | 88.4888% | +0.0000 |
| adversarial | 4000 | 97.3078% | 97.3078% | +0.0000 |
| references | 2094 | 93.9351% | 93.9351% | +0.0000 |
| temporal | 1616 | 57.9208% | 99.7525% | +41.8317 |
| comparisons | 5661 | 47.6064% | 100.0000% | +52.3936 |
| profile-1 | 49142 | 99.9919% | 99.7782% | -0.2137 |
| profile-2 | 49142 | 99.9735% | 99.7680% | -0.2055 |
| profile-3 | 49142 | 99.9878% | 99.9044% | -0.0834 |
| profile-4 | 49142 | 99.9858% | 99.9023% | -0.0834 |
| profile-5 | 49141 | 100.0000% | 99.9227% | -0.0773 |
| profile-6 | 49141 | 99.9756% | 99.2857% | -0.6899 |
| profile-7 | 49141 | 99.9491% | 99.8637% | -0.0855 |
| profile-8 | 49141 | 99.9898% | 99.8331% | -0.1567 |
| profile-9 | 49141 | 99.9980% | 99.9186% | -0.0794 |
| profile-10 | 49141 | 99.9654% | 99.8209% | -0.1445 |
| profile-11 | 49141 | 99.9532% | 99.8230% | -0.1302 |
| profile-12 | 49141 | 99.9044% | 99.8799% | -0.0244 |
| profile-13 | 49141 | 100.0000% | 99.7660% | -0.2340 |
| profile-14 | 49141 | 99.9756% | 99.8921% | -0.0834 |
| profile-15 | 49141 | 100.0000% | 99.8840% | -0.1160 |
| profile-16 | 49141 | 99.9593% | 99.7375% | -0.2218 |
| profile-17 | 49141 | 99.9980% | 99.6581% | -0.3398 |
| profile-18 | 49141 | 99.8433% | 99.8698% | +0.0265 |
| profile-19 | 49141 | 99.9980% | 99.8759% | -0.1221 |
| profile-20 | 49141 | 100.0000% | 99.8006% | -0.1994 |

## Erori, abținere și clase

| Rulare | Subset | Clasă | Suport | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- |
| V1 | provided | true | 483752 | 100.0000% | 99.9878% | 99.9939% |
| V1 | provided | false | 427117 | 100.0000% | 99.9504% | 99.9752% |
| V1 | provided | unsure | 71955 | 99.6248% | 100.0000% | 99.8120% |
| V1 | pilot | true | 9604 | 76.0332% | 81.0287% | 78.4515% |
| V1 | pilot | false | 6966 | 72.1582% | 66.5231% | 69.2262% |
| V1 | pilot | unsure | 209 | 45.0820% | 26.3158% | 33.2326% |
| V2 compatibil | provided | true | 486943 | 99.9990% | 99.7470% | 99.8728% |
| V2 compatibil | provided | false | 431203 | 99.9991% | 99.8504% | 99.9247% |
| V2 compatibil | provided | unsure | 71955 | 97.4669% | 99.9972% | 98.7159% |
| V2 compatibil | pilot | true | 6413 | 93.7994% | 96.2420% | 95.0050% |
| V2 compatibil | pilot | false | 2880 | 92.2018% | 90.7292% | 91.4596% |
| V2 compatibil | pilot | unsure | 209 | 62.5000% | 26.3158% | 37.0370% |

În raportul JSON, `coverage` înseamnă proporția răspunsurilor definitive true/false,
nu proporția datelor procesate. `unsure` este o clasă validă și este verificată
față de eticheta așteptată. O abținere pe un true/false este o eroare în accuracy.
Probabilitățile GBT nu au fost calibrate pe acest set; accuracy mare nu le certifică.

### Regresia concretă: versiunea produsului și versiunea API

Am verificat structural **toate cele 1,879 erori** din
subsetul V2 de note. În 1,879 dintre
ele, targetul cere `api_version`, iar textul a fost legat la atributul `version`.
Acest lucru include toate cele 9 erori
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

ID-urile celor nouă erori definitive: `million-05-001097, million-05-001100, million-09-038123, million-13-022926, million-13-032143, million-13-032144, million-13-042221, million-13-043668, million-17-003199`.
Reproducere: `py -3.14 tools/million_evaluation/diagnose.py --run artifacts/million-v2-final`.

Comparat global, accuracy crește, dar macro-F1 scade de la
99.5737% la 99.4227%.
V2 nu îmbunătățește uniform toate clasele și familiile. Pe subsetul identic de
inputuri nu se schimbă nicio predicție; modelele sunt aceleași.

## Parsare

| Rulare | Cereri note | Gramatica acceptată | Acoperire gramaticală | AST proiectat exact | AST exact % | Pilot assertions | Pilot assertions exacte cu context | Pilot exact % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | 982824 | 982824 | 100.0000% | 900405 | 91.6141% | 9502 | 7678 | 80.8040% |
| V2 strict | 990101 | 0 | 0.0000% | 0 | 0.0000% | 9502 | 7678 | 80.8040% |
| V2 compatibil | 990101 | 990101 | 100.0000% | 828018 | 83.6296% | 9502 | 7678 | 80.8040% |

AST-ul proiectat verifică tipurile de nod, ordinea, operatorii, subiectul,
atributul, data, valoarea tipizată și legăturile source ID. Nu verifică offseturile
caracterelor/reference spans. Pentru pilot se verifică numai subsetul plat
`assertions`, nu se pretinde suport complet pentru toate structurile sale.
Identificatorul unei surse numite poate lipsi din input dacă nota este reținută;
evaluatorul nu inventează sursa din audit. V1 are și literaluri de nume implauzibile
precum «Hooly's headquarters is Hooly», la care parserul conservator se abține.

V1, pilot: fără context 73.8363%,
cu ultimele trei texte explicit furnizate 74.3250%.
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

- V1 înghețat la `2026-10-29T04:28:32.130706+00:00`, înaintea scorului complet.
- Extensia V2 înghețată la `2026-10-29T04:40:57.740077+00:00`, după probe numai pe input
  și înaintea scorului complet compatibil; scorul V1 era deja cunoscut. Adaptare de
  dezvoltare declarată, fără afirmație de test lingvistic blind.
- Toate fișierele înghețate V1 au rămas identice. Extensia produce exact aceleași
  cereri, planuri decomprimate și practice CSV pe toate cele 1.000.000 de intrări V1.
- Targets/metadata/audit sunt separate în `scoring/`; containerul de inferență
  primește exclusiv `features/`, datele practice publice și modelele înghețate.
- Fără bank/oracle/target montate în inferență. Oracle-ul arhivei este folosit doar
  de testul diferențial separat și de checkerul original al datelor.
- Reutilizare V2: 18,649 extrageri identice, 244
  cereri noi, din 18,893 totale distincte. Cheia: mode + text complet +
  dată + contextul anterior complet. Nu se reutilizează disponibilitatea dovezii.

## Resurse și durate

Host: AMD Ryzen 9 6900HS, 8 nuclee/16 fire; Docker Linux x86_64, 16 vCPU vizibile,
7.919.030.272 bytes memorie VM. Inferență: release Rust, Rust 1.90, două CPU,
maximum șase GiB, UID 10001, rețea oprită, filesystem root read-only.

| Rulare | Rânduri | Extrageri distincte totale | Perechi tipizate distincte | Pregătire s | Parsare Docker s | Planificare s | Comparații Docker s | Scoring s | Vârf cgroup parsare MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | 1000000 | 34279 | 12531 | 161.01 | 236.94 | 76.50 | 0.72 | 58.34 | 3636.73 |
| V2 compatibil | 1000000 | 18893 | 6113 | 1046.13 | 5.85 | 74.10 | 0.83 | 65.60 | 107.80 |

Parsarea V2 măsoară numai cererile noi, cele identice fiind preluate din cache.
V1 a executat 31,959 cereri neuronale distincte.
V2 a avut 244 cereri noi și
0 execuții neuronale noi: gramatica
tipizată existentă le-a rezolvat complet. Restul sunt extrageri identice reutilizate,
nu un model neural devenit mai bun fără antrenare.
Duratele de pregătire/scoring sunt pe host; verificarea arhivei și alte operații
au rulat concomitent. Acestea sunt măsurători de rulare, nu benchmark izolat de
latență. Cache-ul face accesibile un milion de combinații cu mult mai puține
extrageri distincte; nu susțin un milion de inferențe neuronale în acest timp.
Verificarea integrală V2 a ieșit cu cod 0 în
712.29 secunde, incluzând pornirea/downloadul inițial al imaginii.

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

### Exemple corectate de rescriere/interfață

- `temporal-f4c5d856f6a01c28beaddb0b` (temporal): gold `true`, V1 `false`, V2 `true`.
  - V1: In the note dated 24 April 2026, the entry for Hooly Maps Day's keynote speaker reads Jian-Yeng; in the note dated 2 July 2026, that entry reads Jian-Yeng.
  - V2: According to the 24 April 2026 note, Jian-Yeng gives the keynote at Hooly Maps Day. From the note dated 2 July 2026: Jian-Yeng gives the keynote at Hooly Maps Day.

- `temporal-ff9ac1885550db404c8d0890` (temporal): gold `true`, V1 `false`, V2 `true`.
  - V1: In the note dated 12 January 2026, the entry for Hooly Devices's german premium phone share reads 1.6%; in the note dated 30 June 2026, that entry reads 2.9%.
  - V2: The 12 January 2026 note says german premium phone share for Hooly Devices: 1.6%. From the note dated 30 June 2026: Hooly Devices, german premium phone share: 2.9%. I wrote this on the back of a receipt.

- `comparisons-9a7868038051372e7e4d21db` (comparisons): gold `true`, V1 `false`, V2 `true`.
  - V1: I compared the net zero date recorded for Hooly Sustainability Report on 24 September 2026 with the joining date recorded for Erlich Bachmann on 31 March 2026. The first value is later than the second.
  - V2: The net zero date for Hooly Sustainability Report reported on 24 September 2026 is later than the joining date for Erlich Bachmann reported on 31 March 2026.
### Exemple care regresează

- `temporal-167ff45373aa98a61e189fd5` (temporal): gold `false`, V1 `false`, V2 `unsure`.
  - V1: I read the two dated notes for Hooly Gemini: on 14 November 2025, the entry for api version reads version 1; on 20 August 2026, that entry reads version 3.
  - V2: The 14 November 2025 note says Hooly Gemini is on version 1. Hooly Gemini runs version 3, as reported on 20 August 2026.

- `temporal-562e6adf3a3bda660a85b327` (temporal): gold `false`, V1 `false`, V2 `unsure`.
  - V1: The entry for Hooly Gemini's api version reads version 2 in the note of 20 August 2026, and version 2 in the note of 14 November 2025.
  - V2: According to the 14 November 2025 note, Hooly Gemini is on version 2. According to the 20 August 2026 note, Hooly Gemini is on version 2. The washing machine has eaten another sock.

- `million-01-000313` (profile-1): gold `true`, V1 `true`, V2 `unsure`.
  - V1: Using only the supplied notes, all of these statements are true: (the entry for Hooly Devices's german premium phone share in the note of 12 January 2026 reads 1.6%); (the entry for Hooly Gemini's api version in the note of 20 August 2026 reads version 2); (the entry for Hooly Workspace Enterprise's audit retention in the note of 6 October 2026 reads 180 days). I am drinking espresso while reading this.
  - V2: From the note dated 12 January 2026: Hooly Devices, german premium phone share: 1.6%. Hooly Gemini runs version 2, as reported on 20 August 2026. According to the 6 October 2026 note, Hooly Workspace Enterprise keeps audit logs for 180 days. The lift stopped on every floor.
### Exemple încă greșite

- `bundles-88b2c17c3f995d0a60b2e956` (bundles): gold `true`, V1 `false`, V2 `false`.
  - V1: Operating margin, Hooly's Q1 results: 11.8%
14.2% operating margin in Hooly's Q2 results
Hooly's Q3 results closed at 15.7% margin
  - V2: Operating margin, Hooly's Q1 results: 11.8%
14.2% operating margin in Hooly's Q2 results
Hooly's Q3 results closed at 15.7% margin

- `bundles-bc9c34fb58af92cfb605dc40` (bundles): gold `unsure`, V1 `true`, V2 `true`.
  - V1: Hooly Android 17 beta starts today, 3 September 2025
Stable is planned for 8 September 2026
Trade in an old phone for up to up to €200
Hooly Pixel 10 is €799 today and ships on 14 May 2026.
  - V2: Hooly Android 17 beta starts today, 3 September 2025
Stable is planned for 8 September 2026
Trade in an old phone for up to up to €200
Hooly Pixel 10 is €799 today and ships on 14 May 2026.

- `adversarial-0d56579df171e038a096e1b6` (adversarial): gold `unsure`, V1 `true`, V2 `true`.
  - V1: The Hooly Board is due back at the table on 16 June 2026. There are 74 teaspoons in the drawer, somehow all different.
  - V2: The Hooly Board is due back at the table on 16 June 2026. There are 74 teaspoons in the drawer, somehow all different.

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

| Artefact | SHA-256 / identificator |
| --- | --- |
| Arhiva V1 | 17194179b1e17cca148ba42c21a7c155c5556423938d352e8bda90ac0b8f852c |
| Arhiva V2 | 416f95c6ab39a8b217e7aa1bad954b93134d75cb20f7f065c319cd71e4c3ecef |
| Model ONNX | 98eebdb851849f689c60499a9f4b2514305d520a523816b0505e98bba4523b6f |
| Verificator GBT | 007d278c95e5cffc785efb89a66ca0b2d2b9428b74f02986798dd2da716c8f59 |
| Imagine Docker | sha256:4fa26b584fc41af6c73e056d55b76bc1f96a3ff22f159c30809c8fc562d271a3 |
| tools/million_evaluation/bench.py | a8c5e9b4a4c01b22efaac12bbde7582f28b295a3c9c6898a2ac43f0857721ed2 |
| tools/million_evaluation/check_kernel.py | feffbe69929e6119ad81cf479fe05c7301f70679a2ef2f8cf04c0aaa5ca5b604 |
| tools/million_evaluation/protocol.py | 21bb33cce78aecb363a91bb968cda986b75b4fb7657be1e65fbaf93b2d523349 |
| tools/million_evaluation/reuse_parses.py | 05fc09ceb151ca43e0b8b3b2ba26e90e4d46982c8d51c7c5a7420be02406e271 |
| tools/million_evaluation/run_bridge.py | 83de5789c9e7b4bbf1bdd637a7d52566eaa0b240befe975731d86a0531feb051 |
| tools/million_evaluation/test_protocol.py | fe3ef2992f97ae0efacaf30a80667142df03b213d97366467c1fe3e4e36868fb |
| tools/million_evaluation/bridge/src/main.rs | c17818a63e6231d5208ce6856eaa2d23e529a9d7d37aee144e77a8d45ae8cc31 |
| tools/million_evaluation/bridge/Cargo.lock | a7902bb44fa0d85da9b599dd72c5f550879c5d748d3980854a21c52183f3ba7b |
| artifacts/million-runtime/bin/bridge | 5bcea73d6e4afe5bb2a54d4a813637531f279a46c8ff9ba39c5978d9d065c4b3 |
| artifacts/million-runtime/bin/bridge-compare | f3862afaf12fda0b4c038e03e48ce33ddb3360cbda961856d3205aab7a63c868 |
| tools/million_evaluation/protocol_v2.py | cc50ef26bd23f7680ecaac2a5af6bc0e233ee807f537be0b5fa2df3449a6562f |
| tools/million_evaluation/bench_v2.py | 678ce137fabe9ed3f52d76cb43773135e0439e6ea1a256087069c089a12fbbf6 |
| tools/million_evaluation/v2-language.json | 66c995239f238ab4f485d16cdb1f330fbcdd83be1a13a99bd715e76cf9fd382d |
| tools/million_evaluation/test_protocol_v2.py | cc4add76ce85b342c0e8863d0ee89cf054e4af3994ef243a4c76398cc380c645 |

Hashul cererilor V1 este `bf3f87674022ef73675eba2b2d5dbee131d5af95723ea3b75cb521101c2d18c7`;
hashul planurilor decomprimate V1 este `27e14c8459b6cc5aaf4555a310dbfba91f8de5f1c23a6d3b52c41d0a21b7cf7b`.
Lexiconul, practice CSV și render-contract sunt identice între arhive.
Hashurile sursei descriu bytes locali la înghețare. `v2-language.json` avea CRLF
pe Windows; Git normalizează acest text la LF, fără schimbarea JSON-ului sau a
regulilor. SHA-256 cu LF pentru reproducere din Git: `956f63833508af75325ff61e4c9126fb3d0f223e44c638c9a4ff0c6f7c9387cb`.
