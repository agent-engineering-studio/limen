# Take part

**The most useful contributions to Limen are not code: they are real events,
measurements and opinions.** Limen measures itself against the landslides,
floods and wildfires that actually happened, and on 29 October 2026 there were
eight verified events: too few to say whether the map works. Every dated event
with a place and a source becomes a row of the register Limen is tested
against. This page says, for each kind of reader, what they can do, with an
example, and what happens next.

> **Limen is not an emergency service.** If you are in danger call **112**
> and follow the instructions of Civil Protection and your municipality. A
> report to Limen serves to measure the map, not to bring help.

## If you see an event: report it

Did you see a landslide, a flooded road, a fire, or read about one in a local
paper? Report it with the
[«Report an event»](https://github.com/agent-engineering-studio/limen/issues/new?template=evento.yml)
form. Four things are needed:

- **the hazard**: landslide, flood or wildfire;
- **when**: the day, and the time if you know it;
- **where**: the municipality, and if you can the point on the map;
- **the source**: an article, an official statement, a photo with its licence.

**An example.** «Landslide on the provincial road to Bagaladi (RC), 10 October
2026 around 3 pm, reported by Gazzetta del Sud at this link.» That is enough.

**What happens next.** The maintainer checks the event on at least two
independent sources, looks at what Limen said in the 72 hours before and
registers it. The event appears on the [Verifications](#/verifiche) page with
its outcome, even when Limen had not seen it: a missed event is the most
useful information.

## If you do research: redo the numbers and challenge them

Every number on the map can be recomputed. Click a cell: the panel shows its
identifier. With it, one address returns all the ingredients of the latest
computation:

```
GET /api/cell/{identifier}/breakdown?hazard=landslide
```

(`hazard` is `landslide`, `flood` or `wildfire`; in the address the `|`
character of the identifier is written `%7C`.) Weights and thresholds live in
each hazard's configuration file, public in the repository. If the sum does
not add up, or you think a weight is wrong, open
[«Challenge a score»](https://github.com/agent-engineering-studio/limen/issues/new?template=contesta-punteggio.yml)
with the cell, the time, the value you expected and the computation you did.

**An example.** «Cell `it-toscana|156|158`, landslide, 9 November 2026 at
10:00: the score is 0.41, but with the weights in `landslide.yaml` and the
components in the response I get 0.38.»

**What happens next.** The answer goes in the issue. If it is a computation
error it is fixed with a test. If it is a proposed weight or threshold, it is
tried on past events with and without the change, and adopted only if it
catches more events without more false alarms. Either way, the measurement
stays written in the issue.

**For a research collaboration** (a thesis, a comparison with your model, a
dataset of events) write in the
[project discussions](https://github.com/agent-engineering-studio/limen/discussions)
or to gzileni@agentengineering.it.

## Local authorities and Civil Protection: events, pilots, opinions

- **The events of your season.** A list of dated landslides, flooded areas or
  interventions, even in a spreadsheet, is worth more than any code change:
  many small events are in no national catalogue. Send it by email; every row
  with date, place and source becomes an event in the register.
- **A trial on your territory.** The public map already covers every region; a
  copy on your own servers installs with one command, then everything from the
  browser.
- **An opinion.** «I would use this information, not that one» is what helps
  most in deciding what to do next.

**An example.** A municipal technical office sends the 23 landslides of 2025
on municipal roads, with day and place: they enter the register and Limen
says, for each one, whether it had seen it and how many hours before.

Limen **is not an official warning system** and does not replace the regional
Functional Centres or IT-Alert: it is a decision-support tool. Write to
**gzileni@agentengineering.it**.

## If you know a useful dataset: propose it

A regional rain-gauge network, a landslide inventory, a more detailed map:
propose it with the
[«Data proposal»](https://github.com/agent-engineering-studio/limen/issues/new?template=proposta-dato.yml)
form. Licence, link, coverage and how to measure it are required; the
[Sources](#/fonti) page explains how Limen decides whether to use it.

## If you have a sensor

A home-built rain gauge or weather station can become a Limen source, with
clear rules on where to install it and who sees the data: they are on the
[Sensors](#/sensori) page.

## If you write code

The starting point is
[`CONTRIBUTING.md`](https://github.com/agent-engineering-studio/limen/blob/main/CONTRIBUTING.md);
small first tasks are labelled
[`good first issue`](https://github.com/agent-engineering-studio/limen/labels/good%20first%20issue).

## How long to wait for an answer

Limen has **a single maintainer**: we usually reply within a week, not always
the same day. The personal data you send us is handled as explained on the
[Personal data](#/privacy) page.

## For the maintainers

An accepted report becomes a fact-check file and then a row of the register
with `limen registra-verifica FILE`. The fields of the «Report an event» form
map to those of the file:

| Form | Fact-check file |
|---|---|
| hazard | `pericolo` (`landslide`, `flood`, `wildfire`) |
| date and time, time precision | `evento.quando` (with the time zone), `evento.precisione_ora` (`T1` hour known, `T2` half a day, `T3` day only) |
| municipality, place | `evento.comuni`, `evento.luogo`, `evento.regione` |
| coordinates, place precision | `evento.lon`, `evento.lat`, `evento.precisione_luogo` (`P0`, `P1`, `P10`, `P100`) |
| sources | `fonti` (at least one, with `url`) |

`esito` and `misura` are not written by the reporter: the fact-check computes
them by comparing the event with what Limen said in the 72 hours before.
