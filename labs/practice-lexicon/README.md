# Practice × Lexicon Lab

Laborator separat pentru explorarea datelor Hooly. Interfață în română, datele originale
în engleză. Citește exclusiv [practice.csv](../../data/practice.csv) și
[lexicon.json](../../data/lexicon.json). Nu modifică datele organizatorului.

## Pornire

Node.js 22+; fără pachete npm, instalare sau servicii externe. Din rădăcina repository-ului:

```sh
node labs/practice-lexicon/serve.mjs
```

Deschide http://127.0.0.1:8790. Serverul ascultă exclusiv pe loopback.
Pentru alt port, setează `LAB_PORT` înainte de pornire.

Pentru un HTML portabil, fără server:

```sh
node labs/practice-lexicon/build.mjs
```

Deschide `artifacts/practice-lexicon-lab/index.html` direct în browser. CSS, JavaScript
și toate datele sunt incluse în fișier. După modificări, rulează din nou build și
reîncarcă pagina. Directorul `artifacts/` este generat și nu se comite.

## Ce poți explora

- **Harta conexiunilor:** relații direcționate între subiecte, cu eticheta rândului și
  query-uri-sursă la click; focalizare, tot lexiconul și explorare pe tot ecranul.
  Apasă **⛶ Ecran complet**: sursele și query-urile se deschid în lateral, fără să ieși din graf.
  Rotița face zoom la cursor, tragi fundalul pentru deplasare, iar pe telefon poți folosi
  două degete. Căutarea găsește și aliasuri, butonul săgeată revine la subiectul anterior.
  **Detalii** ascunde/arată panoul lateral; **⊡** încadrează tot graful. În explorer:
  `+`/`−` pentru zoom, `0` pentru încadrare, săgețile pentru deplasare, `/` pentru căutare,
  `F` pentru fullscreen, `Esc` pentru închidere. Fullscreen-ul nativ are fallback la întreaga
  fereastră când browserul nu îl permite. Selecția unui nod în vederea globală păstrează camera.
- **Atribute:** schema subiectului selectat, aliasurile și numărul de rânduri relevante.
  Graful prezintă primele 16 atribute după numărul de rânduri; lista laterală le include pe toate.
- **Query-uri în timp:** toate rândurile, paginare, data paginii și ID, sortare în ambele
  sensuri, inspector cu textul și JSON-ul original, istoric pentru fiecare atribut.
- **Corelații:** grupuri cu același subiect și atribut, valori distincte, intervale de
  observație și acces la rândurile originale. Panoul unui query arată rândurile corelate
  cronologic și explică dacă valoarea structurată este identică sau diferită.
- **Filtre comune:** text/ID/alias/atribut, subiect, etichetă și interval inclusiv de date.
  Histograma lunară setează intervalul. Exportul CSV include rândurile afișabile în selecție,
  inclusiv selecția unei relații/unui atribut, cu schema originală și ordinea aleasă.

„Query” în acest lab înseamnă un rând din practice, nu o clasificare nouă.

## Interpretare

Data este data paginii-sursă, conform [contractului](../../contracts/README.md).
Nu deducem data intrării în vigoare, persistența valorii sau cauzalitatea. În aceeași zi,
ordinea este stabilă, după ID, numeric unde este posibil.

Etichetele `true`, `false`, `unsure` aparțin întregului rând. Un rând fals cu două valori
nu ne spune care dintre ele este falsă. Graful păstrează această proveniență și nu atribuie
verdicturi proprii valorilor individuale.

O relație în graf există doar când o valoare `kind: name` se rezolvă la un subiect/alias
din lexicon. Celelalte valori rămân vizibile în inspector și istorice, fără noduri inventate.
Legăturile din modul Atribute provin din schema lexiconului, nu din adevărul unei afirmații.

Corelația înseamnă aceeași pereche subiect–atribut. Egalitatea valorilor este structurală:
include tip, unitate, monedă, perioadă și operator. Nu convertim unități; valori distincte
pot avea aceeași semnificație. Aceste grupuri nu sunt detectoare de contradicții și nu sunt
evaluări statistice. Rândurile corelate din inspector provin din întregul practice;
deschiderea lor elimină filtrele, explicit în interfață.

SHA-256 pentru ambele fișiere este inclus în „Surse & metodă”. Nu există material de
antrenare generat. Codul și documentația au fost produse cu asistență Codex; toate
afirmațiile afișate provin din fișierele organizatorului.

## Teste

```sh
node --test labs/practice-lexicon/tests/*.test.mjs
```

Testează CSV cu quoting și linii multiple, date invalide, aliasuri, filtre, ordonare,
proveniența relațiilor, separarea valorilor după unități/monedă/operator și întregul dataset.
Testul de integrare fixează dimensiunile snapshot-ului oficial; dacă datele se schimbă,
verifică upstream și actualizează explicit așteptările după audit.

Test opțional de interfață, într-o pagină Orca deja deschisă la lab:

```sh
node labs/practice-lexicon/tests/browser-smoke.mjs BROWSER_PAGE_ID
```

Folosește `ORCA_CLI_COMMAND` când este setat și verifică 54 de comportamente în browser.
Ține pagina testată vizibilă, pentru ca browserul să producă frame-uri de animație.
Nu este necesar Orca pentru rularea aplicației sau a testelor de date.

Alternativ, verificare automată într-un Chrome/Edge instalat local, fără pachete npm:

```sh
node labs/practice-lexicon/tests/browser-cdp.mjs "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

Rulează cele 54 de verificări la 1440 și 390 px, plus gesturi reale de mouse și touch,
și salvează capturi în `artifacts/practice-lexicon-lab/`. Folosește un profil temporar
separat și închide browserul de test la final.

## Limite și implementare

Acesta este un instrument de explorare pentru dezvoltare, separat de workspace-ul Rust,
API, solver, claim generator și checker. Nu se integrează în build-ul competiției.
Nu oferă precizie de clasificare sau demonstrații de generalizare.

- [Decizie și scope](DECISION.md)
- [Handoff și verificări](HANDOFF.md)
- [Model pur și parser](core.mjs)
- [Interfață](app.js)
- [Explorer și gesturi](graph.js)
- [Teste de date](tests/model.test.mjs)
