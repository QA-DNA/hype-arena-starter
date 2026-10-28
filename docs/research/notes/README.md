# Knowledge base research notes

Raw reports from the 2026-10-28 research, one per worker, kept as written so nothing is lost.
[The knowledge base research](../knowledge-base.md) is the curated version: where a note and the
report disagree, the report wins, because its verdicts were reconciled against the contract and
the measured results.

| Note | Worker | Covers |
| --- | --- | --- |
| [Truth discovery](truth-discovery.md) | W1, Sonnet 5.5 | Accu, AccuCopy, dynamic-world lifespans, DynaTD, CRH, TruthFinder, LTM, Dawid-Skene, SLiMFast, KBT |
| [Temporal KB](temporal-kb.md) | W2, Sonnet 5.5 | storage, as-of resolution, interval qualifiers, TeCoRe, CoTS, Datalog and logic engines, HMMs, change points, Rust crates |
| [Blame, calibration, claims](blame-calibration-claims.md) | W3, Sonnet 5.5 | noisy-OR and MIL blame, SAT and MaxSAT, Platt, isotonic, Venn-Abers, conformal, claim selection, explanation |
| [Frontier and values](frontier-and-values.md) | W4, Sonnet 5.5 | 2025-2026 sweep, value-consistency rules, unit and interval crates |
| [Experiments report](experiments-report.md) | E1, Opus 5.5 | data facts, V0 to V11 results, failure analysis, rerun commands |

Known errors, marked inline in the notes:

- W4 proposed a rounding tolerance and zero-padding of versions. The contract has neither: values
  are exact, approximate wording makes a value invalid, and `2.3` is not `2.3.0`.
- W4 said names ignore aliases. Names resolve through the lexicon aliases.
- W2 could not confirm that the `scallop` crate is the Scallop language.

## Verified citations

The workers could not verify several papers because Semantic Scholar and DBLP were
rate-limited. These were checked afterwards:

| Paper | Link |
| --- | --- |
| Dong, Berti-Equille, Srivastava: truth discovery in a dynamic world (VLDB 2009) | <https://lunadong.com/publication/lifespan_vldb.pdf> |
| Dong, Berti-Equille, Srivastava: source dependence (VLDB 2009) | <https://lunadong.com/publication/dependence_vldb.pdf> |
| Li et al.: discovery of evolving truth, DynaTD (KDD 2015) | <https://cse.buffalo.edu/~jing/doc/kdd15_evolve.pdf> |
| Li et al.: CRH (SIGMOD 2014) | <https://cse.buffalo.edu/~jing/doc/sigmod14_crh.pdf> |
| Zhao et al.: LTM, a Bayesian approach to truth discovery (VLDB 2012) | <https://arxiv.org/abs/1203.0058> |
| Rekatsinas et al.: SLiMFast | <https://arxiv.org/abs/1512.06474> |
| Dong et al.: Knowledge-Based Trust | <https://arxiv.org/abs/1502.03519> |
| Dong et al.: from data fusion to knowledge fusion | <https://arxiv.org/abs/1503.00302> |
| Li et al.: a survey on truth discovery | <https://arxiv.org/abs/1505.02463> |
| Waguih, Berti-Equille: truth discovery algorithms, an experimental evaluation | <https://arxiv.org/abs/1409.6428> |
| Pasternack, Roth: knowing what to believe (COLING 2010) | <https://aclanthology.org/C10-1099/> |
| Yin, Tan: semi-supervised truth discovery (WWW 2011) | <https://ir.webis.de/anthology/2011.wwwconf_conference-2011.25/> |
| Pal et al.: information integration over time (WWW 2012) | <https://scholars.duke.edu/publication/808866> |
| TeCoRe: temporal conflict resolution | <https://madoc.bib.uni-mannheim.de/42281/> |
| Chekol et al.: uncertainty and time in knowledge graphs (AAAI 2017) | <https://ojs.aaai.org/index.php/AAAI/article/view/10495> |
| Talukdar et al.: CoTS, coupled temporal scoping (WSDM 2012) | <https://ir.webis.de/anthology/2012.wsdm_conference-2012.9> |
| Reliable truth discovery for dynamic and dependent sources (TKDE 2026) | <https://researchers.mq.edu.au/en/publications/reliable-truth-discovery-for-dynamic-and-dependent-sources/> |
| ChronoFact (IJCAI 2025) | <https://arxiv.org/abs/2410.14964> |
