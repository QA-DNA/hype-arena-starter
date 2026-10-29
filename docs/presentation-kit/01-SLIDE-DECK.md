# VERIDYCT / Deck complet

Opt slide-uri principale, două anexe. Textul public este în engleză. Notele și indicațiile de compoziție sunt pentru echipă. Fiecare slide are o idee principală; copy-ul nu trebuie înghesuit peste capturi.

## Direcția vizuală

Format 16:9. Fond fildeș `#F5F3EE`, text `#17201C`, accent violet `#7562A3`. Coperta poate folosi fond închis și text cald. Folosiți Aptos sau Inter dacă este disponibil: titlu 40–48 pt, corp 24–28 pt, note de sursă lizibile. Margini de minimum 64 px în planșa de 1920×1080. O singură diagramă sau captură dominantă pe slide. Fără fotografii decorative cu roboți, rețele fără sens sau logo-uri de presupuşi clienți.

## 1. Before the offer goes out.

**Copy exact:**

> **Before the offer goes out.**
>
> Check product claims against dated evidence.
>
> VERIDYCT
>
> Teo, Edi and Mihai · Team JEV

**Compoziție:** titlu mare în stânga. În dreapta, un fragment simplu dintr-o ofertă ilustrativă, fără verdict fabricat. Numele echipei discret.

**Notă vorbitor:** „Când se schimbă un produs, informația veche poate rămâne într-o ofertă sau într-un răspuns către client. Am construit VERIDYCT ca să examinăm afirmația, dovada și momentul la care se referă.”

## 2. The price changed. The proposal did not.

**Copy exact:**

> **The price changed. The proposal did not.**
>
> Approved price, effective June: €59
>
> Draft proposal for June: €49
>
> Which source supports the offer?
>
> Illustrative business scenario.

**Compoziție:** două fragmente de document, același produs și aceeași bază de tarifare. Valori și date mari. Marcajul „Illustrative business scenario” vizibil.

**Notă vorbitor:** „Exemplul este inventat pentru a explica problema. Un document mai nou nu este automat valabil pentru orice client și perioadă. Trebuie să verificăm produsul, valoarea, condițiile și intervalul.”

## 3. Review a claim. Inspect the evidence.

**Copy exact:**

> **Review a claim. Inspect the evidence.**
>
> Import statements.
>
> Run the analysis.
>
> Inspect the verdict, source and date.
>
> Review uncertain cases.
>
> Export the results.

**Compoziție:** captura reală ocupă două treimi din planșă. Restul prezintă pașii. Măriți un singur inspector; nu folosiți un screenshot cu text imposibil de citit.

**Notă vorbitor:** „Aici este traseul utilizatorului. În pilotul comercial propus, persoana care face review păstrează aprobarea finală. Nu pretindem că prototipul interpretează deja orice document sau contract.”

## 4. Every value needs context.

**Copy exact:**

> **Every value needs context.**
>
> Entity. Attribute. Value. Unit. Time.
>
> Evidence constraints and learned verification produce verdicts.
>
> Supported candidates become diverse claims.
>
> Native Rust. CPU inference. No runtime LLM.

**Compoziție:** sus, propoziția ilustrativă din `00`, colorată pe roluri. Jos, maximum șase blocuri din diagrama tehnică. Folosiți liniile punctate pentru integrarea neverificată; afișați o legendă scurtă. Lanțul temporal apare ca modul condițional.

**Notă vorbitor:** „Normalizăm nume și aliasuri, păstrăm valorile cu unități și timp și le comparăm cu dovezi. Am ales Rust pentru execuție nativă și control asupra memoriei. Arătăm componentele din configurația care rulează, nu toate experimentele din repo ca și cum ar fi simultan active.”

## 5. The official sample, processed live.

**Copy exact:**

> **The official sample, processed live.**
>
> 20 unlabelled rows.
>
> Follow one result from statement to evidence.
>
> Inspect uncertainty.
>
> Generate and export claims.

**Compoziție:** treceți efectiv în aplicație. Acest slide poate fi o planșă de tranziție cu numele sample-ului. Nu afișați procent de accuracy pentru un sample fără etichete oficiale.

**Notă vorbitor:** „Acesta este sample-ul publicat în dimineața concursului.” Selectați `datasets/sample.csv`, apăsați butonul real și deschideți un rezultat. Arătați inclusiv o limitare dacă apare. Cazurile explicative inventate nu se amestecă în această rulare.

## 6. Large tests need precise labels.

**Copy exact:**

> **Large tests need precise labels.**
>
> V1: 1,000,000 synthetic rows
>
> V2: 1,000,000 synthetic rows
>
> Related development cohorts.
>
> Declared protocol adaptation.
>
> Model weights remained frozen during these evaluations.

**Compoziție:** două coloane egale legate vizual de nota despre cazurile înrudite. Fără contor „2 million independent tests”. Nota de sursă: `docs/research/million-v1-v2.md`.

**Notă vorbitor:** „Am evaluat integral două versiuni ale unei suite de dezvoltare. Ele păstrează identitatea cazurilor și etichetele, dar schimbă multe intrări. Testarea a arătat atât adaptarea reușită, cât și sensibilitatea la schimbarea protocolului. Scorurile acestor suite nu sunt scorul concursului.”

**Alternativă pentru o prezentare axată pe performanță predictivă:** înlocuiți această planșă cu Anexa A, explicând că cifra aparține candidatului înghețat. Nu cumulați toate procentele într-un singur headline.

## 7. Start with one product catalogue.

**Copy exact:**

> **Start with one product catalogue.**
>
> User: product operations.
>
> Workflow: check claims before publication.
>
> Pilot input: approved facts and dated statements.
>
> Output: reviewable results.
>
> Proposed commercial application.

**Compoziție:** trei etape: draft, review asistat, aprobare umană. Evitați o hartă de integrări care nu există. Un import CSV poate fi suficient pentru primul pilot propus.

**Notă vorbitor:** „Am începe cu o familie de produse și o echipă care verifică deja informația manual. Adaptarea la documentele reale și la vocabularul companiei face parte din pilot.”

## 8. A pilot we can measure.

**Copy exact:**

> **A pilot we can measure.**
>
> One team. One catalogue. Human-reviewed references.
>
> Compare review time, errors and review workload.
>
> Next: test VERIDYCT inside a real review process.

**Compoziție:** trei indicatori fără valori inventate: review time, incorrect approvals, human review load. Echipa și repo-ul în final.

**Notă vorbitor:** „Căutăm un proces real pe care să îl măsurăm. Pilotul trebuie să arate dacă persoana care verifică lucrează mai eficient și vede erorile mai clar. Dacă rezultatele justifică, discutăm integrarea și licența.”

## Anexa A. Rezultatul înghețat

**Copy exact:**

> **87.58% label accuracy.**
>
> 20,000 targets from a fresh synthetic world.
>
> Frozen candidate and configuration.
>
> 58.17% definitive coverage.
>
> Separate from the official hidden evaluation.

**Notă:** 94,42% este corectitudinea numai între predicțiile definitive. Nu o afișați ca rezultat pe întregul set. Datele provin din [handoff](../handoffs/evidence-graph-runtime.md); nu reprezintă o măsurătoare nouă a integrării curente.

## Anexa B. Selecția fără repetiție

**Copy exact:**

> **Select useful coverage.**
>
> Build candidates from accepted evidence.
>
> Validate structure and remove duplicates.
>
> Penalize overlap with selected claims.
>
> Preserve meaning-changing differences.

**Vizual:** trei afirmații asemănătoare grupate, una diferită păstrată. Eticheta „Selection illustration”. MMR folosește în această implementare o aproximare a suprapunerii lexicale; nu pretindeți deduplicare semantică bazată pe embeddings.

## Export și verificare

Export PDF, verificați la dimensiune normală fiecare slide și copiați linkul repo-ului în text, nu doar într-un QR. Capturile trebuie să fie din versiunea filmată. Țineți sursele și notele de limită lângă cifre. Ultima verificare se face cu [registrul de rezultate](06-REZULTATE-SI-SURSE.md).
