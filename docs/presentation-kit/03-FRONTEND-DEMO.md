# Frontend / storyboard pentru o afirmație verificabilă

Brief editorial și vizual. Nu schimbă aplicația. Capturile trebuie să reprezinte ce rulează; vizualizările propuse pot fi folosite pe slide-uri cu marcajul `Illustration`.

## Ce există și ce propunem

| Element | Stare în snapshot | Cum îl folosim |
| --- | --- | --- |
| Upload CSV, `Run pipeline` | Există în [HTML](../../apps/web/index.html) | Rulare reală pe sample oficial |
| `Live workbench`, inspector | Există | Text, dată, explicație și observații-sursă |
| `Generated claims`, export | Există | Arătăm afirmațiile efective și fișierul produs |
| `Accuracy test` | Există | Diagnostic separat; nu este scorul sample-ului |
| `Architecture`, PNG-uri | Există | Descriu o versiune istorică; verificați potrivirea cu runtime-ul filmat |
| Cuvinte colorate pe roluri semantice | Propunere vizuală | Slide explicativ sau mockup etichetat |
| Cronologie interactivă a dovezilor | Propunere | Nu se prezintă ca funcție deja livrată |
| Vizualizarea candidaților respinși de MMR | Propunere | Diagramă pedagogică |
| Browser conectat la întregul CLI nativ/chain | De verificat la integrare | Nu presupuneți paritate |

## Scena 1. Start with the statement.

Afișați afirmația originală, ID-ul și data sursei. Un rând domină ecranul. Utilizatorul trebuie să poată citi ce se verifică înainte să vadă interpretarea.

Compoziție: treimea superioară, textul original; zona centrală, rezultat și explicație; dreapta, observațiile-sursă. Captura se mărește până când textul important este lizibil în video.

## Scena 2. Keep the parts that change meaning.

Exemplu ilustrativ, nu output extras din sample:

> From 1 May through 31 May 2026, Product A costs €59 per month.

| Fragment | Rol | Culoare de explicație |
| --- | --- | --- |
| Product A | Entity | Violet |
| costs | Attribute cue | Cerneală închisă, subliniere |
| 59 | Numeric value | Albastru |
| € | Currency | Albastru |
| per month | Billing period | Ocru |
| From 1 May through 31 May 2026 | Explicit temporal scope | Verde temperat |

Fiecare categorie are și o etichetă scrisă. Nu depindeți numai de culoare. În animație, fragmentele se mută sub text într-o structură simplă, păstrând originea.

„Not”, „only”, „at least”, „before” și „per year” pot schimba sensul. Nu descrieți aceste cuvinte ca zgomot eliminat automat. Data paginii și perioada explicită se afișează separat.

## Scena 3. Normalize names. Preserve distinctions.

Arătați două aliasuri care duc la aceeași entitate canonică. Păstrați distincte moneda, perioada, unitatea și operatorul. O normalizare de nume nu autorizează conversii numerice sau interpretări temporale arbitrare.

JSON-ul complet poate rămâne în inspector. Pentru filmare, o reprezentare cu cinci câmpuri lizibile explică mai mult decât o pagină întreagă de JSON.

## Scena 4. Show the source behind the decision.

Rezultat în stânga, observații relevante în dreapta. Fiecare observație arată ID, text și dată. Dacă nu există dovadă atașată, mesajul rămâne vizibil. Afișați `Model score` distinct de un procent de accuracy.

Deschideți un caz efectiv produs de sample. Dacă verdictul pare incorect, explicați limita întâlnită. Nu înlocuiți textul sau scorul în captură pentru a potrivi povestea.

## Scena 5. Select useful coverage.

Storyboard explicativ pentru redundanță:

1. Se văd mai mulți candidați construiți din surse.
2. Candidații aproape identici se grupează vizual.
3. O afirmație similară primește o penalizare de selecție.
4. Setul final păstrează acoperire mai variată.

Etichetă: `Illustrative candidate selection. Actual choices depend on support and similarity.`

Nu estompați ca „redundantă” o diferență de monedă, unitate, dată sau negație fără justificare. MMR optimizează selecția; adevărul și formatul se verifică separat. Implementarea folosește suprapunere lexicală, nu un model universal de echivalență semantică.

## Scena 6. A result someone can review.

Încheiați pe rezultatul utilizabil: verdict, dovezi, incertitudine și export. Utilizarea comercială propusă introduce un reviewer înaintea publicării. Nu afișați „Approved for publication” drept funcție existentă dacă nu există acel workflow.

## Stil și interacțiune

Capturile actuale rămân intacte. Pentru mockup-uri: ivory `#F5F3EE`, ink `#17201C`, purple `#7562A3`. Folosiți tranziții discrete de 150–250 ms doar pentru orientare, nu pentru a simula calcul. Reduceți mișcarea în înregistrare, păstrați focus vizibil și folosiți stări explicite pentru încărcare, eroare și lipsă de date.

O compoziție bună arată un caz complet. O rețea mare de noduri poate fi decorativă și greu de explicat. Măriți subgraful relevant și arătați etichetele muchiilor și sursele, dacă datele reale sunt disponibile.

## Handoff către autorul frontend-ului

Acest document definește o prezentare și o direcție posibilă. Implementarea unor noi vizualizări necesită o sarcină separată. [Arhitectura](04-ARHITECTURA-TEHNICA.md) și [registrul de rezultate](06-REZULTATE-SI-SURSE.md) controlează afirmațiile tehnice. O interfață mai frumoasă nu modifică scorurile sau statutul integrării.
