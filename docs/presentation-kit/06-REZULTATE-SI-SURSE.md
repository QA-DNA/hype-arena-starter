# Rezultate, versiuni și surse

Registru editorial pentru toate materialele din acest director. Snapshot verificat: `0dda354944b5d600eafe9ea6f680159440c1c38f`, 29 octombrie 2026. Alte echipe integrează cod în paralel. Un rezultat istoric nu devine automat rezultat pentru noua integrare.

## Ce putem afirma

| Afirmație | Dovadă | Limita care trebuie păstrată |
| --- | --- | --- |
| Două versiuni de câte 1.000.000 de rânduri evaluate | [Raport million V1/V2](../research/million-v1-v2.md) | Cazuri sintetice pereche, aceleași ID-uri; nu observații independente |
| V1 99,5419%; V2 cu extensie 99,7458% | Același raport, tabelele de rezultate | Evaluator adaptat protocolului public; nu accuracy a CLI-ului original pe text arbitrar |
| V2 transfer strict V1: 8,0827% | Același raport | Arată cât contează protocolul și extinderea explicită a limbajului; păstrați-l în anexa tehnică |
| 9.899 inputuri publice identice între V1/V2 | Același raport, secțiunea „Ce schimbă V2” | Celelalte rânduri se modifică, dar cele două pooluri rămân legate prin identitatea cazurilor |
| 87,74% pe 5.000 și 87,58% pe 20.000 de ținte | [Evaluarea înghețată](../handoffs/evidence-graph-runtime.md) | Lumi sintetice independente pentru acea evaluare; nu scorul ascuns al organizatorului și nu certificarea ultimei integrări |
| La 20.000: 58,17% acoperire definitivă, 94,42% corectitudine între predicțiile definitive | Același handoff | Nu prezentați 94,42% ca accuracy pe întregul set; confidence nu este probabilitate calibrată |
| Chain: 89,49% pe P390 în sweep-ul final documentat | [Verificarea chain](../research/kb-chain-verification.md) | Split influențat de selecția checkpoint-ului; rezultat optimist, nu test final independent |
| Docker-ul complet pornește chain | [Dockerfile.competition](../../Dockerfile.competition) | Root Dockerfile rămâne o cale diferită în snapshot; imaginea completă depinde de modele staged local |
| Generatorul produce 1.000 de rânduri, cu verificări de structură | [Integrarea](../handoffs/evidence-main-integration.md) | Checker-ul de format nu certifică adevărul tuturor afirmațiilor |

## Limite care pot schimba o prezentare

- API-ul din snapshot cheamă motorul comun, dar nu trece prin adaptorul CLI pentru extragerea nativă și chain. Diagrama unei unificări complete este o țintă de integrare până la verificarea parității.
- Chain se activează numai în lumile care trec gardurile sale, inclusiv prezența seed-ului canonic și a ambelor clase true/false. Rulează după motor și păstrează fallback-uri. Nu este un înlocuitor universal al motorului.
- G1 poate eticheta `true` o țintă fără fapte extrase. Există garduri pentru unknown explicit, clauze incomplete și entități străine. Nu susțineți că sistemul se abține în toate cazurile fără dovezi.
- Evaluarea înghețată a generatorului din handoff nu demonstrează validarea independentă a tuturor textelor: checker-ul textual limitat certifica 83 și lăsa 917 formulări non-fact în afara gramaticii sale. Nu spuneți „1.000 din 1.000 certificate de evaluatorul oficial”.
- Antrenarea pe practice, holdout-urile de dezvoltare, evaluările înghețate și suitele million au protocoale diferite. Nu le combinați într-o singură cifră.
- Faptul că un set este train-eligible nu dovedește că a fost folosit pentru antrenarea greutăților. Raportul million spune că greutățile nu au fost antrenate pe aceste pooluri.

## Formulări gata de folosit

**Volum:** “We evaluated two versions of a one-million-row synthetic development suite.”

**Evaluare independentă istorică:** “A frozen candidate achieved 87.58% label accuracy on 20,000 targets from a fresh synthetic world. This is separate from the official sample and the final integrated build.”

**Rust:** “We chose Rust for native CPU execution and explicit memory control. Performance claims refer to a measured configuration.”

**Incertitudine:** “The interface exposes uncertain outcomes. Our routing and fallback policies still have limits that we evaluate separately.”

**Business:** “Our proposed first pilot is product-fact review using approved sources. We have not yet validated commercial savings.”

## Evitați aceste transformări ale rezultatului

| Formulare neacoperită de dovezi | Formulare precisă |
| --- | --- |
| „Milioane de dataset-uri de training” | Două suite de dezvoltare, câte un milion de rânduri |
| „99,7% pe orice document” | 99,7458% pe V2 cu adaptorul de protocol declarat |
| „87,58% pe sample-ul oficial” | 87,58% pentru candidatul înghețat pe o lume sintetică de 20.000 de ținte |
| „Rust este de zece ori mai rapid” | Alegere pentru execuție nativă; comparația de limbaje nu a fost măsurată |
| „MMR verifică adevărul” | MMR selectează diversitatea după construcția și validarea candidaților |
| „Clientul economisește 40 de ore” | Scenariu ipotetic de 40 de ore; pilotul trebuie să măsoare diferența |
| „Bank-ready / compliance certified” | Scenariu de utilizare propus; accesul, sursele și controlul uman cer lucru separat |

## Surse externe și obligații de prezentare

- [Starter oficial](https://github.com/QA-DNA/hype-arena-starter): frontend live, diagrama arhitecturii, fork și PR, freeze la 11:00.
- [Sample publicat](https://github.com/QA-DNA/hype-arena-starter/blob/main/datasets/sample.csv): calea reală verificată prin API, 20 de rânduri fără etichete.
- [Contract](https://github.com/QA-DNA/hype-arena-starter/blob/main/contracts/README.md): imaginea din root Dockerfile, CSV și resursele execuției.
- [Regulamentul NEXXT](https://nexxtsummit.com/rulebook/): problemă, fezabilitate, adopție și demonstrație în criteriile de evaluare.
- Materialul kickoff furnizat de Teo: video de 3 minute, GitHub repository, slide deck; business mentoring 10%. Extensiile MP4/PDF sunt recomandări de producție, nu cerințe găsite în acel material.
- [Rust](https://rust-lang.org/): proprietățile limbajului, distincte de benchmark-urile aplicației.
- [Stripe: schimbarea prețului abonamentelor](https://docs.stripe.com/billing/subscriptions/change-price): exemplu public de operație care depinde de preț, perioadă și momentul schimbării. Nu dovedește o integrare Stripe, o eroare a serviciului sau o relație comercială cu VERIDYCT.

## Înainte de înregistrare

Notați în fișa echipei commitul prezentat, numele imaginii, configurația activă, URL-ul aplicației și dataset-ul încărcat. Alegeți un singur rând real pentru explicația detaliată. Dacă rezultatul este greșit sau `unsure`, descrieți-l ca atare. Dacă integrarea schimbă rezultatele, actualizați materialele din rularea respectivă, fără să transferați automat scoruri istorice.
