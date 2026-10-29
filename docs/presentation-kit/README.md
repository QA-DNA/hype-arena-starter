# VERIDYCT / Presentation kit

Un singur fir: o afirmație, data la care se referă, dovezile disponibile și decizia pe care o poate lua un om.

Pachet de redactare pentru JEV, 29 octombrie 2026. Conține texte, scenariu și indicații vizuale în Markdown. Nu modifică aplicația și nu reprezintă o certificare a integrării finale.

## Deschide fișierul potrivit

| Pentru | Document | Ce primești |
| --- | --- | --- |
| Povestea completă | [00 — Soluția](00-SOLUTIA.md) | Problema, utilizatorul, explicația produsului și motivul alegerii Rust |
| Persoana care face slide-urile | [01 — Slide deck](01-SLIDE-DECK.md) | Copy final în engleză, compoziție și note de prezentare |
| Persoana care înregistrează | [02 — Video](02-VIDEO-3-MINUTE.md) | Scenariu de 180 de secunde, cadre și condiții de folosire |
| Persoana care pregătește demonstrația | [03 — Frontend](03-FRONTEND-DEMO.md) | Parcursul demo-ului și brief pentru vizualizări propuse |
| Explicația tehnică și întrebările juriului | [04 — Arhitectură](04-ARHITECTURA-TEHNICA.md) | Text, tipuri, timp, dovezi, verificare și redundanță |
| Business și răspunsuri scurte | [05 — Business](05-BUSINESS-SI-QA.md) | Scenarii, pilot, indicatori, ipoteză economică și Q&A |
| Orice număr afișat | [06 — Rezultate și surse](06-REZULTATE-SI-SURSE.md) | Ce s-a măsurat, pe ce versiune și ce nu rezultă din măsurătoare |
| Handoff către un editor sau agent | [07 — Producție](07-PROMPTURI-PRODUCTIE.md) | Brief-uri gata de copiat pentru deck, video și frontend |

## Cum se folosește repede

1. Stabiliți versiunea efectivă din demo. Pachetul a fost redactat pornind de la `0dda354944b5d600eafe9ea6f680159440c1c38f`.
2. Citiți `06` înainte să puneți numere pe ecran. Alegeți un rezultat relevant pentru versiunea prezentată.
3. Construiți deck-ul din `01`, înregistrați după `02`, folosiți aplicația conform `03`.
4. Folosiți textele engleze pentru public. Notele românești sunt pentru echipă.
5. Verificați împreună video-ul, PDF-ul și commitul final. Atribuiți aceleași capabilități aceleiași versiuni în toate trei.

Rolurile editoriale sunt propuse: o persoană narator, una operator demo, una verifică versiunea și rezultatele. Echipa își atribuie rolurile; documentul nu presupune cine a implementat fiecare componentă.

## Regula editorială

**Implementat** înseamnă vizibil în codul consultat. **Măsurat** înseamnă documentat pentru o configurație precisă. **În integrare** înseamnă că piesele există, dar traseul complet trebuie verificat. **Propus** înseamnă scenariu de produs sau direcție vizuală.

Scena comercială este ilustrativă. Hooly este universul fictiv al probei. Nicio companie menționată nu este prezentată drept client, partener tehnic sau beneficiar validat al VERIDYCT.

## Livrare și limite

Deck recomandat: PDF 16:9. Video cerut în materialul de kickoff: 3 minute; export recomandat MP4/H.264, 1080p. Repo public și PR către starter, titlu `JEV`, înainte de 11:00. Canalul de upload pentru video/deck se confirmă la organizatori. Nu împingeți modificări pe branch-ul PR-ului după freeze.

Sample-ul publicat efectiv este [datasets/sample.csv](https://github.com/QA-DNA/hype-arena-starter/blob/main/datasets/sample.csv): 20 de rânduri, `id,text,date,label`, etichete goale. Calea din README-ul organizatorului este mai veche.

Acest pachet nu include un PPTX randat sau un video filmat. Brief-urile de frontend nu sunt modificări implementate în aplicație.
