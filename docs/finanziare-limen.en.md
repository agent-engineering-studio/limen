*Versione italiana: [finanziare-limen.md](./finanziare-limen.md)*

# Funding Limen

This document is for a foundation, a public administration or a funding
programme that wants to know in five minutes what it would buy, for how
much, in how long, and how it will see whether it worked. Every figure is
dated and points to the repository file it comes from. Written on 13
November 2026 (issue [#512](https://github.com/agent-engineering-studio/limen/issues/512)).

## 1. The goal, and where we stand

Every hour, Limen computes the risk of landslide, flood and wildfire for
the whole of Italy, with free software (EUPL 1.2 licence) that anyone can
install on their own server.

**The measurable goal** (issue
[#345](https://github.com/agent-engineering-studio/limen/issues/345)):
forecast within 72 hours **90 %** of the events reported in the press,
with no more than **10 %** of municipality-days on alert.

**Where we are today**, hazard by hazard:

| Hazard | Measurement | Date | Source |
|---|---|---|---|
| Landslide | 49 % of affected municipalities caught with a 10 % alert load (153 of 313), over the twelve test windows. **Goal not met.** | October 2026 | `docs/book/05-misurare.md` (§ 8), issues #345 and #357 |
| Flood | 77 % of flooded cells on «high» alert beforehand (Emilia-Romagna), 80 % (Lombardy), about 50 hours of lead time; but false alarms at 78 % and 43 %, against a 30 % target | 8 Nov 2026 | `docs/book/05-misurare.md` (§ 7) |
| Wildfire | Italy, «high» threshold, 72 hours: 62 % of burnt cells caught against an 11 % base rate in 2024 (5.5 times chance), 68 % against 12 % in 2025 (5.5), 62 % against 14 % in 2026 up to 10 November (4.5) | 12 Nov 2026 | `docs/misure/backtest_wildfire_italia_*_High.md` |
| Events from the press | 8 verified events (4 landslides, 4 floods), none forecast above the municipality's usual level. Too few to say anything | 29 Oct 2026 | `docs/book/05-misurare.md` |

The weak point is the landslide, and the reason is measured: the rain that
reaches the engine, taken from weather models, is about **62 %** of what
rain gauges measure, and 41 % in the Marche (`docs/book/04-i-motori.md`,
issue #122, 12 October 2026). The attempts to correct it are written up in
public, with their numbers, in chapter 5 of the book.

## 2. What already works

- **Three hazards live** across Italy: 20 regions, 312,550 cells of 1 km,
  recomputed every hour (`docs/analisi-offerta-pa.md`).
- **Wildfire discriminates well**: 4.5-5.5 times chance, with two to three
  days of lead time, against the official European EFFIS perimeters.
- **Reproducible measurements**: every test is a command, and its report
  carries commit, engine versions and environment (`docs/misure/`).
- **No cloud required**: it runs in Docker containers on a single machine.
  AI only writes the text, never the scores, and spending on Claude is
  capped at **10 dollars a month**, checked before every request
  (`docs/book/08-trasparenza.md`).
- **Today's running cost is not measured** (issue #492): the instance
  described in the book runs on a desktop computer, not a server
  (`docs/book/07-come-gira.md`). On a commercial cloud it would cost between
  4,000 and 12,000 dollars a year depending on the robustness wanted
  (estimate of 11 October 2026, `docs/analisi-costi-cloud.md`).

What does **not** work yet: the landslide does not pass the test; flood
raises too many false alarms; the project depends on **a single person**
(one external change out of 311 accepted, November 2026, issue #514); the
backup sits on the same machine and a restore has never been tried on a
clean one (issues #490 and #307).

## 3. What the money buys

Five packages, independent of each other: funding just one is fine. Costs
are **estimates**: work is valued at about 300 euro a day and staff at
60-70 thousand euro a year of employer cost for a senior full-time person,
as in the public-sector offer analysis (`docs/analisi-offerta-pa.md`, 11
October 2026); the other bases are given row by row.

| # | What is bought | Estimated cost | Duration | How we will know it worked |
|---|---|---|---|---|
| 1 | **A second person** who develops and runs Limen, half time. Basis: half the cost of a senior full-time person | €30-35k | 12 months | External changes accepted (today 1 of 311); response time to reports; an upgrade and a restore done by the second person alone |
| 2 | **Collecting real events**: dated landslides, floods and fires, region by region, from the press and from public bodies' lists (format already in place, `limen importa-eventi`, issue #509). Basis: 0.3 full-time «support and data» | €18-22k | 12 months | Events in the verification register, by hazard and region (today 8); at least one public body's list imported with its licence |
| 3 | **A research partner for landslides** (a university or a CNR institute): measured rain into the engine and thresholds reviewed with geological expertise. Basis: order of magnitude of a one-year Italian research grant plus a contribution for data; an estimate not taken from project documents | €25-35k | 12 months | Affected municipalities caught with a 10 % load over the twelve windows, before (49 %) and after; ratio of engine rain to gauges (today about 62 %) |
| 4 | **A standby server and an off-site archive**, with a restore test on a clean machine (issues #490, #307, #308). Basis: €150-250/month for a virtual machine on an Italian cloud plus 10-15 working days | €5-8k | 3 months of work, 12 months of service | Full restore from scratch on a clean server, with the time measured and published |
| 5 | **A pilot with a Region** for one season: installation, regional calibration, training of a civil protection office. Basis: 40-70 working days, the cost of a regional installation in the offer analysis | €15-25k | 6-9 months | A usage report for one season: who opened it, for which decisions, which events it saw or missed |
| | **Total** | **€93-125k** | | |

Limen remains **decision support**: it does not replace the alerts of the
regional Functional Centres or IT-Alert. No package changes that.

## 4. Funding channels

Checked on **13 November 2026**. Requirements and deadlines change: check
them again before every application.

| Channel | What it funds | Amount | Deadline | Notes |
|---|---|---|---|---|
| **NLnet**, open calls (open call and theme funds) — <https://nlnet.nl/propose/> | Technical development of free software and digital commons | €5,000-50,000 for a first grant | **3 January 2027, 12:00 CET**; then every two months, on the 3rd of odd months | Individuals may apply too. On 13/11 the form was not accepting proposals and the generative-AI policy was being revised (<https://nlnet.nl/news/2026/20260903-call.html>). The NGI Zero Commons Fund closed its last call on 1 June 2026. Whether a territorial-risk project fits the themes still has to be checked |
| **Horizon Europe, Cluster 3**, topic HORIZON-CL3-2027-01-DRS-03 «decision support systems for disaster crises» — <https://www.horizon-europe.gouv.fr/enhancing-decision-support-system-disaster-crises-leveraging-emerging-technologies-improved-civil> | Innovation actions: decision support systems from early warning to early action, with explainable AI | €9M for the topic; per-project contribution not stated | Opens **5 May 2027**, closes **4 November 2027** | Needs a European consortium; Limen would join as an open component alongside a research partner. Dates read on a French national portal, to be confirmed on the Commission's Funding & Tenders portal |

Checked and **closed** on that date: the LIFE programme, climate change
adaptation 2026 (closed 22 September 2026; the 2027 call is not yet
verified); Fondazione CRT «Piccoli Comuni» 2026 (30 September 2026);
Compagnia di San Paolo «Simbiosi» 2026 (27 February 2026). The search found
no open call from Italian banking foundations on hydrogeological risk;
they usually open at the start of the year.

Other channels named in the project documents and **not verified** here:
cloud credits for open-source or research projects (they pay for servers,
not people) and, on the side of public bodies, the regional ERDF
2021-2027 programmes, regional civil protection funds and Interreg
(`docs/analisi-costi-cloud.md`, `docs/analisi-offerta-pa.md`). Italy's
recovery plan (PNRR) ends in 2026.

## 5. Who receives the funds

[to be completed by the maintainer: legal entity receiving the funds]

Whoever the recipient is, funded code stays under EUPL 1.2: no funding can
lock it into a private product (`docs/book/08-trasparenza.md`). Every result
is published with its measurement and its base rate, before and after, in
`docs/misure/`.
