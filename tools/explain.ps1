[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = 'VERIDYCT - Cum functioneaza sistemul'
function Titlu([string]$text) { Write-Host "`n$text" -ForegroundColor Cyan }
Write-Host 'VERIDYCT / JEV - EXPLICATIE COMPLETA A SISTEMULUI' -ForegroundColor Magenta
Write-Host 'Pagina locala: http://127.0.0.1:8787' -ForegroundColor Green
Write-Host 'Acesta este un ghid in terminal. Nu modifica datele si nu antreneaza alt model.'
Titlu '1. CE REZOLVAM'
Write-Host @"
Primim propozitii despre universul fictiv Hooly. Pentru un rand fara eticheta,
programul alege true, false sau unsure. Separat, construieste 1.000 de claims noi,
cu forma structurata si dovezi. Adevarul vine din datele universului, nu din web
si nu din cunostintele generale ale unui LLM. Programul final NU este un LLM.
"@
Titlu '2. CE FISIERE CITIM'
Write-Host @"
data/practice.csv: exemple publice cu id,text,date,label,form. form contine faptele
marcate de organizatori: subject, attribute, value. Acestea sunt date de antrenare.
data/lexicon.json: nume canonice, aliasuri, atribute permise si evenimente.
La concurs: /universe/universe.csv are DOAR id,text,date,label. Unele etichete sunt
goale. Coloana form nu exista; sistemul trebuie sa extraga singur faptele.
Imaginea poate include practice.csv cu forme, conform contractului.
"@
Titlu '3. PRIMUL PAS: VALIDARE CSV'
Write-Host @"
Core-ul verifica antetul, ID-uri unice, text, data calendaristica si etichete.
Accepta CSV cu virgula sau punct si virgula, UTF-8 si BOM. Texte cu virgule sau
newline sunt citite de o biblioteca CSV, nu prin split simplu. Datele invalide
produc eroare explicita. Nu antrenam sau rulam pe un fisier respins.
Implementare: crates/core/src/io.rs.
"@
Titlu '4. CE AM REFOLOSIT DE LA MIHAI'
Write-Host @"
Am portat matcherul de entitati din analiza lui Mihai, commit 4478b99:
normalizare Unicode NFKC, litere mici, spatii variabile, limite de cuvant si
alegerea celui mai lung nume. Hooly AI Pro trebuie recunoscut ca planul complet,
nu ca simpla companie Hooly. Lexiconul primit la rulare ramane autoritar.
Analiza lui arata si multe subiecte implicite si propozitii cu mai multe fapte.
Implementare: crates/core/src/engine.rs, functiile normalize/entities/extract.
"@
Titlu '5. CUM DEVINE O PROPOZITIE UN FAPT'
Write-Host @"
Exemplu sustinut de p-5, data 2026-01-12:
  Text: Hooly Cloud covers 3 regions.
  Subject: Hooly Cloud
  Attribute: regions
  Value: {kind:quantity, value:3, unit:region}
Extragem entitati, cautam exemple si sabloane similare, adaptam valori tipizate
(numere, procente, bani, date, durate, versiuni si nume). Formele practice pot
ajuta sabloanele; randurile noi nu primesc automat formele sau raspunsul corect.
Extragerea pe texte necunoscute este euristica si poate fi incompleta.
"@
Titlu '6. CE INSEAMNA DOVADA'
Write-Host @"
O observatie pastreaza ID-ul sursei, textul, data, eticheta si faptul extras.
Doar observatiile cu eticheta true pot sustine generarea unor claims.
Un rand false cu mai multe fapte nu inseamna ca fiecare fapt al lui este fals.
Repetarea unui rand neetichetat nu il transforma in adevar.
Nu folosim dovezi din viitor pentru a demonstra o afirmatie din trecut.
O observatie mai veche NU demonstreaza singura ca valoarea a ramas neschimbata.
Pentru o decizie decisiva, cautam valori true neambigue pe aceeasi data.
"@
Titlu '7. RANDOM FOREST: CE FACE MODELUL'
Write-Host @"
Avem 48 de arbori CART, adancime limitata, seed fix, rulare pe CPU.
Folosim 80 de caracteristici: text, similitudine, entitati, valori, indicii de
negatie/incertitudine si potriviri/conflicte cu dovezi. Arborii combina voturile;
corectam distributia invatata folosind proportiile claselor din antrenare.
Rezultatul are trei scoruri care insumeaza 1: true, false, unsure.
Scor 0.90 NU inseamna acuratete masurata de 90% si nu este o garantie calibrata.
Reguli de dovezi si abtinere pot interveni peste estimarea statistica.
Un text identic cu un exemplu practice, pe aceeasi data, este recunoscut explicit
ca exemplu memorat. Acest caz NU demonstreaza generalizare.
Implementare: crates/core/src/forest.rs si engine.rs.
"@
Titlu '8. UN EXEMPLU: DE CE TRUE / FALSE / UNSURE'
Write-Host @"
Daca o sursa true spune Hooly Cloud are 3 regiuni pe 2026-01-12:
- afirmatia 3 regiuni, aceeasi data, poate primi suport;
- afirmatia 30 regiuni, aceeasi data, poate primi o contradictie;
- culoarea preferata a lui Holdan, fara dovezi, trebuie tratata ca necunoscuta.
Modelul poate totusi gresi: extragerea si recunoasterea sensului nu sunt perfecte.
De aceea pagina arata afirmatia, faptele, sursele si motivul fiecarui verdict.
"@
Titlu '9. ACURATETE: CUM TESTAM CU ADEVARAT'
Write-Host @"
Test diagnostic: ascundem etichetele la fiecare al cincilea rand (380 de randuri).
Scoatem din antrenare TOATE textele normalizate egale cu textele testate.
Inputul testat nu contine nici etichetele reale, nici formele organizatorilor.
Dupa predictie comparam raspunsurile cu etichetele pastrate separat.
Afisam acuratete, corecte/total, macro-F1, precision/recall/F1 pe clase, matricea
de confuzie si fiecare greseala. Comparatia de baza este clasa majoritara.
Diagnostic existent: 80.26% acuratete, macro-F1 0.335; baseline majoritar 85.26%.
False si unsure raman slabe. Nu ascundem aceasta limita. Acest split a fost folosit
pentru diagnostic si ajustari, deci nu este o evaluare finala independenta.
Pe un input complet neetichetat, fara raspunsuri de referinta, acuratetea NU poate
fi calculata. Putem afisa doar predictii, scoruri si dovezi.
"@
Titlu '10. COMPARATIA CU REVIZUIREA LLM'
Write-Host @"
Demo integrat: un CSV demonstrativ fara etichete si o referinta LLM citata.
LLM-ul poate revizui exemple in timpul dezvoltarii, folosind doar dovezile Hooly.
Referintele LLM raman separate de CSV-ul trimis motorului.
Rezultat masurat: 14 din 20 de randuri, 70% ACORD CU REFERINTA LLM.
Nu il numim automat acuratete fata de adevar. LLM-ul poate gresi si el.
Nicio cerere catre un LLM nu este necesara la rularea programului din Docker.
"@
Titlu '11. GENERAREA CELOR 1.000 DE CLAIMS'
Write-Host @"
Construim candidati din observatii true, cu surse. Nu promovam predictiile true
ale modelului la rangul de dovezi pentru generare. Folosim cele cinci forme:
fact, compare, change, at_event si relation. Comparam date istorice confirmate;
pentru change avem doua valori observate in ordine; at_event cere data verificata
a evenimentului; relation cere o legatura si un fapt compatibile temporal.
Nu ghicim ziua exacta a unei schimbari din data publicarii unei pagini.
MMR alege 1.000 de candidati distincti din aproximativ 1.315:
  scor_selectie = 0.78 * incredere_in_dovada - 0.22 * redundanta_maxima.
MMR reduce repetitia; NU transforma o afirmatie nedovedita in adevar.
Implementare: crates/core/src/claims.rs.
"@
Titlu '12. FORMATUL FINAL PENTRU ORGANIZATORI'
Write-Host @"
/output/output.csv, UTF-8, maximum 16 MiB. Antet exact:
  id,type,text,form,label,confidence
Pentru randurile fara eticheta: type/text/form goale, label true/false/unsure.
Confidence este 0.5..1 pentru true/false, gol pentru unsure.
Pentru claims: type din cele cinci forme, text max 300 caractere, form JSON,
label true si confidence 0.5..1. Exact 1.000 de claims noi, cu ID-uri unice.
Scriem mai intai un fisier temporar complet in /output, apoi rename atomic.
O schema valida nu demonstreaza automat adevarul temporal sau acceptarea privata.
"@
Titlu '13. CE FACE BUTONUL RUN DIN PAGINA'
Write-Host @"
Browserul trimite CSV-ul la API-ul local Axum. Un worker CPU executa acelasi core
Rust folosit de CLI. Progresul vine din etape terminate, nu dintr-un timer fals.
Logurile arata incarcarea datelor, antrenarea, clasificarea, MMR si exportul.
Afisam tabelul cu scoruri, inspectorul de dovezi si descarcarea output.csv.
Disponibil: tab de evaluare cu acuratete masurata si diagrame PNG explicite.
Pagina foloseste HTML/CSS/JavaScript local, fara CDN si fara Node la runtime.
"@
Titlu '14. DOCKER: CONDITIILE TESTATE'
Write-Host @"
Linux amd64, fara retea pentru CLI, 2 CPU, 6 GiB RAM, UID 10001, maximum 256 PID,
root read-only, /tmp tmpfs 128 MB, /universe read-only, /output writable.
Containerul web expune HTTP doar pe 127.0.0.1:8787; foloseste acelasi core.
Test efectiv: 20.000 de randuri -> 18.103 verdicte + 1.000 claims, in 4.44 secunde.
Memorie cgroup maxima aproximativ 124 MB. Acesta este un test sintetic de viteza,
nu o masuratoare a acuratetii pe date noi. Testele Rust si checkerul de format trec.
"@
Titlu '15. COMENZI SI FISIERE PENTRU PREZENTARE'
Write-Host @"
Deschide: http://127.0.0.1:8787
Pornire:  docker compose up -d --build
Oprire:   docker compose down
Verificare contract: powershell -File tools/arena-check.ps1 -SkipBuild
Test 20k: powershell -File tools/benchmark-arena.ps1
Evaluare Rust: cargo run --release -p veridyct-core --example evaluate
Ghid complet: docs/handoffs/live-mvp.md
Arhitectura: docs/architecture.md
Organizatori: contracts/README.md, claim-forms.md, value-forms.md
"@
Write-Host "`nTerminalul ramane deschis. Poti derula in sus pentru explicatie." -ForegroundColor Green
