# Video pitch / 180 de secunde

Text vorbit în engleză, instrucțiuni de filmare în română. Duratele de mai jos sunt bugete de montaj, nu o măsurare a unei înregistrări existente. Repetați cu cronometru. Textul „Spoken” este singurul text care se citește; notele și variantele nu se adaugă peste el.

Sample oficial: [datasets/sample.csv](https://github.com/QA-DNA/hype-arena-starter/blob/main/datasets/sample.csv), 20 de rânduri fără etichete. Fișierul de demo din aplicație este un alt fișier.

## 00:00–00:20 / Problema

Cadru: două documente ilustrative cu prețuri diferite și date explicite. Eticheta `Illustrative business scenario` rămâne vizibilă.

**Spoken:**

> A price changes. The old offer stays in a presentation, a support article and somebody's next email. Before sending it, someone has to find which source applies and what the evidence supports. We built VERIDYCT to make that review easier to inspect.

## 00:20–00:45 / Mecanismul

Cadru: diagrama configurației folosite. Dacă browserul nu a fost unificat, folosiți varianta de mai jos. Arătați pe scurt entity, attribute, value, unit, time.

**Spoken:**

> We work inside the supplied Hooly universe. Text becomes typed assertions: an entity, an attribute, a value, its unit and context. Evidence links them to source rows and dates. We chose Rust for native CPU execution and memory control. Our competition pipeline uses learned verification, without a runtime LLM.

## 00:45–01:35 / Rularea reală

Cadru: selectați CSV-ul oficial, apoi `Run pipeline`. Păstrați tranziția reală la rezultate. Deschideți un rând cu text, dată, explicație și surse lizibile. Nu acoperiți rezultatul cu subtitrări.

**Spoken:**

> Here is the official twenty-row sample. Its labels are empty, so this demonstration has no answer key. I upload the file and start the pipeline. These are the results of this run. Opening a row exposes the statement, its date, extracted facts and attached source observations. We can inspect what the system used and where support is missing. An unsure result remains a case for review. The displayed confidence is a model score, not measured accuracy on this sample.

## 01:35–01:55 / Generare și redundanță

Cadru: `Generated claims`, o afirmație deschisă și exportul. Numărul se vede din aplicație; nu îl suprascrieți prin grafică dacă rularea produce alt rezultat.

**Spoken:**

> The generator constructs new claims from accepted evidence. It removes duplicates and uses MMR to balance support with diversity, so similar statements do not consume the selection. MMR chooses among candidates; it does not prove them true. We can export the structured results.

## 01:55–02:25 / Ce am măsurat

Cadru: cifra 87.58%, 20.000 ținte, eticheta `Frozen candidate / synthetic evaluation`. Apoi două coloane V1 și V2, un milion de rânduri fiecare, eticheta `Related development cohorts`.

**Spoken:**

> A separate frozen candidate reached 87.58 percent accuracy on twenty thousand targets from a fresh synthetic world. We also evaluated two versions of a one-million-row development suite. Their cases are related and use declared protocol handling. We did not train model weights on those pools. These results describe those experiments, not accuracy on the organizer's hidden data or a customer's documents.

## 02:25–03:00 / Utilitatea propusă

Cadru: product operations, draft verificat, aprobare umană. Trei indicatori de pilot fără rezultate numerice inventate. Final: JEV și numele echipei.

**Spoken:**

> Our proposed first user is a product operations team reviewing product claims before publication. We would start with one product family, approved sources and a human reviewer. The pilot would compare review time, errors and cases escalated against the manual process. We have demonstrated the prototype on Hooly. Applying it to a company's vocabulary and documents is the next validation step. We are JEV: Teo, Edi and Mihai.

## Varianta obligatorie dacă browserul rămâne pe traseul simplificat

Înlocuiți întregul bloc 00:20–00:45 cu acest bloc, fără să le cumulați:

> We turn Hooly text into typed assertions and compare them with dated evidence. This browser demonstrates our current shared-core path. The native extractor and guarded temporal chain run in the separate competition CLI. Rust gives us native CPU execution and explicit memory control. We keep these execution paths visible.

Diagrama afișată trebuie să facă aceeași distincție. Nu declarați paritate înainte să fie verificată. Dacă integrarea se încheie, reînregistrați demonstrația pe configurația finală și ajustați numai afirmațiile confirmate.

## Adaptări la rezultatele reale

| Situație | Formulare scurtă, în locul propoziției nepotrivite |
| --- | --- |
| Rând fără surse atașate | “This result has no attached source evidence. That is a limitation we keep visible.” |
| Niciun unsure în rularea filmată | “The interface supports unsure decisions; this particular run did not produce one.” |
| Rulare eșuată | Arătați eroarea și cauza cunoscută. O captură veche se marchează “Previously recorded run”; nu o prezentați ca rulare live. |
| Procesare mai lungă decât bugetul cadrului | Păstrați începutul și finalul real; dacă tăiați așteptarea, marcați “Processing time shortened in edit” și afișați durata măsurată. |

## Lista de filmare

- CSV oficial selectat și numărul de rânduri.
- Clickul de rulare și rezultatul acelei execuții.
- Un inspector lizibil: text, dată, explicație, surse.
- O afirmație generată și exportul.
- Diagrama versiunii efectiv demonstrate.
- Evaluare separată de sample, cu tipul datasetului și versiunea.
- Numele echipei și repo-ul în final.

Recomandare de producție: o singură voce, un operator de demo, un coleg care verifică datele afișate. Audio clar, captură 1080p, mouse lent, fără muzică peste explicații. Verificați fișierul MP4 final de la început la sfârșit.
