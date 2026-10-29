# Business și întrebări pentru JEV

## O problemă pe care o putem explica în 20 de secunde

Un produs se schimbă. Afirmația veche continuă să circule într-o ofertă, o pagină de suport sau un răspuns către client. Cineva trebuie să stabilească ce sursă susține afirmația pentru perioada relevantă. Propunerea VERIDYCT este să facă această verificare mai ușor de inspectat.

Primul utilizator propus: product operations sau pre-sales. Responsabilul de buget: conducătorul operațiunilor de produs ori comerciale. Acestea sunt ipoteze de pilot, nu utilizatori confirmați.

Mesaj public:

> VERIDYCT helps a reviewer check a claim against dated evidence and see which cases still need human attention.

## Trei scenarii, unul principal

| Scenariu propus | Întrebarea concretă | Ce ar necesita pilotul |
| --- | --- | --- |
| Catalog SaaS / pre-sales | Este prețul din ofertă aplicabil produsului și perioadei descrise? | Surse aprobate, unități și perioade explicite, reviewer |
| Produs de plăți | Descriu oferta și documentația aceleași condiții de tarifare? | Vocabular de domeniu, condiții și excepții, integrare adaptată |
| Materiale pentru un produs bancar | Este afirmația din campanie susținută de fișa aprobată pentru perioada respectivă? | Surse autorizate, acces controlat și aprobarea umană a comunicării |

Scenariile sunt ipotetice. Nu afirmați că Stripe, o bancă sau un sponsor folosește VERIDYCT. Nu promiteți certificare de compliance, interpretare juridică sau verificarea automată a oricărui contract.

Un reper public concret: [documentația Stripe despre modificarea prețului unui abonament](https://docs.stripe.com/billing/subscriptions/change-price) distinge schimbarea prețului, intervalul de facturare și momentul schimbării. Acest lucru ilustrează de ce perioada și contextul contează. Nu demonstrează o integrare cu VERIDYCT sau o problemă a serviciului Stripe.

În prezentare, păstrați catalogul de produse ca scenariu principal. Celelalte două sunt răspunsuri pentru discuția cu mentorii, nu trei piețe deja cucerite.

## Pilot propus de două săptămâni

**Săptămâna 1:** o echipă selectează o familie de produse, exemple reprezentative, surse aprobate și cazuri dificile. Reviewerii stabilesc referințele și măsurăm timpul verificării manuale. Separăm exemplele de configurare de cele de evaluare.

**Săptămâna 2:** verificare asistată în paralel cu aprobarea umană. Colectăm timpul, corectările, erorile și cazurile escaladate. Conectorii către CRM sau documentație sunt extensii ulterioare; pentru pilot propunem importuri controlate.

Criterii propuse înainte de pilot:

- Reducerea timpului median de review, cu o țintă negociată înainte de măsurare.
- Calitatea aprobărilor cel puțin la nivelul procesului manual.
- Proveniență inspectabilă pentru justificările afișate.
- Raport separat pentru cazurile nesigure și erorile definitive.
- Nicio publicare automată pe baza unei predicții în pilot.

## Ipoteză economică transparentă

Exemplu ilustrativ, nu rezultat comercial:

| Ipoteză | Valoare |
| --- | ---: |
| Afirmații pe săptămână | 500 |
| Timp manual pe afirmație | 3 minute |
| Timp asistat presupus | 1,5 minute |
| Excepții și administrare suplimentare | 120 minute pe săptămână |
| Total manual | 25 ore |
| Total asistat presupus | 14,5 ore |
| Diferență de capacitate | 10,5 ore pe săptămână |

Calcul: `500 × 3 / 60 = 25`; `500 × 1,5 / 60 + 120 / 60 = 14,5`. Capacitatea eliberată nu este automat economie în numerar. Din valoare se scad pregătirea surselor, configurarea, evaluarea, suportul și calculul. În deck-ul scurt, preferați indicatorii pilotului în locul acestor ipoteze numerice.

Model comercial propus: pilot plătit pentru un domeniu limitat, apoi licență pentru echipă sau instalare dacă rezultatele justifică. Cererea și disponibilitatea de plată rămân de validat.

## Întrebări și răspunsuri

**De ce Rust?**

„Am ales execuție nativă și control explicit asupra memoriei pentru un buget mic de CPU și RAM. Limbajul ajută implementarea, iar benchmark-urile configurației livrate stabilesc performanța. Nu avem o comparație echivalentă care să dovedească un multiplicator față de Python.”

**De ce nu un chatbot?**

„Pentru această sarcină vrem afirmații structurate, valori și date inspectabile și rezultate urmărite până la sursă. Sistemul executat la concurs nu folosește un LLM.”

**Folosiți totuși AI?**

„Există extragere neurală specializată și verificare învățată în anumite configurații. ONNX CPU execută modelul de extracție. Nu este un model conversațional care generează verdictul. Diagrama arată configurația prezentată.”

**Ce înseamnă că împărțiți cuvintele în categorii?**

„Identificăm rolurile utile afirmației: entitate, atribut, valoare, monedă, unitate, operator și timp. Păstrăm negațiile și condițiile. Nu declarăm că avem un parser gramatical universal.”

**Ce înseamnă redundant?**

„După validarea candidaților, comparăm suprapunerea lexicală cu afirmațiile selectate. MMR penalizează repetiția pentru a obține acoperire mai variată. O dată, unitate sau negație diferită poate schimba sensul și trebuie păstrată.”

**Ați antrenat pe milioane de dataset-uri?**

„Am evaluat două versiuni înrudite ale unei suite sintetice, fiecare cu un milion de rânduri. Rapoartele spun că nu am antrenat greutățile pe acele pooluri. Testele de dezvoltare și antrenarea sunt etape diferite.”

**Cât de bun este sistemul?**

„Un candidat înghețat a obținut 87,58% pe 20.000 de ținte dintr-o lume sintetică nouă. Acesta este rezultatul acelei configurații. Pentru sample-ul oficial nu avem etichetele de referință, deci nu pretindem accuracy pe el.”

**De ce nu spuneți doar 99,7%?**

„Cifra aparține unui evaluator adaptat protocolului V2. Transferul strict a arătat o cădere mare, pe care am păstrat-o în raport. Un procent fără protocol ar ascunde limita cea mai importantă.”

**Când nu există suficiente dovezi, răspundeți întotdeauna unsure?**

„Nu universal. Motorul și routerul au politici distincte. De exemplu, traseul chain poate atribui true unei extrageri goale, cu anumite garduri. Aceasta este o limită evaluată și nu o garanție de adevăr.”

**Ce mai trebuie pentru un client real?**

„Surse aprobate, adaptarea vocabularului și a extracției, evaluare pe exemple reprezentative, controlul accesului și un proces uman de review. Prototipul demonstrează mecanismele în universul probei.”

**Care este principala limitare tehnică?**

„O decizie bună pe o afirmație extrasă greșit rămâne greșită pentru propoziția originală. Evaluăm extracția, verdictul și generarea separat. Scorurile modelului nu sunt probabilități general calibrate.”

**Ce cereți după hackathon?**

„O echipă, un catalog și un proces real de review. Vrem să măsurăm timpul, erorile și cât de utilă este dovada pentru persoana care decide.”

## Ce aduce mentoratul de business

Grila de kickoff alocă 10% business mentoring: problema și utilizatorul, valoarea și adopția. Dacă ați primit feedback real, spuneți concret ce v-a schimbat: de exemplu, restrângerea pilotului la un catalog sau păstrarea aprobării umane. Nu inventați interviuri, citate sau validări. Criteriile generale sunt și în [regulamentul NEXXT](https://nexxtsummit.com/rulebook/).
