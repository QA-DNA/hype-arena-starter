# results (seed 20261029, 5000 draws, 4s)

observations: 1964 true exact assertions over 501 keys; fact candidates 501; compare pairs skipped as date-overlap-undecidable: 0; events with usable date: 6 (Gemini Launch Night 2025-10-07, Hooly Cloud Next 2026 2026-06-09, Hooly I/O 2026 2026-03-24, Hooly Maps Day 2026-06-23, Made by Hooly 2026 2026-04-28, The May 2026 outage 2026-05-19)

## pool

| type | candidates |
|---|---|
| fact | 501 |
| compare | 4464 |
| change | 324 |
| at_event | 1701 |
| relation | 27 |

total 7017; distinct base keys 501; distinct subjects 62

## candidate p by type

| index | mean | min | 25% | 50% | 75% | max |
|---|---|---|---|---|---|---|
| at_event | 0.390 | 0.061 | 0.281 | 0.362 | 0.479 | 0.791 |
| change | 0.649 | 0.365 | 0.568 | 0.649 | 0.758 | 0.818 |
| compare | 0.449 | 0.092 | 0.354 | 0.439 | 0.539 | 0.793 |
| fact | 0.654 | 0.253 | 0.552 | 0.663 | 0.762 | 0.932 |
| relation | 0.635 | 0.482 | 0.607 | 0.649 | 0.672 | 0.758 |

## dependency (pool)

candidates per base key: max 437, p90 57, mean 26.4, median 13
share of compare candidates touching the 10 most-connected keys: 0.115
top-10 keys: Hooly Maps Day.date(437), Hooly Cloud Next 2026.date(432), The May 2026 outage.date(412), Made by Hooly 2026.date(393), Hooly I/O 2026.date(304), Gemini Launch Night.date(68), Hooly Chrome.stable_release_date(67), Hooly Photos.latest_release_date(64), Holdan.joined(63), Dinesh Chugtay.joined(63)

## strategies k=1000 (mix = fact/compare/change/at_event/relation)

| strategy | E | sd | p5 | p1 | P95 | maxexp | keys | subj | mix | H1 | H2 | H3 | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 top-k | 710.674 | 47.234 | 625.000 | 587.000 | 0.000 | 104 | 386 | 61 | 293/382/190/117/18 | 0.711 | 0.623 | 0.442 |  |
| S1 MMR l=0.5 | 691.487 | 44.877 | 609.950 | 573.000 | 0.000 | 97 | 501 | 62 | 300/371/201/113/15 | 0.691 | 0.691 | 0.489 | med_pen@50=0.30 med_pen@100=0.40 med_pen@500=0.80 |
| S1 MMR l=0.7 | 697.481 | 43.168 | 618.000 | 583.990 | 0.000 | 97 | 494 | 62 | 325/345/209/106/15 | 0.697 | 0.668 | 0.490 | med_pen@50=0.30 med_pen@100=0.30 med_pen@500=0.80 |
| S1 MMR l=0.85 | 708.049 | 45.450 | 625.000 | 589.000 | 0.000 | 100 | 434 | 62 | 297/367/207/113/16 | 0.708 | 0.645 | 0.466 | med_pen@50=0.30 med_pen@100=0.30 med_pen@500=0.80 |
| S1 MMR l=0.95 | 710.528 | 47.230 | 625.000 | 586.000 | 0.000 | 104 | 397 | 61 | 291/384/190/117/18 | 0.711 | 0.632 | 0.448 | med_pen@50=0.30 med_pen@100=0.30 med_pen@500=0.80 |
| S2 cap C=3 | 636.752 | 22.491 | 599.950 | 584.000 | 0.000 | 3 | 501 | 62 | 486/179/313/9/13 | 0.637 | 0.462 | 0.451 |  |
| S2 cap C=5 | 664.154 | 24.708 | 623.000 | 606.000 | 0.000 | 5 | 490 | 62 | 444/232/298/8/18 | 0.664 | 0.507 | 0.465 |  |
| S2 cap C=10 | 689.630 | 30.900 | 638.000 | 616.000 | 0.000 | 10 | 440 | 61 | 363/347/252/18/20 | 0.690 | 0.571 | 0.457 |  |
| S3 quota+MMR .85 | 699.585 | 60.126 | 591.000 | 526.000 | 0.000 | 155 | 462 | 62 | 244/243/243/243/27 | 0.700 | 0.648 | 0.476 | med_pen@50=0.30 med_pen@100=0.30 med_pen@500=0.80 |
| S4 cover mu=0.1 | 706.487 | 45.920 | 617.000 | 581.000 | 0.000 | 119 | 469 | 62 | 309/325/224/124/18 | 0.706 | 0.627 | 0.484 |  |
| S4 cover mu=0.3 | 690.607 | 43.470 | 605.000 | 569.000 | 0.000 | 115 | 501 | 62 | 288/365/223/111/13 | 0.691 | 0.618 | 0.489 |  |
| S5 DPP greedy | 693.720 | 37.546 | 626.000 | 594.000 | 0.000 | 85 | 501 | 62 | 359/271/281/80/9 | 0.694 | 0.598 | 0.491 | dpp_picked=567 |
| S6 cap C=5+MMR l=0.5 | 650.280 | 26.154 | 608.000 | 587.990 | 0.000 | 5 | 501 | 62 | 382/334/250/16/18 | 0.650 | 0.561 | 0.460 | med_pen@50=0.30 med_pen@100=0.40 med_pen@500=0.80 |
| S6 cap C=5+MMR l=0.7 | 662.056 | 25.269 | 620.000 | 602.000 | 0.000 | 5 | 501 | 62 | 418/266/287/11/18 | 0.662 | 0.529 | 0.469 | med_pen@50=0.30 med_pen@100=0.30 med_pen@500=0.80 |
| S6 cap C=5+MMR l=0.85 | 663.551 | 24.837 | 623.000 | 604.990 | 0.000 | 5 | 500 | 62 | 433/245/296/8/18 | 0.664 | 0.518 | 0.469 | med_pen@50=0.30 med_pen@100=0.30 med_pen@500=0.80 |
| S6 cap C=10+MMR l=0.5 | 672.722 | 32.820 | 619.000 | 597.990 | 0.000 | 10 | 501 | 62 | 326/427/210/18/19 | 0.673 | 0.647 | 0.476 | med_pen@50=0.30 med_pen@100=0.40 med_pen@500=0.80 |
| S6 cap C=10+MMR l=0.7 | 683.195 | 30.772 | 631.000 | 611.990 | 0.000 | 10 | 500 | 62 | 364/359/239/18/20 | 0.683 | 0.609 | 0.483 | med_pen@50=0.30 med_pen@100=0.30 med_pen@500=0.80 |
| S6 cap C=10+MMR l=0.85 | 687.047 | 30.128 | 636.000 | 615.000 | 0.000 | 10 | 486 | 62 | 377/336/249/18/20 | 0.687 | 0.589 | 0.479 | med_pen@50=0.30 med_pen@100=0.30 med_pen@500=0.80 |
| S7 cap C=10+top3 l=0.7 | 683.570 | 28.023 | 636.000 | 616.990 | 0.000 | 10 | 500 | 62 | 416/267/282/18/17 | 0.684 | 0.555 | 0.483 | med_pen@50=0.20 med_pen@100=0.30 med_pen@500=0.67 |
| S7 cap C=10+top3 l=0.85 | 687.633 | 29.292 | 638.000 | 617.000 | 0.000 | 10 | 477 | 62 | 396/300/267/18/19 | 0.688 | 0.564 | 0.475 | med_pen@50=0.20 med_pen@100=0.30 med_pen@500=0.67 |

## strategies k=100 (mix = fact/compare/change/at_event/relation)

| strategy | E | sd | p5 | p1 | P95 | maxexp | keys | subj | mix | H1 | H2 | H3 | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S0 top-k | 83.245 | 3.903 | 77.000 | 74.000 | 0.000 | 3 | 96 | 32 | 88/2/9/1/0 | 0.832 | 0.825 | 0.816 |  |
| S1 MMR l=0.5 | 79.959 | 3.930 | 74.000 | 71.000 | 0.000 | 1 | 102 | 61 | 66/0/32/1/1 | 0.800 | 0.800 | 0.808 | med_pen@50=0.30 |
| S1 MMR l=0.7 | 82.327 | 3.738 | 76.000 | 73.000 | 0.000 | 1 | 101 | 55 | 80/0/19/0/1 | 0.823 | 0.823 | 0.827 | med_pen@50=0.30 |
| S1 MMR l=0.85 | 82.789 | 3.690 | 77.000 | 74.000 | 0.000 | 1 | 100 | 51 | 84/0/16/0/0 | 0.828 | 0.828 | 0.828 | med_pen@50=0.30 |
| S1 MMR l=0.95 | 83.169 | 3.679 | 77.000 | 74.000 | 0.000 | 1 | 100 | 40 | 87/0/13/0/0 | 0.832 | 0.832 | 0.832 | med_pen@50=0.30 |
| S2 cap C=3 | 83.245 | 3.903 | 77.000 | 74.000 | 0.000 | 3 | 96 | 32 | 88/2/9/1/0 | 0.832 | 0.825 | 0.816 |  |
| S2 cap C=5 | 83.245 | 3.903 | 77.000 | 74.000 | 0.000 | 3 | 96 | 32 | 88/2/9/1/0 | 0.832 | 0.825 | 0.816 |  |
| S2 cap C=10 | 83.245 | 3.903 | 77.000 | 74.000 | 0.000 | 3 | 96 | 32 | 88/2/9/1/0 | 0.832 | 0.825 | 0.816 |  |
| S3 quota+MMR .85 | 76.041 | 7.937 | 59.000 | 54.000 | 0.000 | 20 | 100 | 49 | 20/20/20/20/20 | 0.760 | 0.747 | 0.760 | med_pen@50=0.40 |
| S4 cover mu=0.1 | 83.037 | 3.719 | 77.000 | 74.000 | 0.000 | 1 | 102 | 35 | 89/0/9/1/1 | 0.830 | 0.830 | 0.839 |  |
| S4 cover mu=0.3 | 67.159 | 4.498 | 60.000 | 57.000 | 0.000 | 1 | 178 | 55 | 18/67/4/2/9 | 0.672 | 0.672 | 0.896 |  |
| S5 DPP greedy | 82.242 | 3.802 | 76.000 | 73.000 | 0.000 | 1 | 101 | 53 | 79/0/20/0/1 | 0.822 | 0.822 | 0.827 | dpp_picked=100 |
| S6 cap C=5+MMR l=0.5 | 79.959 | 3.930 | 74.000 | 71.000 | 0.000 | 1 | 102 | 61 | 66/0/32/1/1 | 0.800 | 0.800 | 0.808 | med_pen@50=0.30 |
| S6 cap C=5+MMR l=0.7 | 82.327 | 3.738 | 76.000 | 73.000 | 0.000 | 1 | 101 | 55 | 80/0/19/0/1 | 0.823 | 0.823 | 0.827 | med_pen@50=0.30 |
| S6 cap C=5+MMR l=0.85 | 82.789 | 3.690 | 77.000 | 74.000 | 0.000 | 1 | 100 | 51 | 84/0/16/0/0 | 0.828 | 0.828 | 0.828 | med_pen@50=0.30 |
| S6 cap C=10+MMR l=0.5 | 79.959 | 3.930 | 74.000 | 71.000 | 0.000 | 1 | 102 | 61 | 66/0/32/1/1 | 0.800 | 0.800 | 0.808 | med_pen@50=0.30 |
| S6 cap C=10+MMR l=0.7 | 82.327 | 3.738 | 76.000 | 73.000 | 0.000 | 1 | 101 | 55 | 80/0/19/0/1 | 0.823 | 0.823 | 0.827 | med_pen@50=0.30 |
| S6 cap C=10+MMR l=0.85 | 82.789 | 3.690 | 77.000 | 74.000 | 0.000 | 1 | 100 | 51 | 84/0/16/0/0 | 0.828 | 0.828 | 0.828 | med_pen@50=0.30 |
| S7 cap C=10+top3 l=0.7 | 81.696 | 3.845 | 75.000 | 73.000 | 0.000 | 1 | 101 | 53 | 74/0/25/0/1 | 0.817 | 0.817 | 0.821 | med_pen@50=0.20 |
| S7 cap C=10+top3 l=0.85 | 82.976 | 3.695 | 77.000 | 74.000 | 0.000 | 1 | 100 | 44 | 87/0/13/0/0 | 0.830 | 0.830 | 0.830 | med_pen@50=0.20 |

## stress k=1000

| strategy | E_lying-page | E_shrink30 | sd_lying-page | sd_shrink30 | p5_lying-page | p5_shrink30 | p1_lying-page | p1_shrink30 |
|---|---|---|---|---|---|---|---|---|
| S0 top-k | 657.5 | 596.9 | 47.4 | 51.1 | 573.0 | 508.0 | 534.0 | 476.0 |
| S1 MMR l=0.5 | 632.8 | 585.3 | 45.1 | 48.6 | 553.0 | 502.0 | 515.0 | 471.0 |
| S1 MMR l=0.7 | 641.7 | 592.5 | 43.3 | 47.1 | 564.0 | 512.0 | 527.0 | 483.0 |
| S1 MMR l=0.85 | 651.4 | 597.1 | 45.6 | 49.4 | 571.0 | 512.0 | 533.0 | 481.0 |
| S1 MMR l=0.95 | 656.0 | 596.6 | 47.3 | 51.2 | 572.0 | 508.0 | 534.0 | 476.0 |
| S2 cap C=3 | 575.2 | 577.8 | 22.5 | 23.2 | 538.0 | 540.0 | 523.0 | 524.0 |
| S2 cap C=5 | 600.6 | 590.8 | 24.8 | 25.8 | 560.0 | 549.0 | 543.0 | 530.0 |
| S2 cap C=10 | 629.1 | 595.8 | 31.0 | 32.7 | 578.0 | 542.0 | 558.0 | 521.0 |
| S3 quota+MMR .85 | 631.8 | 590.2 | 62.1 | 64.4 | 513.0 | 473.0 | 468.0 | 431.0 |
| S4 cover mu=0.1 | 650.2 | 598.8 | 45.5 | 50.5 | 564.0 | 509.0 | 524.0 | 478.0 |
| S4 cover mu=0.3 | 635.5 | 586.5 | 42.5 | 47.9 | 553.0 | 501.0 | 519.0 | 472.0 |
| S5 DPP greedy | 645.0 | 599.9 | 37.2 | 41.2 | 577.0 | 528.0 | 547.0 | 502.0 |
| S6 cap C=5+MMR l=0.5 | 582.7 | 572.2 | 25.7 | 27.0 | 540.0 | 528.0 | 522.0 | 508.0 |
| S6 cap C=5+MMR l=0.7 | 595.6 | 586.3 | 25.1 | 26.3 | 554.0 | 544.0 | 537.0 | 524.0 |
| S6 cap C=5+MMR l=0.85 | 598.6 | 589.3 | 24.8 | 25.9 | 558.0 | 547.0 | 541.0 | 528.0 |
| S6 cap C=10+MMR l=0.5 | 609.7 | 577.2 | 32.6 | 34.4 | 556.0 | 521.0 | 536.0 | 499.0 |
| S6 cap C=10+MMR l=0.7 | 624.6 | 590.3 | 30.8 | 32.6 | 575.0 | 537.0 | 554.0 | 514.0 |
| S6 cap C=10+MMR l=0.85 | 628.0 | 595.0 | 30.2 | 32.0 | 578.0 | 543.0 | 558.0 | 521.0 |
| S7 cap C=10+top3 l=0.7 | 626.2 | 599.0 | 28.3 | 29.9 | 579.0 | 550.0 | 560.0 | 530.0 |
| S7 cap C=10+top3 l=0.85 | 628.5 | 598.7 | 29.5 | 31.1 | 580.0 | 547.0 | 560.0 | 527.0 |

## adversarial k=1000

| strategy | worst_keys | lost_claims | E_given_wrong | drop_vs_E | keys |
|---|---|---|---|---|---|
| S0 top-k | 1 | 104 | 637.6 | 73.0 | Hooly I/O 2026.date(104) |
| S0 top-k | 5 | 203 | 568.5 | 142.1 | Hooly I/O 2026.date(104), The May 2026 outage.date(40), Hooly Gemini.data_retention(23), Hooly Gemini.launched(23), Hooly Vault.planned_general_availability(22) |
| S1 MMR l=0.5 | 1 | 97 | 623.2 | 68.3 | Hooly I/O 2026.date(97) |
| S1 MMR l=0.5 | 5 | 195 | 554.7 | 136.8 | Hooly I/O 2026.date(97), The May 2026 outage.date(40), Hooly Gemini.data_retention(23), Hooly Gemini.launched(22), Bertram Gilfoil.joined(21) |
| S1 MMR l=0.7 | 1 | 97 | 629.2 | 68.3 | Hooly I/O 2026.date(97) |
| S1 MMR l=0.7 | 5 | 187 | 565.9 | 131.6 | Hooly I/O 2026.date(97), The May 2026 outage.date(32), Hooly Gemini.data_retention(23), Hooly Gemini.launched(22), Bertram Gilfoil.joined(21) |
| S1 MMR l=0.85 | 1 | 100 | 637.6 | 70.4 | Hooly I/O 2026.date(100) |
| S1 MMR l=0.85 | 5 | 196 | 570.5 | 137.6 | Hooly I/O 2026.date(100), The May 2026 outage.date(38), Hooly Gemini.data_retention(23), Hooly Gemini.launched(23), Bertram Gilfoil.joined(21) |
| S1 MMR l=0.95 | 1 | 104 | 637.5 | 73.0 | Hooly I/O 2026.date(104) |
| S1 MMR l=0.95 | 5 | 203 | 568.4 | 142.2 | Hooly I/O 2026.date(104), The May 2026 outage.date(40), Hooly Gemini.data_retention(23), Hooly Gemini.launched(23), Hooly Vault.planned_general_availability(22) |
| S2 cap C=3 | 1 | 3 | 634.4 | 2.4 | Bertram Gilfoil.joined(3) |
| S2 cap C=3 | 5 | 15 | 627.3 | 9.5 | Bertram Gilfoil.joined(3), Bertram Gilfoil.previous_employer(3), Erlich Bachmann.joined(3), Gemini Launch Night.attendees(3), Gemini Launch Night.date(3) |
| S2 cap C=5 | 1 | 5 | 660.3 | 3.8 | Bertram Gilfoil.joined(5) |
| S2 cap C=5 | 5 | 25 | 646.8 | 17.4 | Bertram Gilfoil.joined(5), Holdan.previous_employer(5), Hooly.founded(5), Hooly.series_a_amount(5), Hooly AI Free.history_retention(5) |
| S2 cap C=10 | 1 | 10 | 682.3 | 7.3 | Bertram Gilfoil.joined(10) |
| S2 cap C=10 | 5 | 47 | 656.4 | 33.3 | Bertram Gilfoil.joined(10), Hooly.founded(10), Hooly AI Free.history_retention(10), Hooly AI Pro.support_first_response(10), Hooly Calendar.launched(10) |
| S3 quota+MMR .85 | 1 | 155 | 595.8 | 103.8 | Hooly I/O 2026.date(155) |
| S3 quota+MMR .85 | 5 | 310 | 492.5 | 207.1 | Hooly I/O 2026.date(155), The May 2026 outage.date(104), Hooly Gemini.data_retention(21), Hooly Gemini.launched(20), Bertram Gilfoil.joined(17) |
| S4 cover mu=0.1 | 1 | 119 | 624.5 | 82.0 | Hooly I/O 2026.date(119) |
| S4 cover mu=0.1 | 5 | 206 | 563.2 | 143.3 | Hooly I/O 2026.date(119), The May 2026 outage.date(30), Hooly Gemini.data_retention(23), Hooly Gemini.launched(22), Bertram Gilfoil.joined(21) |
| S4 cover mu=0.3 | 1 | 115 | 611.8 | 78.8 | Hooly I/O 2026.date(115) |
| S4 cover mu=0.3 | 5 | 186 | 560.7 | 129.9 | Hooly I/O 2026.date(115), Hooly Gemini.data_retention(21), Hooly Gemini.launched(20), Bertram Gilfoil.joined(19), Hooly Vault.planned_general_availability(19) |
| S5 DPP greedy | 1 | 85 | 633.1 | 60.6 | Hooly I/O 2026.date(85) |
| S5 DPP greedy | 5 | 155 | 582.7 | 111.0 | Hooly I/O 2026.date(85), Hooly Gemini.data_retention(21), Hooly Gemini.launched(20), Hooly Vault.planned_general_availability(19), Bertram Gilfoil.joined(18) |
| S6 cap C=5+MMR l=0.5 | 1 | 5 | 646.5 | 3.8 | Bertram Gilfoil.joined(5) |
| S6 cap C=5+MMR l=0.5 | 5 | 25 | 634.1 | 16.2 | Bertram Gilfoil.joined(5), Holdan.previous_employer(5), Hooly.customers_in_the_eu(5), Hooly.founded(5), Hooly.series_a_amount(5) |
| S6 cap C=5+MMR l=0.7 | 1 | 5 | 658.2 | 3.8 | Bertram Gilfoil.joined(5) |
| S6 cap C=5+MMR l=0.7 | 5 | 25 | 645.9 | 16.2 | Bertram Gilfoil.joined(5), Holdan.previous_employer(5), Hooly.customers_in_the_eu(5), Hooly.founded(5), Hooly.series_a_amount(5) |
| S6 cap C=5+MMR l=0.85 | 1 | 5 | 659.7 | 3.8 | Bertram Gilfoil.joined(5) |
| S6 cap C=5+MMR l=0.85 | 5 | 25 | 647.2 | 16.4 | Bertram Gilfoil.joined(5), Holdan.previous_employer(5), Hooly.founded(5), Hooly.series_a_amount(5), Hooly.soc2_audit_start(5) |
| S6 cap C=10+MMR l=0.5 | 1 | 10 | 665.4 | 7.3 | Bertram Gilfoil.joined(10) |
| S6 cap C=10+MMR l=0.5 | 5 | 47 | 639.4 | 33.3 | Bertram Gilfoil.joined(10), Hooly.founded(10), Hooly AI Free.history_retention(10), Hooly AI Pro.support_first_response(10), Hooly Calendar.launched(10) |
| S6 cap C=10+MMR l=0.7 | 1 | 10 | 675.9 | 7.3 | Bertram Gilfoil.joined(10) |
| S6 cap C=10+MMR l=0.7 | 5 | 47 | 649.9 | 33.3 | Bertram Gilfoil.joined(10), Hooly.founded(10), Hooly AI Free.history_retention(10), Hooly AI Pro.support_first_response(10), Hooly Calendar.launched(10) |
| S6 cap C=10+MMR l=0.85 | 1 | 10 | 679.7 | 7.3 | Bertram Gilfoil.joined(10) |
| S6 cap C=10+MMR l=0.85 | 5 | 47 | 653.8 | 33.3 | Bertram Gilfoil.joined(10), Hooly.founded(10), Hooly AI Free.history_retention(10), Hooly AI Pro.support_first_response(10), Hooly Calendar.launched(10) |
| S7 cap C=10+top3 l=0.7 | 1 | 10 | 676.2 | 7.3 | Bertram Gilfoil.joined(10) |
| S7 cap C=10+top3 l=0.7 | 5 | 46 | 650.9 | 32.6 | Bertram Gilfoil.joined(10), Hooly.founded(10), Hooly AI Free.history_retention(10), Hooly AI Pro.support_first_response(10), Hooly Calendar.launched(10) |
| S7 cap C=10+top3 l=0.85 | 1 | 10 | 680.3 | 7.3 | Bertram Gilfoil.joined(10) |
| S7 cap C=10+top3 l=0.85 | 5 | 46 | 655.0 | 32.6 | Bertram Gilfoil.joined(10), Hooly.founded(10), Hooly AI Free.history_retention(10), Hooly AI Pro.support_first_response(10), Hooly Calendar.launched(10) |

## stress k=100

| strategy | E_lying-page | E_shrink30 | sd_lying-page | sd_shrink30 | p5_lying-page | p5_shrink30 | p1_lying-page | p1_shrink30 |
|---|---|---|---|---|---|---|---|---|
| S0 top-k | 82.0 | 72.9 | 4.0 | 4.7 | 75.0 | 65.0 | 73.0 | 62.0 |
| S1 MMR l=0.5 | 78.3 | 70.7 | 4.0 | 4.5 | 72.0 | 63.0 | 69.0 | 60.0 |
| S1 MMR l=0.7 | 81.3 | 72.5 | 3.8 | 4.5 | 75.0 | 65.0 | 72.0 | 62.0 |
| S1 MMR l=0.85 | 81.7 | 73.0 | 3.7 | 4.4 | 75.0 | 66.0 | 73.0 | 63.0 |
| S1 MMR l=0.95 | 82.2 | 73.2 | 3.7 | 4.4 | 76.0 | 66.0 | 74.0 | 63.0 |
| S2 cap C=3 | 82.0 | 72.9 | 4.0 | 4.7 | 75.0 | 65.0 | 73.0 | 62.0 |
| S2 cap C=5 | 82.0 | 72.9 | 4.0 | 4.7 | 75.0 | 65.0 | 73.0 | 62.0 |
| S2 cap C=10 | 82.0 | 72.9 | 4.0 | 4.7 | 75.0 | 65.0 | 73.0 | 62.0 |
| S3 quota+MMR .85 | 75.1 | 62.2 | 7.9 | 9.0 | 58.0 | 45.0 | 53.0 | 41.0 |
| S4 cover mu=0.1 | 81.2 | 72.9 | 3.8 | 4.5 | 75.0 | 65.0 | 72.0 | 63.0 |
| S4 cover mu=0.3 | 61.7 | 54.8 | 4.5 | 4.9 | 54.0 | 47.0 | 51.0 | 43.0 |
| S5 DPP greedy | 80.8 | 72.5 | 3.9 | 4.5 | 74.0 | 65.0 | 71.0 | 62.0 |
| S6 cap C=5+MMR l=0.5 | 78.3 | 70.7 | 4.0 | 4.5 | 72.0 | 63.0 | 69.0 | 60.0 |
| S6 cap C=5+MMR l=0.7 | 81.3 | 72.5 | 3.8 | 4.5 | 75.0 | 65.0 | 72.0 | 62.0 |
| S6 cap C=5+MMR l=0.85 | 81.7 | 73.0 | 3.7 | 4.4 | 75.0 | 66.0 | 73.0 | 63.0 |
| S6 cap C=10+MMR l=0.5 | 78.3 | 70.7 | 4.0 | 4.5 | 72.0 | 63.0 | 69.0 | 60.0 |
| S6 cap C=10+MMR l=0.7 | 81.3 | 72.5 | 3.8 | 4.5 | 75.0 | 65.0 | 72.0 | 62.0 |
| S6 cap C=10+MMR l=0.85 | 81.7 | 73.0 | 3.7 | 4.4 | 75.0 | 66.0 | 73.0 | 63.0 |
| S7 cap C=10+top3 l=0.7 | 80.2 | 72.1 | 3.9 | 4.5 | 74.0 | 64.0 | 71.0 | 61.0 |
| S7 cap C=10+top3 l=0.85 | 81.8 | 73.1 | 3.7 | 4.4 | 75.0 | 66.0 | 73.0 | 63.0 |

## adversarial k=100

| strategy | worst_keys | lost_claims | E_given_wrong | drop_vs_E | keys |
|---|---|---|---|---|---|
| S0 top-k | 1 | 3 | 80.7 | 2.5 | Hooly Gemini.data_retention(3) |
| S0 top-k | 5 | 9 | 75.7 | 7.6 | Hooly Gemini.data_retention(3), Hooly Gemini.cloud_provider(2), Hooly I/O 2026.date(2), Hooly Photos.end_to_end_encrypted_backups(2), Hooly Q1 2026 Results.call_length(2) |
| S1 MMR l=0.5 | 1 | 1 | 79.1 | 0.9 | Bertram Gilfoil.joined(1) |
| S1 MMR l=0.5 | 5 | 5 | 75.9 | 4.0 | Bertram Gilfoil.joined(1), Brightline Labs.integration_partner_of_flawless(1), Erlich Bachmann.joined(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S1 MMR l=0.7 | 1 | 1 | 81.5 | 0.9 | Bertram Gilfoil.joined(1) |
| S1 MMR l=0.7 | 5 | 5 | 78.2 | 4.2 | Bertram Gilfoil.joined(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1), Holdan.previous_employer(1) |
| S1 MMR l=0.85 | 1 | 1 | 81.9 | 0.9 | Bertram Gilfoil.joined(1) |
| S1 MMR l=0.85 | 5 | 5 | 78.6 | 4.2 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S1 MMR l=0.95 | 1 | 1 | 82.3 | 0.9 | Bertram Gilfoil.joined(1) |
| S1 MMR l=0.95 | 5 | 5 | 79.0 | 4.2 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S2 cap C=3 | 1 | 3 | 80.7 | 2.5 | Hooly Gemini.data_retention(3) |
| S2 cap C=3 | 5 | 9 | 75.7 | 7.6 | Hooly Gemini.data_retention(3), Hooly Gemini.cloud_provider(2), Hooly I/O 2026.date(2), Hooly Photos.end_to_end_encrypted_backups(2), Hooly Q1 2026 Results.call_length(2) |
| S2 cap C=5 | 1 | 3 | 80.7 | 2.5 | Hooly Gemini.data_retention(3) |
| S2 cap C=5 | 5 | 9 | 75.7 | 7.6 | Hooly Gemini.data_retention(3), Hooly Gemini.cloud_provider(2), Hooly I/O 2026.date(2), Hooly Photos.end_to_end_encrypted_backups(2), Hooly Q1 2026 Results.call_length(2) |
| S2 cap C=10 | 1 | 3 | 80.7 | 2.5 | Hooly Gemini.data_retention(3) |
| S2 cap C=10 | 5 | 9 | 75.7 | 7.6 | Hooly Gemini.data_retention(3), Hooly Gemini.cloud_provider(2), Hooly I/O 2026.date(2), Hooly Photos.end_to_end_encrypted_backups(2), Hooly Q1 2026 Results.call_length(2) |
| S3 quota+MMR .85 | 1 | 20 | 60.7 | 15.3 | Hooly I/O 2026.date(20) |
| S3 quota+MMR .85 | 5 | 41 | 45.4 | 30.7 | Hooly I/O 2026.date(20), Hooly Cloud.reliability_lead(7), Hooly Gemini.data_retention(7), Bertram Gilfoil.joined(4), Peter Gregori.chairs(4) |
| S4 cover mu=0.1 | 1 | 1 | 82.2 | 0.9 | Bertram Gilfoil.joined(1) |
| S4 cover mu=0.1 | 5 | 5 | 78.8 | 4.2 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S4 cover mu=0.3 | 1 | 1 | 66.4 | 0.7 | Bertram Gilfoil.joined(1) |
| S4 cover mu=0.3 | 5 | 5 | 63.7 | 3.4 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Dinesh Chugtay.joined(1), Erlich Bachmann.joined(1) |
| S5 DPP greedy | 1 | 1 | 81.4 | 0.9 | Bertram Gilfoil.joined(1) |
| S5 DPP greedy | 5 | 5 | 78.0 | 4.2 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S6 cap C=5+MMR l=0.5 | 1 | 1 | 79.1 | 0.9 | Bertram Gilfoil.joined(1) |
| S6 cap C=5+MMR l=0.5 | 5 | 5 | 75.9 | 4.0 | Bertram Gilfoil.joined(1), Brightline Labs.integration_partner_of_flawless(1), Erlich Bachmann.joined(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S6 cap C=5+MMR l=0.7 | 1 | 1 | 81.5 | 0.9 | Bertram Gilfoil.joined(1) |
| S6 cap C=5+MMR l=0.7 | 5 | 5 | 78.2 | 4.2 | Bertram Gilfoil.joined(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1), Holdan.previous_employer(1) |
| S6 cap C=5+MMR l=0.85 | 1 | 1 | 81.9 | 0.9 | Bertram Gilfoil.joined(1) |
| S6 cap C=5+MMR l=0.85 | 5 | 5 | 78.6 | 4.2 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S6 cap C=10+MMR l=0.5 | 1 | 1 | 79.1 | 0.9 | Bertram Gilfoil.joined(1) |
| S6 cap C=10+MMR l=0.5 | 5 | 5 | 75.9 | 4.0 | Bertram Gilfoil.joined(1), Brightline Labs.integration_partner_of_flawless(1), Erlich Bachmann.joined(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S6 cap C=10+MMR l=0.7 | 1 | 1 | 81.5 | 0.9 | Bertram Gilfoil.joined(1) |
| S6 cap C=10+MMR l=0.7 | 5 | 5 | 78.2 | 4.2 | Bertram Gilfoil.joined(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1), Holdan.previous_employer(1) |
| S6 cap C=10+MMR l=0.85 | 1 | 1 | 81.9 | 0.9 | Bertram Gilfoil.joined(1) |
| S6 cap C=10+MMR l=0.85 | 5 | 5 | 78.6 | 4.2 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S7 cap C=10+top3 l=0.7 | 1 | 1 | 80.8 | 0.9 | Bertram Gilfoil.joined(1) |
| S7 cap C=10+top3 l=0.7 | 5 | 5 | 77.5 | 4.2 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |
| S7 cap C=10+top3 l=0.85 | 1 | 1 | 82.1 | 0.9 | Bertram Gilfoil.joined(1) |
| S7 cap C=10+top3 l=0.85 | 5 | 5 | 78.8 | 4.2 | Bertram Gilfoil.joined(1), Bertram Gilfoil.previous_employer(1), Brightline Labs.integration_partner_of_flawless(1), Gemini Launch Night.attendees(1), Gemini Launch Night.city(1) |

# follow-up: S6 (cap + max-sim MMR), S7 (cap + top3-mean MMR)

## hybrid main k=1000

| strategy | E | sd | p5 | p1 | maxexp | keys | subj | mix |
|---|---|---|---|---|---|---|---|---|
| S0 top-k | 710.7 | 47.2 | 625.0 | 587.0 | 104 | 386 | 61 | 293/382/190/117/18 |
| S1 MMR l=0.5 | 691.5 | 44.9 | 610.0 | 573.0 | 97 | 501 | 62 | 300/371/201/113/15 |
| S1 MMR l=0.7 | 697.5 | 43.2 | 618.0 | 584.0 | 97 | 494 | 62 | 325/345/209/106/15 |
| S2 cap C=10 | 689.6 | 30.9 | 638.0 | 616.0 | 10 | 440 | 61 | 363/347/252/18/20 |
| S6 cap C=5+MMR l=0.5 | 650.3 | 26.2 | 608.0 | 588.0 | 5 | 501 | 62 | 382/334/250/16/18 |
| S6 cap C=5+MMR l=0.7 | 662.1 | 25.3 | 620.0 | 602.0 | 5 | 501 | 62 | 418/266/287/11/18 |
| S6 cap C=5+MMR l=0.85 | 663.6 | 24.8 | 623.0 | 605.0 | 5 | 500 | 62 | 433/245/296/8/18 |
| S6 cap C=10+MMR l=0.5 | 672.7 | 32.8 | 619.0 | 598.0 | 10 | 501 | 62 | 326/427/210/18/19 |
| S6 cap C=10+MMR l=0.7 | 683.2 | 30.8 | 631.0 | 612.0 | 10 | 500 | 62 | 364/359/239/18/20 |
| S6 cap C=10+MMR l=0.85 | 687.0 | 30.1 | 636.0 | 615.0 | 10 | 486 | 62 | 377/336/249/18/20 |
| S7 cap C=10+top3 l=0.7 | 683.6 | 28.0 | 636.0 | 617.0 | 10 | 500 | 62 | 416/267/282/18/17 |
| S7 cap C=10+top3 l=0.85 | 687.6 | 29.3 | 638.0 | 617.0 | 10 | 477 | 62 | 396/300/267/18/19 |

## hybrid stress k=1000 (E / p5 / p1)

| strategy | lying-page | shrink30 |
|---|---|---|
| S0 top-k | 657.5 / 573 / 534 | 596.9 / 508 / 476 |
| S1 MMR l=0.5 | 632.8 / 553 / 515 | 585.3 / 502 / 471 |
| S1 MMR l=0.7 | 641.7 / 564 / 527 | 592.5 / 512 / 483 |
| S2 cap C=10 | 629.1 / 578 / 558 | 595.8 / 542 / 521 |
| S6 cap C=5+MMR l=0.5 | 582.7 / 540 / 522 | 572.2 / 528 / 508 |
| S6 cap C=5+MMR l=0.7 | 595.6 / 554 / 537 | 586.3 / 544 / 524 |
| S6 cap C=5+MMR l=0.85 | 598.6 / 558 / 541 | 589.3 / 547 / 528 |
| S6 cap C=10+MMR l=0.5 | 609.7 / 556 / 536 | 577.2 / 521 / 499 |
| S6 cap C=10+MMR l=0.7 | 624.6 / 575 / 554 | 590.3 / 537 / 514 |
| S6 cap C=10+MMR l=0.85 | 628.0 / 578 / 558 | 595.0 / 543 / 521 |
| S7 cap C=10+top3 l=0.7 | 626.2 / 579 / 560 | 599.0 / 550 / 530 |
| S7 cap C=10+top3 l=0.85 | 628.5 / 580 / 560 | 598.7 / 547 / 527 |

## hybrid adversarial k=1000

| strategy | worst 1 (lost / E|wrong) | worst 5 (lost / E|wrong) |
|---|---|---|
| S0 top-k | 104 / 637.6 | 203 / 568.5 |
| S1 MMR l=0.5 | 97 / 623.2 | 195 / 554.7 |
| S1 MMR l=0.7 | 97 / 629.2 | 187 / 565.9 |
| S2 cap C=10 | 10 / 682.3 | 47 / 656.4 |
| S6 cap C=5+MMR l=0.5 | 5 / 646.5 | 25 / 634.1 |
| S6 cap C=5+MMR l=0.7 | 5 / 658.2 | 25 / 645.9 |
| S6 cap C=5+MMR l=0.85 | 5 / 659.7 | 25 / 647.2 |
| S6 cap C=10+MMR l=0.5 | 10 / 665.4 | 47 / 639.4 |
| S6 cap C=10+MMR l=0.7 | 10 / 675.9 | 47 / 649.9 |
| S6 cap C=10+MMR l=0.85 | 10 / 679.7 | 47 / 653.8 |
| S7 cap C=10+top3 l=0.7 | 10 / 676.2 | 46 / 650.9 |
| S7 cap C=10+top3 l=0.85 | 10 / 680.3 | 46 / 655.0 |

## hybrid scoring k=1000 (rel = value / best over all S0-S7 at this k; maximin = min rel)

| strategy | H1 | H2 | H3 | H1_rel | H2_rel | H3_rel | maximin |
|---|---|---|---|---|---|---|---|
| S0 top-k | 0.711 | 0.623 | 0.442 | 1.000 | 0.901 | 0.899 | 0.899 |
| S1 MMR l=0.5 | 0.691 | 0.691 | 0.489 | 0.973 | 1.000 | 0.997 | 0.973 |
| S1 MMR l=0.7 | 0.697 | 0.668 | 0.490 | 0.981 | 0.966 | 0.998 | 0.966 |
| S2 cap C=10 | 0.690 | 0.571 | 0.457 | 0.970 | 0.826 | 0.932 | 0.826 |
| S6 cap C=5+MMR l=0.5 | 0.650 | 0.561 | 0.460 | 0.915 | 0.811 | 0.937 | 0.811 |
| S6 cap C=5+MMR l=0.7 | 0.662 | 0.529 | 0.469 | 0.932 | 0.766 | 0.954 | 0.766 |
| S6 cap C=5+MMR l=0.85 | 0.664 | 0.518 | 0.469 | 0.934 | 0.749 | 0.956 | 0.749 |
| S6 cap C=10+MMR l=0.5 | 0.673 | 0.647 | 0.476 | 0.947 | 0.935 | 0.970 | 0.935 |
| S6 cap C=10+MMR l=0.7 | 0.683 | 0.609 | 0.483 | 0.961 | 0.880 | 0.984 | 0.880 |
| S6 cap C=10+MMR l=0.85 | 0.687 | 0.589 | 0.479 | 0.967 | 0.851 | 0.975 | 0.851 |
| S7 cap C=10+top3 l=0.7 | 0.684 | 0.555 | 0.483 | 0.962 | 0.802 | 0.984 | 0.802 |
| S7 cap C=10+top3 l=0.85 | 0.688 | 0.564 | 0.475 | 0.968 | 0.815 | 0.967 | 0.815 |

## maximin ranking, all strategies, k=1000

| strategy | maximin | H1_rel | H2_rel | H3_rel | p1 |
|---|---|---|---|---|---|
| S1 MMR l=0.5 | 0.973 | 0.973 | 1.000 | 0.997 | 573.000 |
| S1 MMR l=0.7 | 0.966 | 0.981 | 0.966 | 0.998 | 583.990 |
| S3 quota+MMR .85 | 0.938 | 0.984 | 0.938 | 0.968 | 526.000 |
| S6 cap C=10+MMR l=0.5 | 0.935 | 0.947 | 0.935 | 0.970 | 597.990 |
| S1 MMR l=0.85 | 0.933 | 0.996 | 0.933 | 0.950 | 589.000 |
| S1 MMR l=0.95 | 0.912 | 1.000 | 0.915 | 0.912 | 586.000 |
| S4 cover mu=0.1 | 0.907 | 0.994 | 0.907 | 0.985 | 581.000 |
| S0 top-k | 0.899 | 1.000 | 0.901 | 0.899 | 587.000 |
| S4 cover mu=0.3 | 0.893 | 0.972 | 0.893 | 0.996 | 569.000 |
| S6 cap C=10+MMR l=0.7 | 0.880 | 0.961 | 0.880 | 0.984 | 611.990 |
| S5 DPP greedy | 0.865 | 0.976 | 0.865 | 1.000 | 594.000 |
| S6 cap C=10+MMR l=0.85 | 0.851 | 0.967 | 0.851 | 0.975 | 615.000 |
| S2 cap C=10 | 0.826 | 0.970 | 0.826 | 0.932 | 616.000 |
| S7 cap C=10+top3 l=0.85 | 0.815 | 0.968 | 0.815 | 0.967 | 617.000 |
| S6 cap C=5+MMR l=0.5 | 0.811 | 0.915 | 0.811 | 0.937 | 587.990 |
| S7 cap C=10+top3 l=0.7 | 0.802 | 0.962 | 0.802 | 0.984 | 616.990 |
| S6 cap C=5+MMR l=0.7 | 0.766 | 0.932 | 0.766 | 0.954 | 602.000 |
| S6 cap C=5+MMR l=0.85 | 0.749 | 0.934 | 0.749 | 0.956 | 604.990 |
| S2 cap C=5 | 0.733 | 0.935 | 0.733 | 0.947 | 606.000 |
| S2 cap C=3 | 0.669 | 0.896 | 0.669 | 0.918 | 584.000 |

## hybrid main k=100

| strategy | E | sd | p5 | p1 | maxexp | keys | subj | mix |
|---|---|---|---|---|---|---|---|---|
| S0 top-k | 83.2 | 3.9 | 77.0 | 74.0 | 3 | 96 | 32 | 88/2/9/1/0 |
| S1 MMR l=0.5 | 80.0 | 3.9 | 74.0 | 71.0 | 1 | 102 | 61 | 66/0/32/1/1 |
| S1 MMR l=0.7 | 82.3 | 3.7 | 76.0 | 73.0 | 1 | 101 | 55 | 80/0/19/0/1 |
| S2 cap C=10 | 83.2 | 3.9 | 77.0 | 74.0 | 3 | 96 | 32 | 88/2/9/1/0 |
| S6 cap C=5+MMR l=0.5 | 80.0 | 3.9 | 74.0 | 71.0 | 1 | 102 | 61 | 66/0/32/1/1 |
| S6 cap C=5+MMR l=0.7 | 82.3 | 3.7 | 76.0 | 73.0 | 1 | 101 | 55 | 80/0/19/0/1 |
| S6 cap C=5+MMR l=0.85 | 82.8 | 3.7 | 77.0 | 74.0 | 1 | 100 | 51 | 84/0/16/0/0 |
| S6 cap C=10+MMR l=0.5 | 80.0 | 3.9 | 74.0 | 71.0 | 1 | 102 | 61 | 66/0/32/1/1 |
| S6 cap C=10+MMR l=0.7 | 82.3 | 3.7 | 76.0 | 73.0 | 1 | 101 | 55 | 80/0/19/0/1 |
| S6 cap C=10+MMR l=0.85 | 82.8 | 3.7 | 77.0 | 74.0 | 1 | 100 | 51 | 84/0/16/0/0 |
| S7 cap C=10+top3 l=0.7 | 81.7 | 3.8 | 75.0 | 73.0 | 1 | 101 | 53 | 74/0/25/0/1 |
| S7 cap C=10+top3 l=0.85 | 83.0 | 3.7 | 77.0 | 74.0 | 1 | 100 | 44 | 87/0/13/0/0 |

## hybrid stress k=100 (E / p5 / p1)

| strategy | lying-page | shrink30 |
|---|---|---|
| S0 top-k | 82.0 / 75 / 73 | 72.9 / 65 / 62 |
| S1 MMR l=0.5 | 78.3 / 72 / 69 | 70.7 / 63 / 60 |
| S1 MMR l=0.7 | 81.3 / 75 / 72 | 72.5 / 65 / 62 |
| S2 cap C=10 | 82.0 / 75 / 73 | 72.9 / 65 / 62 |
| S6 cap C=5+MMR l=0.5 | 78.3 / 72 / 69 | 70.7 / 63 / 60 |
| S6 cap C=5+MMR l=0.7 | 81.3 / 75 / 72 | 72.5 / 65 / 62 |
| S6 cap C=5+MMR l=0.85 | 81.7 / 75 / 73 | 73.0 / 66 / 63 |
| S6 cap C=10+MMR l=0.5 | 78.3 / 72 / 69 | 70.7 / 63 / 60 |
| S6 cap C=10+MMR l=0.7 | 81.3 / 75 / 72 | 72.5 / 65 / 62 |
| S6 cap C=10+MMR l=0.85 | 81.7 / 75 / 73 | 73.0 / 66 / 63 |
| S7 cap C=10+top3 l=0.7 | 80.2 / 74 / 71 | 72.1 / 64 / 61 |
| S7 cap C=10+top3 l=0.85 | 81.8 / 75 / 73 | 73.1 / 66 / 63 |

## hybrid adversarial k=100

| strategy | worst 1 (lost / E|wrong) | worst 5 (lost / E|wrong) |
|---|---|---|
| S0 top-k | 3 / 80.7 | 9 / 75.7 |
| S1 MMR l=0.5 | 1 / 79.1 | 5 / 75.9 |
| S1 MMR l=0.7 | 1 / 81.5 | 5 / 78.2 |
| S2 cap C=10 | 3 / 80.7 | 9 / 75.7 |
| S6 cap C=5+MMR l=0.5 | 1 / 79.1 | 5 / 75.9 |
| S6 cap C=5+MMR l=0.7 | 1 / 81.5 | 5 / 78.2 |
| S6 cap C=5+MMR l=0.85 | 1 / 81.9 | 5 / 78.6 |
| S6 cap C=10+MMR l=0.5 | 1 / 79.1 | 5 / 75.9 |
| S6 cap C=10+MMR l=0.7 | 1 / 81.5 | 5 / 78.2 |
| S6 cap C=10+MMR l=0.85 | 1 / 81.9 | 5 / 78.6 |
| S7 cap C=10+top3 l=0.7 | 1 / 80.8 | 5 / 77.5 |
| S7 cap C=10+top3 l=0.85 | 1 / 82.1 | 5 / 78.8 |

## hybrid scoring k=100 (rel = value / best over all S0-S7 at this k; maximin = min rel)

| strategy | H1 | H2 | H3 | H1_rel | H2_rel | H3_rel | maximin |
|---|---|---|---|---|---|---|---|
| S0 top-k | 0.832 | 0.825 | 0.816 | 1.000 | 0.991 | 0.910 | 0.910 |
| S1 MMR l=0.5 | 0.800 | 0.800 | 0.808 | 0.961 | 0.961 | 0.901 | 0.901 |
| S1 MMR l=0.7 | 0.823 | 0.823 | 0.827 | 0.989 | 0.990 | 0.923 | 0.923 |
| S2 cap C=10 | 0.832 | 0.825 | 0.816 | 1.000 | 0.991 | 0.910 | 0.910 |
| S6 cap C=5+MMR l=0.5 | 0.800 | 0.800 | 0.808 | 0.961 | 0.961 | 0.901 | 0.901 |
| S6 cap C=5+MMR l=0.7 | 0.823 | 0.823 | 0.827 | 0.989 | 0.990 | 0.923 | 0.923 |
| S6 cap C=5+MMR l=0.85 | 0.828 | 0.828 | 0.828 | 0.995 | 0.995 | 0.924 | 0.924 |
| S6 cap C=10+MMR l=0.5 | 0.800 | 0.800 | 0.808 | 0.961 | 0.961 | 0.901 | 0.901 |
| S6 cap C=10+MMR l=0.7 | 0.823 | 0.823 | 0.827 | 0.989 | 0.990 | 0.923 | 0.923 |
| S6 cap C=10+MMR l=0.85 | 0.828 | 0.828 | 0.828 | 0.995 | 0.995 | 0.924 | 0.924 |
| S7 cap C=10+top3 l=0.7 | 0.817 | 0.817 | 0.821 | 0.981 | 0.982 | 0.916 | 0.916 |
| S7 cap C=10+top3 l=0.85 | 0.830 | 0.830 | 0.830 | 0.997 | 0.998 | 0.926 | 0.926 |

## maximin ranking, all strategies, k=100

| strategy | maximin | H1_rel | H2_rel | H3_rel | p1 |
|---|---|---|---|---|---|
| S4 cover mu=0.1 | 0.936 | 0.998 | 0.998 | 0.936 | 74.000 |
| S1 MMR l=0.95 | 0.928 | 0.999 | 1.000 | 0.928 | 74.000 |
| S7 cap C=10+top3 l=0.85 | 0.926 | 0.997 | 0.998 | 0.926 | 74.000 |
| S1 MMR l=0.85 | 0.924 | 0.995 | 0.995 | 0.924 | 74.000 |
| S6 cap C=10+MMR l=0.85 | 0.924 | 0.995 | 0.995 | 0.924 | 74.000 |
| S6 cap C=5+MMR l=0.85 | 0.924 | 0.995 | 0.995 | 0.924 | 74.000 |
| S1 MMR l=0.7 | 0.923 | 0.989 | 0.990 | 0.923 | 73.000 |
| S6 cap C=10+MMR l=0.7 | 0.923 | 0.989 | 0.990 | 0.923 | 73.000 |
| S6 cap C=5+MMR l=0.7 | 0.923 | 0.989 | 0.990 | 0.923 | 73.000 |
| S5 DPP greedy | 0.922 | 0.988 | 0.989 | 0.922 | 73.000 |
| S7 cap C=10+top3 l=0.7 | 0.916 | 0.981 | 0.982 | 0.916 | 73.000 |
| S0 top-k | 0.910 | 1.000 | 0.991 | 0.910 | 74.000 |
| S2 cap C=10 | 0.910 | 1.000 | 0.991 | 0.910 | 74.000 |
| S2 cap C=5 | 0.910 | 1.000 | 0.991 | 0.910 | 74.000 |
| S2 cap C=3 | 0.910 | 1.000 | 0.991 | 0.910 | 74.000 |
| S6 cap C=5+MMR l=0.5 | 0.901 | 0.961 | 0.961 | 0.901 | 71.000 |
| S1 MMR l=0.5 | 0.901 | 0.961 | 0.961 | 0.901 | 71.000 |
| S6 cap C=10+MMR l=0.5 | 0.901 | 0.961 | 0.961 | 0.901 | 71.000 |
| S3 quota+MMR .85 | 0.849 | 0.913 | 0.898 | 0.849 | 54.000 |
| S4 cover mu=0.3 | 0.807 | 0.807 | 0.808 | 1.000 | 57.000 |
