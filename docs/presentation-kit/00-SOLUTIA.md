# VERIDYCT: înainte să publici o afirmație, verifică ce o susține

Text de lucru pentru prezentare. Exemplul comercial este ilustrativ; capabilitățile curente și rezultatele verificabile sunt delimitate în [registrul de dovezi](06-REZULTATE-SI-SURSE.md).

## Deschiderea

La 09:15, cineva pregătește o ofertă pentru un client. Pagina produsului arată un preț. Un PDF salvat luna trecută arată altul. Un coleg trimite o prezentare cu o a treia formulare. Întrebarea nu este doar unde apare informația. Întrebarea este ce afirmație poate fi susținută, pentru ce dată și pe baza cărei surse.

Acesta este scenariul de produs pe care îl propunem pentru VERIDYCT: verificarea afirmațiilor înainte să ajungă în oferte, pagini de produs sau răspunsuri către clienți.

În hackathon, testăm mecanismele pe Hooly, universul fictiv primit de la organizatori. Intrarea are propoziții, date și unele etichete cunoscute. Sistemul trebuie să clasifice restul și să construiască 1.000 de afirmații noi. Trecerea la documentele unei companii reale ar necesita surse aprobate, extragere adaptată domeniului și un pilot separat.

## Ce vrem să vadă juriul

O propoziție intră în sistem. Cuvintele relevante devin o structură verificabilă: cine, ce atribut, ce valoare, în ce unitate și în ce interval. Sistemul caută dovezi compatibile, păstrează proveniența și produce un rezultat. Utilizatorul poate deschide sursele și poate vedea unde informația este incompletă.

Povestea trebuie să rămână ancorată în acest parcurs. Demo-ul arată un rând real din sample, rezultatul efectiv și dovezile pe care aplicația le expune. Diagrama explică mecanismul. Evaluarea arată unde mecanismul rezistă și unde are limite.

Text public scurt, în engleză:

> VERIDYCT checks claims against dated evidence. We turn text into typed assertions, preserve their sources, and expose the information behind each decision. Our prototype runs on the Hooly challenge. Our proposed first use is helping product teams review commercial facts before publication.

## Ce înseamnă concret „înțelege textul”

Nu tratăm fiecare propoziție ca pe o singură etichetă opacă. Identificăm entități și aliasuri, atribute, valori, monede, unități, operatori și indicii temporale. Normalizăm forme diferite ale aceluiași nume, păstrând textul original pentru inspecție.

Exemplu inventat pentru explicație, nu rezultat de demo:

> From 1 April, Atlas Pro costs €59 per user per month.

| Fragment | Rol |
| --- | --- |
| Atlas Pro | Subiectul afirmației |
| costs | Indiciu pentru atributul preț |
| 59 | Valoare numerică |
| € | Monedă EUR |
| per user | Baza de tarifare |
| per month | Perioada |
| From 1 April | Condiție temporală explicită; anul trebuie stabilit din context autorizat |

O animație poate construi această structură pas cu pas. Ea explică metoda; un astfel de overlay rămâne propus dacă aplicația nu îl expune încă. Clasificarea semantică a fragmentelor nu trebuie descrisă ca un POS tagger universal: parserul separat folosește reguli și lexicon, iar calea nativă utilizează modele de extragere specializate.

## Timpul schimbă sensul

Două prețuri diferite pot fi ambele corecte, în perioade diferite. Data publicării unei pagini nu dovedește singură când a intrat în vigoare un preț. O afirmație falsă cu două componente nu dovedește că ambele componente sunt false. Aceste distincții sunt explicații tehnice bune pentru juriu: arată de ce problema cere mai mult decât potrivire lexicală.

Nu promitem că fiecare caz lipsit de dovezi devine automat `unsure`. Versiunea de competiție conține politici și fallback-uri descrise în documentele tehnice, inclusiv o regulă pentru extragere goală. Demo-ul trebuie să arate rezultatul real, iar răspunsurile despre limite trebuie să menționeze aceste politici când sunt relevante.

## Cum evităm 1.000 de variații ale aceleiași idei

Generatorul construiește candidați din dovezi acceptate și tipuri de afirmații permise. Verifică forma și noutatea, apoi selecția MMR penalizează asemănarea cu afirmațiile deja alese. Intuiția: următoarea afirmație trebuie să fie utilă și să adauge ceva setului.

Scena vizuală propusă: un grup de propoziții aproape identice se strânge într-un singur grup. Rămân vizibile afirmații despre atribute, comparații și perioade diferite. Eticheta scenei este „Selection illustration” dacă nu se folosesc candidați și scoruri exportate de rularea efectivă.

MMR ajută la diversitate. Validitatea și susținerea factuală se verifică separat. Nu declarăm că o selecție diversă garantează adevărul.

## De ce Rust

Am ales Rust pentru un executabil nativ, control asupra alocărilor și structuri de date care exprimă explicit tipurile și erorile. Modelul de ownership și lipsa unui garbage collector obligatoriu sunt potrivite pentru un proces cu buget limitat de memorie. Cargo și lockfile-urile ajută echipa să construiască aceeași versiune.

Constrângerile probei sunt concrete: două CPU, 6 GiB RAM, execuție offline și 30 de minute. Ne interesează timpul total și memoria maximă pentru configurația livrată. Rust nu înlocuiește măsurătorile. Nu avem în acest pachet o comparație controlată care să demonstreze că soluția este de zece ori mai rapidă decât una echivalentă în Python sau Go.

Text pentru slide sau voiceover:

> We chose Rust to compile the CPU pipeline into a native executable and keep memory use under explicit control. We measure the full system against the challenge budget. The optional extractor runs a compact ONNX model locally.

Sursa pentru proprietățile limbajului: [Rust](https://rust-lang.org/). Configurația produsului trebuie citită în Dockerfile-ul versiunii efectiv predate; nu implicați că absența unui runtime Python în imagine înseamnă absența bibliotecilor native.

## Cum povestim munca pe date

Formula recomandată:

> We evaluated two versions of a one-million-row development suite. Their shared cases let us examine how language changes affect the pipeline. We report these protocol-specific results separately from our frozen tests on fresh synthetic worlds.

Este o poveste mai utilă decât un număr mare singur: arată că ați testat variații, ați păstrat proveniența și ați observat diferența dintre adaptarea la un protocol și generalizare. Cele două versiuni păstrează aceleași ID-uri de caz. Nu sunt două milioane de observații independente și rapoartele nu susțin că ați antrenat greutățile pe aceste pooluri.

În deck, două coloane „V1: 1,000,000 rows” și „V2: 1,000,000 rows”, legate de nota „Paired synthetic development cases”. Evitați un contor izolat „2M training datasets”.

## De la Hooly la un pilot comercial

Primul utilizator propus este persoana care verifică fapte comerciale: product operations sau pre-sales. Prima versiune de pilot ar primi exporturi structurate aprobate și afirmațiile care urmează să fie publicate. Omul rămâne responsabil de aprobarea finală.

Măsurăm timpul de verificare, erorile care trec de control și câte cazuri necesită revizie. O companie ar cumpăra rezultatul acestui proces, dacă pilotul îl validează: verificări mai ușor de urmărit, cu sursele la îndemână. Licența pentru echipă este o ipoteză comercială, nu venit existent.

## Ultima propoziție

> Our next step is a small pilot on approved product information: measure review time, inspect every error, and learn whether the evidence is useful to the people making the final decision.

Închideți pe exemplul de la început: persoana care pregătește oferta poate vedea ce susține afirmația și ce trebuie verificat mai departe.
