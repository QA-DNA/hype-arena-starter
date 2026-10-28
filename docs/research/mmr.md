# MMR pentru VERIDYCT: relevanță, dovezi, variante de testat

Status: research + experimente scurte pe `data/practice.csv`, 2026-10-28. Nu e cod de producție,
nu e commis. Autor: Edi (orchestrare) cu workeri Claude (3 research, 2 experimente).
Scripturile și rapoartele brute sunt în [`analysis/mmr/`](../../analysis/mmr/).

Întrebarea: cum folosim Maximal Marginal Relevance (MMR) ca să scoatem scor maxim pe Hype or
Truth, unde e relevant cu adevărat, unde strică, și ce variante merită testate.

---

## 0. Pe scurt

1. **MMR intră în trei locuri, cu greutăți foarte diferite.**
   - **Selecția celor 1.000 de claim-uri**: locul principal. Folosim însă o variantă modificată,
     cu plafon pe fiecare fapt de bază sau penalizare cumulativă, nu MMR-ul clasic.
   - **Datele de antrenare și calibrare**: util și ieftin, dar secundar.
   - **Etichetarea celor ~18.000 de rânduri**: aici MMR-ul clasic pe similaritate de text
     **strică**, am măsurat asta (secțiunea 4). Ideea lui de penalizare a redundanței trebuie
     mutată în agregarea voturilor, adică discount pe paginile care copiază (Dong et al. 2009).
     X3 (secțiunea 4.4) a testat-o peste modelul V11 al echipei: ca feature în plus nu ajută.
     În schimb, X3 a arătat că **V11 e vulnerabil la minciuni copiate**: recall-ul pe false
     scade de la 0,46 la 0,20. Reparația de testat e dedup-ul la sursă, înainte de orice
     feature.
2. **Matematica deciziei.** Dacă fiecare claim corect valorează la fel (scor liniar), top-k după
   P(true) e exact optim, oricât de corelate ar fi erorile. Diversificarea nu crește valoarea
   așteptată, ci reduce riscul. Merită totuși, din trei motive:
   - p-ul nostru e o **estimare**, iar erorile ei sunt corelate prin faptele de bază
     (optimizer's curse);
   - formula de scor e **necunoscută**: poate penaliza duplicatele, poate răsplăti acoperirea,
     poate avea praguri;
   - o singură pagină mincinoasă în care am avut încredere poate strica zeci de claim-uri
     deodată.
3. **MMR-ul clasic are un defect structural pentru problema noastră.** Penalizarea folosește
   `max` peste setul ales. După primul claim pe cheia A, fiecare claim următor pe A primește
   aceeași penalizare, deci MMR-ul blochează duplicatele aproape identice, dar **nu limitează
   expunerea** pe un fapt. Soluții: agregare `sum` (mean-variance, teoria portofoliului),
   penalizare care crește cu numărul de claim-uri pe aceeași cheie, sau plafon strict per fapt
   de bază.
4. **Experimentele de azi** (detalii în secțiunile 3.5 și 4.1):
   - Claims, k=1.000 din pool-ul practice (7.017 candidați pe 501 chei): top-k pune 104
     claim-uri pe o singură cheie (`Hooly I/O 2026.date`). MMR-ul clasic nu repară asta
     (expunerea rămâne 97-104), iar un **plafon de 10 claim-uri pe fapt** o reduce la 10 cu
     costul de −3% din valoarea așteptată. Efectul: deviația standard scade cu 35%, percentila 1
     crește cu 29 de claim-uri, iar pierderea la o cheie greșită scade de la 104 la 10 claim-uri.
     La raportul realist pool/k (k=100 pe practice), top-k e deja divers și plafonul nu se
     activează deloc, deci asigurarea e gratuită.
   - Sub ipotezele de scor neliniare (duplicate penalizate, acoperire), MMR cu λ între 0,5 și
     0,7 câștigă +11% la k=1.000.
   - **Hibridul plafon C=10 + MMR λ=0,5** e cel mai bun compromis:
     - maximin 0,935 pe ipotezele de scor, față de 0,899 la top-k;
     - p1 598, față de 587;
     - sd −31%;
     - pierderea la o cheie greșită scade de la 104 la 10 claim-uri.

     Nu există o strategie dominantă, ci un front Pareto între robustețea la scor și coada de
     risc.
   - Evidence retrieval: MMR pe text cu λ ≤ 0,7 **scade** regăsirea dovezii decisive cu
     7,6 puncte la k=10 (0,559 → 0,483). λ=0,9 e neutru. Recency weighting strică și el.
5. **Recomandarea default, de testat întâi:**
   1. dedup exact pe forma canonică;
   2. P(valid și true) calibrat, diferit pe tip de claim;
   3. greedy lazy după p, cu **plafon pe fiecare fapt de bază** de ~1% din k (C=10 la
      k=1.000; C=5 e prea strâns) și **penalizare MMR structurală** cu λ=0,5 dacă vrei
      robustețe la scor sau λ=0,85 dacă vrei coada de risc;
   4. fără cote egale pe tip;
   5. λ și C aleși prin simulare pe mai multe ipoteze de scoring, cu criteriul
      maximin-regret, ideal **la rulare, pe pool-ul real** (C19).

   Plafonul nu costă nimic când pool-ul e deja divers și taie coada când nu e. MMR-ul adaugă
   +11% doar dacă scorul răsplătește diversitatea.

---

## 1. MMR pe scurt

**Definiția** (Carbonell & Goldstein, SIGIR 1998):

```
MMR = argmax_{d ∈ R \ S} [ λ · Sim1(d, Q) − (1 − λ) · max_{s ∈ S} Sim2(d, s) ]
```

- `R` e pool-ul de candidați, `S` setul ales până acum, `Q` interogarea.
- `Sim1` e relevanța, `Sim2` e redundanța.
- Greedy: la fiecare pas adaugă candidatul cu scorul maxim, până la k.
- λ=1 dă top-k pur, după relevanță. λ=0 dă diversitate pură.
- Folosit inițial la reordonarea documentelor și la rezumate multi-document.

**Cum a fost evaluat inițial.** Evaluarea din 1998 e subțire:
- un pilot cu 5 utilizatori, dintre care 80% au preferat MMR;
- SUMMAC 1998, unde a avut F=0,73, cel mai bun la rezumate dependente de interogare;
- un test de precizie pe propoziții fără diferență semnificativă între λ=1, 0,7 și 0,3.

Autorii sugerează λ≈0,3 pentru explorare, apoi λ≈0,7.

**Ce garantează și ce nu.**
- MMR e un greedy pentru o problemă de tip *max-sum / max-min diversification*, care e NP-hard.
- **MMR-ul exact nu are garanție de aproximare.** Lin & Bilmes (ACL 2011, Teorema 2) arată
  că funcția de set implicită e submodulară, dar **non-monotonă**, deci limita 1 − 1/e nu se
  aplică. Borodin et al. spun explicit că MMR "has not been theoretically justified".
- Variantele formulate monoton au garanții:
  - Lin & Bilmes: acoperire + recompensă de diversitate, greedy cu 1 − 1/e, ROUGE-1 38,90 pe
    DUC-04 față de 37,94 pentru cel mai bun sistem DUC;
  - Borodin et al. 2012: max-sum diversification, 2-aproximare cu greedy-ul lor;
  - greedy sub matroid partiție: 1/2.
- Gollapudi & Sharma (WWW 2009) definesc 8 axiome și arată că nicio funcție de diversificare
  nu le poate satisface pe toate. Orice alegere e un compromis.

**Ce arată măsurătorile din practică** (detalii în
[r1](../../analysis/mmr/research/r1-foundations.md)):
- **Pe pool-uri curate MMR strică** (arXiv 2610.09412). HotpotQA S-Recall@5 scade de la
  78,7 (k-NN simplu) la 58,6 la λ=0,5, iar ArguAna NDCG@10 de la 38,3 la 0,2. Ajută doar când
  pool-ul are duplicate aproape identice.
- **PM-2 (SIGIR 2012)**: pe TREC Web, MMR a ajutat și a stricat cam la fel de multe
  interogări. PM-2 și xQuAD au fost clar mai bune acolo unde existau aspecte explicite.
- **Experiență de la utilizatori**:
  - LocalLens #34: λ=0,5 a scos cel mai bun chunk, iar λ=0,7 a reparat;
  - LangChain #39052: wrapper-ul Qdrant inversează `lambda_mult`;
  - BERTopic #1142: MMR nu face nimic când pool-ul are aceeași mărime ca output-ul.
- **Convențiile diferă între biblioteci**:
  - LangChain are implicit `lambda_mult=0,5` și `fetch_k=20`;
  - Weaviate e implicit pe diversitate maximă;
  - Qdrant și OpenSearch folosesc "diversity", unde 1 înseamnă mai divers.

  Dacă portăm o valoare din altă parte, verificăm întâi convenția.

**Problemele cunoscute ale MMR, toate relevante pentru noi.**
- **Scale mismatch.** Relevanța și similaritatea trebuie să fie pe aceeași scară, altfel λ nu
  înseamnă nimic. La noi relevanța e o probabilitate în [0,1]. Similaritatea trebuie
  normalizată la fel.
- **Sensibilitate la λ.** Nu există un λ universal. AVeriTeC a folosit 0,75, LangChain are
  implicit 0,5, iar literatura din 2024 (arXiv 2407.04573) se plânge că λ e greu de prezis.
- **`max` nu e acoperire.** Penalizează doar cel mai apropiat vecin deja ales. Nu numără câți
  vecini similari sunt deja în set (vezi 3.2).
- **Cost.** Naiv e O(n·k) evaluări de similaritate cu un vector de max-sim ținut în cache.
  La noi similaritatea e structurală și rară, deci costul e aproape liniar (vezi 3.6).

**Familia** (detalii în [r1](../../analysis/mmr/research/r1-foundations.md) și
[r3](../../analysis/mmr/research/r3-improvements.md)):

| Metodă | Ce optimizează | Garanție | Când bate MMR |
| --- | --- | --- | --- |
| xQuAD, PM-2, IA-Select | acoperirea unor aspecte explicite ale interogării | IA-Select: 1 − 1/e | când aspectele sunt cunoscute (la noi: tip, subiect, atribut) |
| DPP, k-DPP (Kulesza & Taskar 2012; greedy MAP, Chen et al. 2018) | det(L_S), cu L = diag(q)·S·diag(q) | greedy pe log-det, non-monoton | când vrei calitate × diversitate într-un singur obiectiv, fără λ ad-hoc |
| Facility location, coverage (Lin & Bilmes 2011) | cât de bine e reprezentat universul | 1 − 1/e | când scorul răsplătește acoperirea |
| Portfolio theory (Wang & Zhu, SIGIR 2009) | E[relevanță] − b·Var | n/a (greedy) | când contează riscul și erorile corelate: exact cazul nostru |
| k-center, core-set (Sener & Savarese 2018) | raza maximă de acoperire | 2-aprox | selecție de date de antrenare |
| DIVERSUM (entity summarization) | un singur triplet per proprietate | n/a | la selecția de fapte despre entități, cel mai bun la k=10 pe ESBM |

---

## 2. Unde apare o problemă de tip MMR în challenge

| Componentă | Forma problemei | Relevanța | Redundanța | Potrivire |
| --- | --- | --- | --- | --- |
| 1.000 de claim-uri | alegi k=1.000 din N ≫ 1.000 candidați | P(claim valid și adevărat) | aceleași fapte de bază, același subiect sau atribut, același tip | **mare**, cu modificări |
| Evidence pentru etichetare | alegi dovezile pentru fiecare rând | similaritate de text sau aceeași cheie | aceeași pagină, aceeași valoare copiată | **negativă** pe text (măsurat); **pozitivă** mutată în vot |
| Date de antrenare și calibrare | alegi exemple sintetice sau de verificat | utilitate pentru parser sau clasificator | același template, aceeași formă | medie |
| Frontend și pitch | explici de ce ai ales claim-urile | n/a | n/a | bonus de prezentare |

**Date măsurate pe practice.csv** (orchestrator, 2026-10-28), care justifică problema de risc:
- **291 de pagini**: rânduri consecutive cu aceeași dată, în medie 6,5 rânduri pe pagină,
  maximum 15.
- **Minciunile sunt parțial concentrate**: 128 de pagini curate, 34 cu ≥ 50% rânduri false,
  11 cu 100% false.
- **217 din 514 chei** (subject, attribute) au cel puțin un rând fals; 43 au un rând unsure.
- **Rânduri pe cheie**: mediana 4, p90 9, maximum 49; 75 de chei au un singur rând.
- **Minciuni copiate**: 360 de aserțiuni din rânduri false, 294 distincte; **47 de valori false
  se repetă** pe mai multe rânduri. Votul naiv va fi păcălit exact cum descrie Dong (2009).
- **Pool-ul de candidați** e mult mai mare decât 1.000, din practice.csv singur:
  - 501 chei cu ultima observație unică;
  - 4.451 de perechi compatibile pentru compare;
  - plus change, at_event și relation.

  Rularea reală are ~10× mai multe rânduri.

---

## 3. Claims: locul unde MMR contează

Generatorul de claim-uri (ce întreabă KB-ul, cum construiește candidații) e descris în
[claim-generation.md](claim-generation.md). Secțiunea de față tratează doar selecția celor 1.000.
Atenție la o diferență: acolo pasul de selecție are cote pe tip, iar în X1 **cotele egale pe tip**
au ieșit cele mai proaste la risc (3.5). Cote proporționale sau minime nu au fost testate.

### 3.1 Când ajută diversificarea (matematică)

Notații:
- `S` e setul ales, cu |S| = k;
- `X_i ∈ {0,1}` indică dacă claim-ul i e valid și adevărat;
- `p_i = E[X_i]`;
- claim-ul i e corect dacă toate faptele lui de bază `B(i)` sunt corecte;
- fiecare fapt f e corect cu probabilitatea `q_f`, independent de celelalte;
- deci `p_i = ∏_{f∈B(i)} q_f`.

- **Scor liniar** (H1, fiecare claim corect = +1): `E[scor] = Σ_{i∈S} p_i`. Linearitatea
  așteptării ține pentru orice corelație. Top-k după p e optim, iar orice schimb făcut de MMR
  costă `p_out − p_in`.
- **Varianța**: `Var(Σ X_i) = Σ p_i(1−p_i) + Σ_{i≠j} Cov(X_i, X_j)`. Covarianța e pozitivă
  exact când `B(i) ∩ B(j) ≠ ∅`. Contribuția faptului f crește cu `n_f²·q_f(1−q_f)`, unde
  `n_f` e numărul de claim-uri alese care depind de f: **pătratic în expunere**.
- **De ce diversificăm totuși sub H1: optimizer's curse** (Smith & Winkler 2006). Când alegi
  maximul unor estimări zgomotoase, alegi exact estimările cele mai supraevaluate. Top-k după p
  concentrează expunerea pe cheile cu `q̂` umflat, de exemplu o minciună repetată pe 3 pagini,
  care pare bine susținută. Pierderea dintr-o cheie greșit calibrată e liniară în `n_f`.
- **Analogia din finanțe** (DeMiguel, Garlappi, Uppal 2009, "Optimal versus naive
  diversification"): portofoliul 1/N bate mean-variance out of sample, pentru că eroarea de
  estimare înghite câștigul din optimizare. La noi analogul e plafonul de expunere per fapt de
  bază.
- **Scor neliniar** (necunoscut, deci trebuie acoperit):
  - **Prag de precizie**: dacă suntem peste prag, vrem varianță mică; dacă suntem sub, vrem
    varianță mare.
  - **Penalizare pe duplicate**: un duplicat valorează 0 sau negativ, deci dedup și
    diversitate.
  - **Recompensă de acoperire** ("claims that connect what the universe says"): obiectiv
    submodular, unde diversitatea crește valoarea așteptată.
  - **Penalizare o dată per fapt greșit**: favorizează concentrarea pe puține fapte foarte
    sigure, adică opusul diversificării.

  Concluzie: nu există o direcție universal corectă. De aici vine selecția robustă (3.5, C9).

### 3.2 Defectul lui `max` pentru erori corelate

Cu `Sim2 = Jaccard(B(i), B(j))`:
- `compare(A,B)` și `compare(A,C)` au similaritatea 1/3;
- după ce `compare(A,B)` e ales, `compare(A,D)`, `compare(A,E)` și așa mai departe primesc
  toate penalizarea 1/3, oricâte claim-uri pe A sunt deja în set;
- deci expunerea pe A poate crește nelimitat, cu penalizare constantă.

Remedii:
1. **Agregare `sum`**: `score(d|S) = λ·p_d − (1−λ)·Σ_{s∈S} sim(d,s)`. E echivalent cu greedy
   mean-variance (Wang & Zhu 2009) când `sim` e covarianța erorilor.
2. **Penalizare pe expunere**: `− μ·Σ_{f∈B(d)} g(n_f(S))`, cu g crescătoare, de exemplu
   liniară sau pătratică.
3. **Plafon strict**: `n_f(S) ≤ C` pentru orice f. Pentru claim-urile cu un singur fapt de bază
   e un matroid partiție. Pentru claim-urile cu două fapte (compare, relation) e o intersecție
   de constrângeri, cu garanție teoretică mai slabă, dar bună în practică.
4. **Obiectiv concav de acoperire**: `Σ_f w_f·√n_f(S)` sau noisy-OR, care e submodular.

### 3.3 Termenul de relevanță contează mai mult decât λ

MMR e exact atât de bun cât e `p`. `p` trebuie să fie **P(valid ∧ true)**, diferit pe tip:

| Tip | Ce trebuie să fie adevărat | Riscuri | Idee |
| --- | --- | --- | --- |
| `fact` | valoarea ține pe 29 Oct 2026 | staleness, volatilitate, pagini care mint | cel mai fragil tip; penalizează vechimea ultimei observații |
| `compare` gt/lt | ordinea ține pe 29 Oct 2026 | se schimbă una din valori | **margin-aware**: o diferență mare față de volatilitatea istorică e robustă chiar dacă valoarea e ușor veche; `P(ordine) ≥ P(ambele valori exacte)` |
| `compare` eq | egalitate exactă | orice schimbare | evită, cu excepția cazului în care ambele valori sunt foarte sigure |
| `change` | a ținut `from`, apoi `to` | o valoare falsă în istoric | nu depinde de data de referință; contractul spune doar "held from, and later to", deci **orice pereche ordonată i<j** cu valori distincte e validă, nu doar cele consecutive, ceea ce mărește pool-ul |
| `at_event` | valoarea la data evenimentului | o schimbare nevăzută înaintea evenimentului | istoric, robust la vechimea paginilor recente |
| `relation` | atributul țintei cât timp link-ul o numea | intervalul link-ului | istoric |

Plus **P(valid)**: textul trece de referee-ul determinist din `claim-forms.md` și
`value-forms.md`. Un validator propriu care reproduce toate exemplele din contracte duce
P(valid) aproape de 1 pentru template-urile testate.

### 3.4 Similaritatea potrivită pentru claim-uri

Textul aproape nu contează pentru risc. Contează structura. În ordinea importanței:
1. **Fapte de bază comune** (`B(i) ∩ B(j)`): erori corelate. Varianta principială e
   corelația erorilor, calculată din `q_f`.
2. **Același subiect**: pagini comune, entitate cu istoric mincinos.
3. **Aceeași cheie (subject, attribute)** pe tipuri diferite: de exemplu `fact` și `change`
   pe aceeași cheie.
4. **Același tip sau template**: contează doar dacă scorul răsplătește varietatea.
5. **Duplicate oglindite**: `compare(A,B,gt)` ≡ `compare(B,A,lt)`. Le tratăm ca identice
   (similaritate 1) și le eliminăm la dedup.

### 3.5 Experimentul X1: selecția claim-urilor pe practice.csv

**Setup** (worker Opus, script
[`analysis/mmr/exp-claims/claims_mmr.py`](../../analysis/mmr/exp-claims/claims_mmr.py),
2,5 s, seed fix, 5.000 de extrageri Monte Carlo):
- **Pool**: construit din formele rândurilor `true`, cu valori exacte. 7.017 candidați: 501
  fact, 4.464 compare, 324 change, 1.701 at_event, 27 relation. Folosesc 501 chei și 62 de
  subiecte.
- **p proxy**: euristic, **necalibrat**, cu suport, conflicte, volatilitate și staleness.
  Contează doar comparațiile relative, nu nivelurile absolute.
- **Simulare**: fiecare cheie e corectă cu probabilitatea `q_f`, iar un claim e corect dacă
  toate cheile lui sunt corecte. Simularea verifică faptul că media simulată = Σp.
- **Structura de hub-uri**: datele evenimentelor sunt hub-uri. `Maps Day.date` are 437 de
  candidați dependenți, `Cloud Next.date` 432, outage-ul 412. Mediana e 13 candidați pe cheie.

Rezultate la **k=1.000** (stres maxim: 1.000 alese din doar 501 chei):

| Strategie | E[#corecte] | sd | p1 | Expunere max | Chei distincte | Pierdere dacă cheia cea mai expusă e falsă |
| --- | --- | --- | --- | --- | --- | --- |
| S0 top-k după p | **710,7** | 47,2 | 587 | 104 | 386 | 104 |
| MMR λ=0,5 | 691,5 | 44,9 | 573 | 97 | 501 | 97 |
| MMR λ=0,7 | 697,5 | 43,2 | 584 | 97 | 494 | 97 |
| MMR λ=0,95 | 710,5 | 47,2 | 586 | 104 | 397 | 104 |
| **Plafon C=10** | 689,6 | **30,9** | **616** | **10** | 440 | **10** |
| Plafon C=5 | 664,2 | 24,7 | 606 | 5 | 490 | 5 |
| Cote egale pe tip + MMR | 699,6 | 60,1 | 526 | 155 | 462 | 155 |
| Acoperire μ=0,1 | 706,5 | 45,9 | 581 | 119 | 469 | 119 |
| DPP greedy | 693,7 | 37,5 | 594 | 85 | 501 | 85 |

Rezultate pe ipotezele de scor (normalizate 0-1; în paranteză, raportul față de cea mai bună
strategie pe ipoteza respectivă):

| Strategie (k=1.000) | H1 precizie | H2 duplicate numărate o dată | H3 precizie × √acoperire | Cel mai slab raport (maximin) |
| --- | --- | --- | --- | --- |
| S0 top-k | **0,711** | 0,623 (0,90) | 0,442 (0,90) | 0,90 |
| MMR λ=0,5 | 0,691 (0,97) | **0,691** | 0,489 (1,00) | **0,97** |
| MMR λ=0,7 | 0,697 (0,98) | 0,668 (0,97) | 0,490 (1,00) | **0,97** |
| Plafon C=10 | 0,690 (0,97) | 0,571 (0,83) | 0,457 (0,93) | 0,83 |
| DPP | 0,694 (0,98) | 0,598 (0,87) | **0,491** | 0,87 |

Ce înseamnă:
1. **Defectul `max` e confirmat empiric.** Mediana max-sim a candidaților rămași e 0,30 la
   pasul 50 și 0,80 la pasul 500: penalizarea se saturează și nu mai separă candidații.
   MMR-ul clasic schimbă acoperirea (386 → 501 chei), dar nu expunerea maximă (104 → 97).
2. **Plafonul controlează coada de risc**:
   - la stresul "pagină mincinoasă" (cheile cu un rând fals au q=0,5): p1 543 la C=5,
     față de 534 la top-k;
   - la stresul "shrink30" (toate q trase cu 30% spre 0,5): plafonul C=10 pierde doar 1,1 în
     E și câștigă 45 la p1;
   - adversarial, dacă cele mai expuse 5 chei sunt greșite: top-k pierde 203 claim-uri,
     plafonul C=10 doar 47.
3. **MMR λ 0,5-0,7 câștigă pe H2 și H3 (+11%)**, adică dacă scorul penalizează duplicatele sau
   răsplătește acoperirea. Plafonul pierde pe H2 dintr-un motiv mecanic: împinge selecția
   spre `fact` și `change` pe aceeași cheie, care au aceeași mulțime de fapte de bază.
4. **Cotele egale pe tip sunt cele mai proaste pe risc.** Forțează 243 de claim-uri
   `at_event`, care se îngrămădesc pe datele evenimentelor (expunere 155, p1 −61). Dacă vrei
   mix de tipuri, combină cotele cu un plafon, nu cu MMR.
5. **La k=100** (raportul pool/k realist, pentru că rularea are ~10× mai multe rânduri):
   - top-k e deja divers: expunere max 3, 96 de chei distincte;
   - plafoanele C ≥ 3 **nu se activează deloc**;
   - MMR λ=0,95 costă 0,08 claim-uri și scade sd cu 6%.

   Deci plafonul e **asigurare gratuită** când nu e nevoie de ea și salvează coada când e.
6. **Hibridul plafon + MMR (S6, S7)**, rulat în a doua trecere. Maximin = minimul, peste
   H1-H3, al raportului față de cea mai bună dintre cele 20 de strategii testate:

   | Strategie (k=1.000) | E | sd | p1 | Expunere max | Pierdere: cheia cea mai expusă / primele 5 | Maximin H1-H3 |
   | --- | --- | --- | --- | --- | --- | --- |
   | S0 top-k | 710,7 | 47,2 | 587 | 104 | 104 / 203 | 0,899 |
   | MMR λ=0,5 | 691,5 | 44,9 | 573 | 97 | 97 / 195 | **0,973** |
   | Plafon C=10 | 689,6 | 30,9 | 616 | 10 | 10 / 47 | 0,826 |
   | **Plafon C=10 + MMR λ=0,5** | 672,7 | 32,8 | 598 | 10 | 10 / 47 | **0,935** |
   | Plafon C=10 + MMR λ=0,85 | 687,0 | 30,1 | 615 | 10 | 10 / 47 | 0,851 |
   | Plafon C=10 + top-3-mean λ=0,7 | 683,6 | **28,0** | **617** | 10 | 10 / 46 | 0,802 |
   | Plafon C=5 + MMR λ=0,7 | 662,1 | 25,3 | 602 | 5 | 5 / 25 | 0,766 |

   - **Frontul Pareto** (maximin vs p1): MMR λ=0,5 → MMR λ=0,7 → hibrid λ=0,5 → hibrid λ=0,7
     → hibrid λ=0,85 → plafon simplu → top-3-mean. Top-k, DPP și cotele sunt dominate.
   - **Hibridul C=10 λ=0,5 e compromisul**: bate top-k pe ambele axe și ține pierderea maximă
     la 10 claim-uri.
   - **C=5 e prea strâns**: costă 47-60 de claim-uri din E fără să bată C=10 pe p1.
   - **Plafoanele pierd pe H2.** Plafonul împinge selecția spre `fact` și `change` pe aceeași
     cheie, care au aceeași mulțime de fapte de bază. Un plafon pe **mulțimea** de fapte, nu
     doar pe fapt, ar repara asta (netestat).
   - **La k=100 plafonul nu se activează niciodată**, deci hibridul = MMR. Alegerea se reduce
     la λ: între 0,85 și 0,95, H1 rămâne la 0,5% de top-k, cu expunere 1.

Limitările proxy-ului:
- Chei independente: o pagină care minte pe mai multe chei le-ar lega, și asta ar favoriza
  diversificarea pe subiecte mai mult decât arată simularea.
- Nicio validare a textului randat (de exemplu at_event pe boolean sau compare eq pe date).
- Compare într-o singură orientare.

Raport complet: [`analysis/mmr/exp-claims/REPORT.md`](../../analysis/mmr/exp-claims/REPORT.md).

### 3.6 Algoritmul recomandat (pentru Rust)

```
input:  candidați c cu p_c, B(c) (fapte de bază), subiect, tip; k = 1000; C (plafon); λ; cote pe tip
0. dedup: cheie canonică (tip, forme sortate; compare oglindit normalizat la gt/lt canonic)
          + elimină orice claim al cărui text e identic cu un rând de input ("not new")
1. heap max după score(c) = λ·p_c − (1−λ)·pen(c|S), inițial pen = 0
2. index inversat: fapt f → candidați; subiect → candidați
3. repetă până |S| = k:
     scoate vârful c; dacă scorul lui e stale, recalculează și reinserează (lazy greedy)
     dacă vreun f ∈ B(c) are n_f = C, sau cota tipului e plină: aruncă c, continuă
     adaugă c în S; n_f += 1 pentru f ∈ B(c)
     (penalizarea vecinilor crește doar pentru candidații din indexul lui B(c) și al subiectului)
4. scrie S în ordinea selecției (prefix-optimal: dacă se apropie deadline-ul, primele m sunt deja cele mai bune)
```

- **Lazy greedy e exact, nu aproximativ.** Pentru `sim ≥ 0`, scorul fiecărui candidat e
  ne-crescător pe măsură ce S crește, atât cu agregarea `max`, cât și cu `sum`. O intrare
  stale din heap e deci o limită superioară validă, iar rezultatul e identic cu greedy-ul
  plin (Minoux 1978).
- **Cost**: cu similaritate structurală rară, fiecare selecție atinge doar vecinii din
  indexul inversat. N = 10⁵ și k = 1.000 înseamnă milisecunde în Rust, fără nicio
  dependență externă.
- **Fără crate.** Pe crates.io există `mmr-rerank` (MMR pe o matrice densă de perechi) și
  `divsel` (GIST max-min), dar niciunul nu face lazy greedy, plafoane sau DPP. Bucla de ~50 de
  linii o scriem noi.
- **Ordinea de ieșire**: ordinea greedy e și ordinea de scriere. Combinată cu scrierea
  `output.tmp` urmată de rename, oferă siguranță la deadline.

---

## 4. Etichetarea: unde MMR-ul clasic strică

### 4.1 Experimentul X2: evidence retrieval pe practice.csv

**Setup:**
- **Interogări**: 1.897 de rânduri.
- **Corpus**: celelalte 1.896.
- **Reprezentare**: TF-IDF pe caractere 3-5 grame, care a ieșit cea mai bună (Recall@10
  0,928, față de 0,924 pe cuvinte).
- **Dovada decisivă** `D(q)`: rândul adevărat cu ultima dată ≤ data lui q pe aceeași cheie,
  plus primul de după.

| Strategie (k=10) | Recall@10 | Decisive (toate) | Decisive (≥1) | Redundanță |
| --- | --- | --- | --- | --- |
| Top-k cosinus | 0,928 | **0,559** | 0,853 | 0,299 |
| MMR λ=0,5 | 0,912 | 0,266 | 0,641 | 0,088 |
| MMR λ=0,7 | **0,939** | 0,483 | 0,816 | 0,199 |
| MMR λ=0,9 | 0,935 | **0,561** | **0,858** | 0,273 |
| MMR pe dată (pagină) λ=0,7 | 0,933 | 0,521 | 0,849 | 0,233 |
| Recency τ=90 zile + MMR | 0,839 | 0,385 | 0,794 | 0,113 |

- **Doar acoperirea crește.** MMR λ=0,7 urcă Recall cu 1,1 puncte, dar scade dovada decisivă
  cu 7,6 puncte. **Rândurile false pierd cel mai mult**: Decisive-all 0,453 → 0,326.
- **Motivul.** Dovada decisivă e de obicei o **reformulare aproape identică a aceluiași
  fapt**, pe altă pagină, exact ce elimină penalizarea de diversitate. La verificare,
  redundanța înseamnă **coroborare**, nu zgomot.
- **Verificatorul oracol** (parser perfect, doar rânduri adevărate), la k=20: top-k 0,512
  accuracy, MMR 0,9 0,516, MMR 0,7 0,506. Plafonul cu toate rândurile vizibile e doar 0,557,
  deci **retrieval-ul nu e gâtul de sticlă**. Sunt două probleme mai mari:
  - 412 rânduri true nu au nicio observație anterioară, de exemplu un anunț nou pe pagina lui;
  - granularitatea valorilor diferă (`2025-11` vs `2025-11-04`).
- **Cost**: 3,9 ms/interogare top-k, 4,7 ms MMR, pe un corpus de 19k. Pentru 18.000 de
  interogări înseamnă ~70-85 s, deci costul nu decide nimic.

Raport complet: [`analysis/mmr/exp-evidence/REPORT.md`](../../analysis/mmr/exp-evidence/REPORT.md).

### 4.2 Unde intră de fapt ideea "penalizează redundanța" la etichetare

Cu un parser text → (subject, attribute, value), evidence retrieval devine **lookup exact pe
cheie**. Partea grea rămâne agregarea a multe observații datate, unele copiate, unele false.
Asta e **truth discovery cu dependență între surse**:

- **Dong, Berti-Equille, Srivastava (VLDB 2009).** O valoare falsă se răspândește prin copiere.
  Două surse care împart o valoare *rară sau falsă* sunt probabil dependente. Votul unei surse
  e scalat cu probabilitatea că nu a copiat. Pe date reale (cărți), precizia a urcat de la
  **0,71** (vot naiv) la **~0,89**.
- **Li et al. (VLDB 2013).** Votul naiv dă 0,908 pe Stock și 0,864 pe Flight. Flight e mai slab
  în principal din cauza copierii valorilor greșite. Aproximativ o treime din inconsistențe
  vin din date **învechite**, adică exact natura datasetului nostru.
- **Analogul MMR**, netestat: **vot cu discount MMR**. Ordonezi observațiile după încredere, iar
  fiecare observație nouă primește ponderea `trust · (1 − max sim cu cele deja numărate)`, unde
  `sim` e aceeași pagină, aceeași valoare rară sau același template. Dong e mai principial,
  pentru că se uită la valori rare comune, nu la text.

### 4.3 Opțiuni concrete la etichetare (în ordinea valorii)

| ID | Opțiune | Status | De ce |
| --- | --- | --- | --- |
| L0 | Lookup pe cheie după parsare, fără MMR | standard | X2: retrieval-ul nu e limita; parserul și regulile temporale sunt |
| L1 | Fallback pe text: top-k=20, fetch 100, char 3-5 grame | **măsurat azi** | cel mai bun pe dovada decisivă |
| L2 | Dacă vrei MMR pe text: doar λ ≥ 0,9, ca dedup ușor | **măsurat azi** | λ ≤ 0,7 strică dovada decisivă, mai ales pe rândurile false |
| L3 | MMR pe valori, nu pe rânduri: grupează pe (cheie, valoare), MMR peste valori distincte, plus un slot forțat pentru ultima observație ≤ dată | netestat (R2 §2.3) | o valoare veche repetată de 30 de ori ocupă un singur slot; conflictele ies la suprafață |
| L4 | Discount pe copii, stil Dong: valori rare comune între pagini înseamnă dependență | testat în literatură; **X3: ca feature în plus nu ajută** (4.4); ca dedup la sursă, netestat | 47 de valori false repetate în practice |
| L5 | Încredere pe pagină din etichetele practice: rândurile practice vin etichetate în input, deci paginile cu rânduri false sunt cunoscute | netestat | 34 de pagini ≥ 50% false; o pagină mincinoasă e probabil mincinoasă și pe rândurile neetichetate |
| L6 | Anti-MMR: caută dovezi redundante care concordă (coroborare) | netestat (R3 8.8), susținut indirect de X2 | coroborarea independentă crește q_f |
| L7 | `unsure` doar când nu există nicio observație independentă compatibilă cu data | literatură (evidence sufficiency) | baza `unsure` e doar 2% (39/1.897), deci pragul trebuie să fie conservator |
| L8 | Context de pagină pentru subiecte implicite ("He begins with...") | netestat | 665 de rânduri au subiect implicit; pagina se reconstruiește din id-uri consecutive cu aceeași dată, dacă id-urile rămân în ordine la rulare (neverificat) |

### 4.4 Experimentul X3: dovezi independente peste V11 (punctul 1)

Modelul de etichetare al echipei e în [knowledge-base.md](knowledge-base.md):
**V11lr-self1**.
- **Ce face:** regresie logistică pe feature-uri de dovezi per fapt, plus suspiciune pe pagină,
  calibrare izotonică și o rundă de self-training.
- **Rezultat:**
  - în regimul R80 (80% din pagini etichetate): 0,907 accuracy, Brier 0,073;
  - în regimul R10 (10% etichetate, cel mai apropiat de rularea reală): 0,809 accuracy,
    Brier 0,124.
- **Referința "always true":** 0,833 (R80) și 0,831 (R10).

X3 a verificat dacă ideea MMR "numeri surse independente, nu rânduri" îl îmbunătățește. Codul
e în [`labs/kb-experiments/v12.py`](../../labs/kb-experiments/v12.py), iar raportul în
[`REPORT_v12.md`](../../labs/kb-experiments/REPORT_v12.md). Cele trei variante au fost fixate
**înainte** de orice rezultat:

| Variantă | Ce adaugă la V11 |
| --- | --- |
| V12pages | numărul de pagini distincte, în loc de rânduri, pentru ancore, voturi și negative |
| V12mmr | masa de dovezi cu discount MMR: fiecare dovadă contează `rel · (1 − max sim)` față de cele deja numărate, unde `sim` = 1 pentru aceeași pagină, altfel cosinus TF-IDF pe text |
| V12mmr-replace | aceeași masă, dar **în locul** numărătorilor brute |

**Pe practice nu câștigă nimic peste zgomot** (comparație pereche, split cu split):

| Variantă | Regim | Acc | Recall false | Precizie false | Brier |
| --- | --- | --- | --- | --- | --- |
| V11lr-self1 | R80 | 0,907 | 0,695 | 0,793 | 0,073 |
| V12mmr | R80 | 0,905 | 0,723 | 0,766 | 0,073 |
| V12mmr-replace | R80 | 0,902 | 0,741 | 0,737 | 0,074 |
| V11lr-self1 | R10 | 0,809 | 0,461 | 0,499 | 0,124 |
| V12mmr | R10 | 0,803 | 0,523 | 0,475 | 0,124 |
| V12mmr-replace | R10 | 0,822 | 0,459 | 0,535 | 0,125 |

La R80, precizia pe false chiar scade în toate cele 5 fold-uri (−0,027 la V12mmr, −0,056 la
replace).

**Găsirea importantă e un risc pentru V11, nu un câștig pentru MMR.**
- **Stresul "minciuni copiate la test" (hlie)** pune 3 copii ale fiecărui rând fals de pe
  paginile **neetichetate** din split. Copiile sunt pe pagini noi, la +1, +7 și +30 de zile.
  Ele nu sunt niciodată etichetate și nu intră niciodată în evaluare.
  - **V11** cade: recall pe false de la 0,461 la **0,204**, mai rău în 10 din 10 splituri;
    Brier +0,037, accuracy −0,084.
  - **V9lr**, fără self-training, cade și mai tare: de la 0,465 la 0,120.
- **Controlul:** același număr de copii, dar ale rândurilor adevărate, nu schimbă practic
  nimic (recall pe false +0,006).
- **V12mmr nu protejează.** Degradează cu 0,065 **mai mult** decât V11 și e mai bun doar în
  4 din 10 splituri. V12mmr-replace e la nivel de zgomot.
- **De ce:** copiile ajung la model și pe alte canale, unde contează la greutate întreagă:
  - feature-urile de tip bracket (cea mai apropiată observație înainte și după);
  - cele numerice;
  - votul ponderat `marg`, care alimentează și suspiciunea pe pagină;
  - ancorele pseudo-"true" din self-training.

  Discountul MMR a atins doar coloanele adăugate.
- **Primele scenarii de stres** (toate rândurile false copiate, inclusiv cele de pe pagini
  etichetate, plus un scenariu "mixt") erau **confundate**. La antrenare, "are duplicat"
  devenea un indiciu pentru eticheta false, așa că V11 părea să *câștige* sub copiere.
  Reviewerul Opus a prins confuzia, iar workerul a refăcut testul pe pagini neetichetate.
  Cifrele vechi rămân în `results_v12.txt`, marcate ca atare.

**Verdict pentru punctul 1:**
- **Nu adoptăm V12 în V11.** MMR ca feature în plus nu ajută nici pe practice, nici sub atac.
- **Lecția MMR se aplică la sursă, nu la feature.** Rândurile aproape identice de pe pagini
  diferite (TF-IDF ≥ 0,9) trebuie unite într-o singură sursă **înainte** de calculul oricărui
  feature. Asta înseamnă bracket, numeric, `marg`, suspiciune pe pagină și self-training.
  Netestat; e primul lucru de încercat dacă rămâne timp.
- **Diagnostic ieftin la rulare:** cât de des apar texte aproape identice pe pagini diferite în
  cele ~20.000 de rânduri. Dacă apar des, riscul de mai sus e real, iar dedup-ul la sursă devine
  prioritar.

---

## 5. Date de antrenare și calibrare

| ID | Opțiune | Sursă | Notă |
| --- | --- | --- | --- |
| D1 | Poartă de diversitate pentru rândurile sintetice generate cu LLM la dev-time: păstrezi un rând nou doar dacă similaritatea cu toate cele deja păstrate e sub prag | Self-Instruct (ROUGE-L), SemDeDup, D4 | evită 500 de variații pe același template; provenance-ul se înregistrează, conform AGENTS.md |
| D2 | MMR sau k-center ca să alegi ce exemple verifici de mână | core-set (Sener & Savarese 2018), BADGE | doar dacă există timp de etichetare manuală |
| D3 | Split-uri pe clustere de template, nu aleatoare | analiza practice: leakage între split-uri | nu e MMR, dar e aceeași idee de diversitate aplicată la evaluare |
| D4 | Setul de **calibrare**: stratificat, **nu** diversificat | R2 §5 | calibrarea trebuie să reflecte distribuția reală, inclusiv masa de template-uri aproape identice |
| D5 | Exemplare diverse pentru un parser kNN sau pe template-uri (TopK-Div) | ICL diversity (arXiv 2505.19426) | diversitatea ajută pe input-uri out-of-distribution; top-k câștigă in-distribution |

---

## 6. Catalogul complet de opțiuni pentru claim-uri

Legendă status: **T-azi** = măsurat azi pe practice; **T-lit** = testat în literatură în alt
domeniu; **N** = netestat nicăieri, din câte am găsit.

| ID | Opțiune | Status | Ce câștigi | Risc sau cost | Cum testezi |
| --- | --- | --- | --- | --- | --- |
| C0 | Top-k după p (control) | T-azi | optim sub H1 dacă p e corect | expunere maximă pe puține chei | baseline în simulator |
| C1 | Dedup exact pe forma canonică, compare oglindite, text egal cu un rând de input | obligatoriu | fără duplicate și fără claim-uri "not new" | zero | test unitar |
| C2 | MMR clasic, `max`, similaritate structurală, grilă de λ | T-azi | blochează duplicatele aproape identice | nu limitează expunerea (3.2) | X1 |
| C3 | Plafon pe fapt de bază, C ∈ {3, 5, 10}, stil DIVERSUM | T-azi, T-lit (ESBM) | limitează pierderea dintr-o pagină mincinoasă la C claim-uri | pierdere mică de valoare așteptată | X1, sweep pe C |
| C4 | MMR cu agregare `sum` sau covarianță (mean-variance) | T-lit (Wang & Zhu 2009), N pe structură de fapte | penalizează exact riscul corelat | b trebuie acordat | simulator, grilă pe b |
| C5 | Cote pe tip (matroid partiție), proporționale cu fiabilitatea tipului | N | acoperire pe tipuri dacă scorul o cere | costă p dacă un tip e slab | calculează "prețul" cotei: Σ gap p |
| C6 | Obiectiv de acoperire (facility location, noisy-OR), sau în două etape: acoperire, apoi MMR | T-lit (Lin & Bilmes) | maxim sub ipoteza de acoperire | forțează claim-uri cu p mai mic; limitează etapa 1 la ~30% | X1 S4, plus două etape |
| C7 | DPP greedy MAP, q = cote^α, S = Jaccard pe fapte (PSD) | T-lit (Chen 2018) | calitate × diversitate fără λ ad-hoc | O(n·k²); rulează pe un pool prefiltrat de ~10⁴ | simulator |
| C8 | Robust la τ fapte mincinoase: maximizezi scorul după eliminarea celor τ fapte cu cea mai mare expunere | T-lit (Orlin et al.), N cu eliminări pe seturi | garanție de worst case | puțin conservator | stress test τ=1,5 |
| C9 | **Meta: alegi selectorul prin maximin-regret** pe H1-H6 simulate (idee SATURATE, Krause 2008) | N | robust la scorul necunoscut | depinde de simulatorul de q | rulezi toate selectoarele, normalizezi pe ipoteză, iei maximin |
| C10 | Uniune hedge: 700 din C3 + 300 din C6 | N | regret limitat sub ambele ipoteze | niciuna nu e optimă | simulator |
| C11 | λ dependent de p: penalizare ∝ p(1−p), deci fără presiune pe claim-urile aproape sigure | N, dar rezultă din formula varianței | păstrează claim-urile sigure, diversifică pe cele medii | încă un hiperparametru | simulator |
| C12 | Relevanță margin-aware la compare | N | compare robuste la valori ușor vechi | trebuie estimată volatilitatea pe atribut | backtest temporal (C16) |
| C13 | Relevanță staleness-aware la fact; preferință pentru tipuri istorice (change, at_event, relation) | N | evită cel mai fragil tip | dacă scorul vrea mix de tipuri, combină cu C5 | backtest temporal |
| C14 | Pool de change extins: toate perechile ordonate i<j, nu doar cele consecutive | contract | pool mai mare, deci mai multă libertate de selecție | o valoare falsă în mijloc produce mai multe claim-uri greșite, deci plafonul C3 contează mai mult | numără pool-ul, verifică pe practice |
| C15 | Coroborare: fapte de bază susținute de ≥ 2 pagini independente, cu discount Dong | T-lit (Dong 2009) | q_f mai bun, deci p mai bun pentru tot | puține chei au ≥ 2 pagini independente | precizia pe practice: coroborat vs singleton |
| C16 | **Backtest temporal** pentru calibrarea lui p: construiești KB din paginile de până la data T, generezi claim-uri, verifici cu rândurile de după T | N | singurul mod de a măsura p real fără referee | rândurile de după T sunt și ele zgomotoase | split la 2026-06 și 2026-08 |
| C17 | Confidence = p calibrat (isotonic pe backtest), tăiat la [0,5, 1] | T-lit (reguli de scoring proper) | robust dacă scorul folosește confidence | n/a | Brier și reliability diagram |
| C18 | Dedup pe text randat (MinHash) și diversitate de template | N | doar dacă juriul deduplică textual | aproape zero | test unitar |
| C19 | **Auto-tuning la rulare**: simulatorul Monte Carlo rulează pe pool-ul real în Rust (~1-3 s) și alege (C, λ) prin maximin-regret pe H1-H6 | N | se adaptează la structura reală de hub-uri, pe care practice nu o reproduce (k=100 vs k=1.000 dau concluzii diferite) | cod în plus pe calea critică; are nevoie de fallback fix | rulează pe practice și pe un pool mărit sintetic; compară cu (C, λ) fix |
| C20 | **Hibrid plafon + MMR**: C=10 plus λ=0,5 | **T-azi**: cel mai bun compromis | maximin 0,935, p1 +11, sd −31%, pierdere maximă 10 | −38 E sub H1 (−5,3%) pe proxy | gata; urmează pe pool-ul real |
| C22 | Plafon pe **mulțimea** de fapte de bază (fact și change pe aceeași cheie împart plafonul), plus plafon pe fapt | N | repară slăbiciunea plafoanelor pe H2 | n/a | o linie în simulator |
| C21 | Hub-uri de evenimente: plafon separat pe cheile `event.date` (437 de candidați pe `Maps Day.date`) sau p redus pentru at_event pe evenimente cu dată incertă | N | hub-urile sunt sursa principală de concentrare | n/a | simulator |

**Ipotezele de scoring pentru C9:**
- **H1** precizie;
- **H2** precizie cu duplicate (aceeași mulțime de fapte de bază) numărate o singură dată;
- **H3** precizie × √(acoperire);
- **H4** Brier pe confidence;
- **H5** prag de precizie (de exemplu ≥ 95%);
- **H6** penalizare o dată per fapt greșit.

---

## 7. Plan de testare până la freeze (29 Oct, 11:00)

Ordinea e dată de valoare împărțită la timp. Pașii 1-4 sunt ieftini și independenți de
restul pipeline-ului.

0. **Default de plecare, gata testat pe proxy: C20**, adică plafon C=10 (~1% din k) + MMR
   λ=0,5. Următorul test ieftin e C22 (plafon pe mulțimea de fapte), ca să recupereze H2.
1. **C1 + C3 + C2 în Rust**, ~50 de linii, fără dependențe. Folosește indexul inversat și lazy
   greedy din 3.6. Test unitar: plafonul ține, nu ies duplicate oglindite, ordinea e
   deterministă.
2. **Simulatorul X1 portat sau rulat pe pool-ul real**, cu cele ~20k rânduri, în timpul
   rulării. Măsori expunerea maximă și numărul de chei distincte; la rulare nu vom avea
   etichete pentru claim-uri.
3. **C16 backtest temporal pe practice**, ca să calibrezi `q_f`. Fără el, orice λ e acordat pe
   un p inventat.
4. **C9**: alegi plafonul C și λ prin maximin-regret pe H1-H6 în simulator. Fixezi valorile în
   config.
5. **L1 sau L2 la etichetare**: top-k=20 sau MMR 0,9 doar ca fallback când parserul nu găsește
   cheia. Nu pune MMR cu λ ≤ 0,7 pe calea de etichetare.
6. **Dacă mai e timp**: L4 sau L5 (discount pe copii, încredere pe pagină), C12 (margin-aware
   la compare), C14 (pool de change extins).

**Criterii de decizie:**
- **Plafonul C**: alegi cea mai mică valoare care costă sub 3% din valoarea așteptată sub H1
  față de C0 și reduce expunerea maximă de cel puțin 3 ori. Pe practice, C=10 la k=1.000 îl
  satisface: −3,0% și 104 → 10.
- **λ**: dacă hibridul C20 nu bate plafonul simplu pe maximin, rămâi pe plafon cu λ=0,95, adică
  MMR doar ca tie-breaker.

---

## 8. Limitări și ce nu am găsit

- **p e un proxy** (euristic, necalibrat). Rezultatele X1 arată mecanismul și ordinea de
  mărime, nu scorul real. Calibrarea vine din C16.
- **Practice e ~1/10 din rulare.** Aglomerarea de duplicate aproape identice va fi mai mare la
  20k de rânduri, iar pool-ul de claim-uri va fi mai mare.
- **Formula de scor e nepublicată**, inclusiv după verificarea issue-urilor din starter și a
  repo-ului `hype-arena-chaos`, care conține doar teste de format.
- **Nu am găsit:**
  - un test controlat MMR vs top-k pe FEVER, HoVer sau FEVEROUS;
  - MMR aplicat pe surse conflictuale sau temporale;
  - CVaR la selecția de seturi;
  - λ dependent de confidence;
  - MMR cu similaritate definită ca eșec corelat;
  - o comparație între dedup-ul MMR înainte de vot și discount-ul lui Dong.

  Ideile marcate N în catalog sunt deci netestate în literatură.
- **Câteva citări sunt la nivel de abstract sau snippet** (marcate în rapoartele brute):
  arXiv 2204.02007, 2504.13079, 2601.21387, 2605.18776, plus tabelul ESBM. Verifică-le
  înainte să le citezi în pitch.

---

## 9. Referințe principale

- Carbonell & Goldstein, *The use of MMR, diversity-based reranking for reordering documents
  and producing summaries*, SIGIR 1998.
- Gollapudi & Sharma, *An axiomatic approach for result diversification*, WWW 2009.
- Borodin, Lee, Ye, *Max-sum diversification, monotone submodular functions and dynamic
  updates*, PODS 2012: https://arxiv.org/abs/1203.6397
- Lin & Bilmes, *A class of submodular functions for document summarization*, ACL 2011:
  https://aclanthology.org/P11-1052/
- Kulesza & Taskar, *Determinantal point processes for machine learning*, 2012:
  https://arxiv.org/abs/1207.6083
- Chen, Zhang, Zhou, *Fast greedy MAP inference for DPP*, NeurIPS 2018:
  https://arxiv.org/abs/1709.05135
- Wang & Zhu, *Portfolio theory of information retrieval*, SIGIR 2009:
  https://ir.webis.de/anthology/2009.sigirconf_conference-2009.16
- Chen & Karger, *Less is more: probabilistic models for retrieving fewer relevant documents*,
  SIGIR 2006: https://ir.webis.de/anthology/2006.sigirconf_conference-2006.57/
- Santos, Macdonald, Ounis, xQuAD, WWW 2010; Agrawal et al., IA-Select, WSDM 2009; Dang & Croft,
  PM-2, SIGIR 2012.
- Krause et al., *Robust submodular observation selection* (SATURATE), JMLR 2008:
  https://www.jmlr.org/papers/v9/krause08b.html
- Orlin, Schulz, Udwani, robust monotone submodular maximization:
  https://arxiv.org/abs/1507.06616
- Mirzasoleiman et al., *Lazier than lazy greedy*, AAAI 2015: https://arxiv.org/abs/1409.7938
- Smith & Winkler, *The optimizer's curse*, Management Science 2006.
- DeMiguel, Garlappi, Uppal, *Optimal versus naive diversification*, RFS 2009.
- Dong, Berti-Equille, Srivastava, *Integrating conflicting data: the role of source
  dependence*, VLDB 2009: https://lunadong.com/publication/dependence_vldb.pdf
- Li et al., *Truth finding on the deep web: is the problem solved?*, VLDB 2013:
  https://arxiv.org/abs/1503.00303
- Yin, Han, Yu, TruthFinder, KDD 2007 / TKDE 2008; Zhao et al., LTM, VLDB 2012:
  https://arxiv.org/abs/1203.0058
- Liu et al., ESBM entity summarization benchmark, ESWC 2020: https://arxiv.org/abs/2003.03734
- AIC CTU la AVeriTeC (MMR în fact-checking, λ=0,75): https://arxiv.org/abs/2410.11446
- Sener & Savarese, core-set, ICLR 2018: https://arxiv.org/abs/1708.00489; SemDeDup:
  https://arxiv.org/abs/2303.09540; D4: https://arxiv.org/abs/2308.12284
- *The role of diversity in in-context learning*, 2025: https://arxiv.org/abs/2505.19426

Lista completă, cu nivelul de verificare pentru fiecare sursă, e în
[`analysis/mmr/research/`](../../analysis/mmr/research/).
