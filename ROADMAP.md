# Roadmap

Limen estimates **landslide, flood and wildfire** danger on a 1 km² grid over
all twenty Italian regions, every hour, with a 72-hour per-cell forecast. The
deterministic engine is the production champion; ML models run in shadow and
an AI only rewrites numbers into words.

This file is a summary. **The source is the list of open issues**, and this
file is updated at every release. No dates are given where none has been
decided.

## The goal everything is measured against

**Epic [#345](https://github.com/agent-engineering-studio/limen/issues/345):
forecast within 72 hours 90 % of the landslides, floods and wildfires
reported by the news, with at most 10 % of municipality-days on alert.** If
Limen does not reach it, the platform is not useful; experience, ML and AI
serve to move towards it. The catch rate is always reported next to the alert
load, because lighting everything up inflates the first number for free.

## Where each hazard stands

| Hazard | State | Latest measurement |
|---|---|---|
| Landslide | in production, 20 regions | Liguria, Nov 2019: the «high» class catches 11 % of 131 landslides with 0.17 % of cell-hours on alert. Ranking within a region works; the rainfall signal is the limit. |
| Flood | in production, 20 regions | Pluvial and fluvial triggers per node; the hydraulic class makes cells too alarming in hilly regions (Calabria at 98 %, [#469](https://github.com/agent-engineering-studio/limen/issues/469)). |
| Wildfire | in production, 20 regions | Basilicata: 79 % of fire days in the high class against a 43 % base rate (2025), 100 % against 28 % (2024). |
| Against the news (#345) | 29/10/2026 | 8 verified events, 0 anticipated above their background: too few to be a statistic. The denominator comes first. |
| ML challengers | shadow | Landslide AUC-PR 0.60 vs 0.28, wildfire 0.35 vs 0.24 in development; the promotion gate now takes hit rate, false alarms and lead time from the backtest ([#483](https://github.com/agent-engineering-studio/limen/issues/483)). No model is trained on the current installation yet ([#486](https://github.com/agent-engineering-studio/limen/issues/486)). |

The numbers come from `limen backtest`, `backtest-flood`, `backtest-wildfire`
and `verifiche-report`; the [book](https://limen-docs.agentengineering.it/)
explains each one.

## Now

- **A wider, more reliable truth set** for #345: dated landslides after 2021
  ([#500](https://github.com/agent-engineering-studio/limen/issues/500)),
  events supplied by public bodies in an open format
  ([#509](https://github.com/agent-engineering-studio/limen/issues/509)).
- **The right rainfall as input**: regional rain gauges
  ([#505](https://github.com/agent-engineering-studio/limen/issues/505)) and
  regional landslide rainfall thresholds
  ([#506](https://github.com/agent-engineering-studio/limen/issues/506)).
- **Fewer flood false alarms**: hydraulic class per cell
  ([#469](https://github.com/agent-engineering-studio/limen/issues/469)),
  channelisation signal
  ([#474](https://github.com/agent-engineering-studio/limen/issues/474)),
  GloFAS return periods
  ([#522](https://github.com/agent-engineering-studio/limen/issues/522)).
- **ML back on the current installation**: training set, registry and FIRMS
  history ([#486](https://github.com/agent-engineering-studio/limen/issues/486), in progress).
- **Install anywhere, from the browser**: epics
  [#409](https://github.com/agent-engineering-studio/limen/issues/409) and
  [#308](https://github.com/agent-engineering-studio/limen/issues/308);
  off-site backups ([#490](https://github.com/agent-engineering-studio/limen/issues/490)).

## Next

- **ML that can be judged**: features added after July 2026
  ([#482](https://github.com/agent-engineering-studio/limen/issues/482)),
  wildfire retraining on the new fuel weights
  ([#485](https://github.com/agent-engineering-studio/limen/issues/485)),
  versioned backtest reports
  ([#481](https://github.com/agent-engineering-studio/limen/issues/481)),
  offline measurements as read-only commands
  ([#480](https://github.com/agent-engineering-studio/limen/issues/480)).
- **Wider backtests**: wildfire on all regions and the whole year
  ([#479](https://github.com/agent-engineering-studio/limen/issues/479),
  [#476](https://github.com/agent-engineering-studio/limen/issues/476)),
  stored GloFAS history for the fluvial branch
  ([#478](https://github.com/agent-engineering-studio/limen/issues/478)),
  urban flash floods ([#475](https://github.com/agent-engineering-studio/limen/issues/475)).
- **Visible uncertainty** per cell
  ([#484](https://github.com/agent-engineering-studio/limen/issues/484)).
- **Open standards**: alerts in CAP 1.2
  ([#499](https://github.com/agent-engineering-studio/limen/issues/499)),
  OGC API Features ([#503](https://github.com/agent-engineering-studio/limen/issues/503)),
  DCAT-AP_IT on dati.gov.it ([#504](https://github.com/agent-engineering-studio/limen/issues/504)).
- **A community that does not depend on one person**:
  [#514](https://github.com/agent-engineering-studio/limen/issues/514),
  a guide for non-developers
  ([#511](https://github.com/agent-engineering-studio/limen/issues/511)),
  a readable funding plan
  ([#512](https://github.com/agent-engineering-studio/limen/issues/512)),
  measured running costs
  ([#492](https://github.com/agent-engineering-studio/limen/issues/492)).

## Later

- **Citizen sensors** as in-situ sources with trust levels: epic
  [#247](https://github.com/agent-engineering-studio/limen/issues/247).
- **3D view**, decided after a go/no-go spike: epic
  [#325](https://github.com/agent-engineering-studio/limen/issues/325).
- **Finer static data**: CARG geological maps
  ([#497](https://github.com/agent-engineering-studio/limen/issues/497)),
  5 m DTM ([#468](https://github.com/agent-engineering-studio/limen/issues/468)),
  municipal burnt-area registers
  ([#498](https://github.com/agent-engineering-studio/limen/issues/498)),
  regional river gauges
  ([#501](https://github.com/agent-engineering-studio/limen/issues/501)),
  Sentinel-1 soil moisture
  ([#507](https://github.com/agent-engineering-studio/limen/issues/507)),
  ground motion features ([#380](https://github.com/agent-engineering-studio/limen/issues/380)).

## Start here

Small, well-scoped tasks are labelled
[`good first issue`](https://github.com/agent-engineering-studio/limen/labels/good%20first%20issue);
a dataset Limen should use goes in a
[data proposal](https://github.com/agent-engineering-studio/limen/issues/new?template=proposta-dato.yml);
questions go in the
[discussions](https://github.com/agent-engineering-studio/limen/discussions).
See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

---

*The source is the list of open issues; this file is updated at every release.*
