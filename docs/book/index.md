# Limen, spiegato per gradi

**Limen** (in latino «soglia») è un sistema aperto che, ogni ora, stima
quanto ogni chilometro quadrato d'Italia è esposto a **frane, alluvioni e
incendi boschivi**. Divide il Paese in 312.550 celle, unisce dati pubblici sul
territorio (pendenze, frane già censite, aree allagabili, boschi) con il meteo
osservato e previsto, e disegna una mappa a cinque classi con una previsione a
72 ore. Ogni numero ha una formula scritta e una fonte. Il codice è libero
(EUPL-1.2) e gira su un solo server, senza servizi cloud.

Questo libro racconta come funziona, partendo dai mattoni più piccoli (le
librerie che parlano con le fonti dei dati) fino al cuore del sistema (i
motori di calcolo, la misura, l'apprendimento automatico).

!!! warning "Prima di tutto"
    Limen **non è un sistema di allertamento ufficiale**. Le allerte che
    contano le emettono il Dipartimento della Protezione Civile e i Centri
    Funzionali regionali. Limen è uno strumento di supporto, aperto e
    ispezionabile: i suoi avvisi non hanno valore legale.

## A chi è rivolto e come leggerlo

Il libro è scritto in italiano semplice: ogni termine tecnico viene spiegato
la prima volta che compare e raccolto nel glossario. Ogni capitolo si apre con
un riquadro **«In breve»** e si chiude con **«Per approfondire»**, dove stanno i
link e la bibliografia tecnica. I riquadri **«Per chi sviluppa»** indicano i
file del codice da cui viene ciò che si racconta: chi non scrive codice può
saltarli senza perdere il filo.

Tre percorsi di lettura, a seconda di chi sei:

| Se sei… | Leggi | Perché |
|---|---|---|
| **Chi decide o finanzia** (un ente, una fondazione, un'amministrazione) | 1 → 5 → 8 → 9 | cosa fa Limen, come si misura se funziona, quanto costa, come partecipare |
| **Chi lavora sul territorio** (un Comune, la Protezione civile locale, un tecnico, un ricercatore) | 1 → 3 → 4 → 5 | da dove vengono i dati, come diventano un punteggio, dove sbaglia |
| **Chi sviluppa** (programmatori, data scientist, chi vuole contribuire) | tutto, in ordine | dalle librerie al cuore: è l'ordine in cui il sistema è costruito |

## Indice

| # | Capitolo | Di che cosa parla | Stato |
|---|---|---|---|
| 1 | [Il problema e cosa fa Limen](01-il-problema.md) | il rischio in Italia, cosa fa Limen e cosa non fa, i principi, a che punto siamo | scritto |
| 2 | [I mattoni: le librerie e perché ci sono](02-le-librerie.md) | le undici librerie estratte da Limen e le dipendenze di terze parti, per ruolo | scritto |
| 3 | I dati: cosa misurano, da dove vengono, con quale licenza | territorio, meteo, satelliti, eventi veri; licenze e attribuzioni | da scrivere |
| 4 | Dal dato al punteggio: frana, alluvione, incendio | le tre formule, le cinque classi, perché il meteo «comanda» e il territorio «modula» | da scrivere |
| 5 | Misurare prima di cambiare | backtest, tasso di base, carico; tre esempi veri: i pesi del combustibile (#295), gli strati HRL (#419), l'acqua temporanea (#420) | da scrivere |
| 6 | Machine learning e intelligenza artificiale | il modello in ombra, la validazione spaziale, il drift; l'LLM che riformula e non calcola | da scrivere |
| 7 | Come gira | worker, tre cadenze, database, mappa, avvisi | da scrivere |
| 8 | Trasparenza, licenze, riproducibilità, costi | come rifare tutto da zero, come verificare un punteggio, quanto costa tenerlo acceso | da scrivere |
| 9 | Partecipare | collaboratori, enti, finanziatori; la roadmap | da scrivere |
| A | Glossario | ogni parola non ovvia | da scrivere (si parte dal [glossario esistente](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/glossario.md)) |
| B | Bibliografia | articoli, rapporti, dataset, con DOI | da scrivere (raccoglie i «Per approfondire» dei capitoli) |
| C | Indice delle librerie | una scheda per libreria e dipendenza | da scrivere (parte dal capitolo 2) |

### Da dove arriva il materiale

Il repository ha già molta documentazione: il libro non la ricopia, la
riordina in un percorso unico e rimanda all'originale per i dettagli.

| Documento esistente | Confluisce in |
|---|---|
| [Limen in una pagina](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/01-limen-in-una-pagina.md) | capitolo 1 |
| [Come si calcola il rischio della tua cella](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/02-come-si-calcola-il-rischio.md), [`scoring-model.md`](https://github.com/agent-engineering-studio/limen/blob/main/docs/scoring-model.md) | capitolo 4 |
| [Cosa fanno ML e AI, e cosa no](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/03-cosa-fanno-ml-e-ai.md), [`ml.md`](https://github.com/agent-engineering-studio/limen/blob/main/docs/ml.md) | capitoli 5 e 6 |
| [Le fonti dati](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/04-fonti-dati-open.md), il catalogo [`dati.yaml`](https://github.com/agent-engineering-studio/limen/blob/main/src/limen/config/dati.yaml) | capitolo 3 |
| [L'AI gira in casa](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/05-ai-che-gira-in-casa.md), [`inference.md`](https://github.com/agent-engineering-studio/limen/blob/main/docs/inference.md) | capitolo 6 |
| [Trasparenza e riproducibilità](https://github.com/agent-engineering-studio/limen/blob/main/docs/divulgazione/06-trasparenza-e-riproducibilita.md) | capitolo 8 |
| [`architecture.md`](https://github.com/agent-engineering-studio/limen/blob/main/docs/architecture.md), [`runbook.md`](https://github.com/agent-engineering-studio/limen/blob/main/docs/runbook.md) | capitolo 7 |
| [Come funziona](https://github.com/agent-engineering-studio/limen/blob/main/docs/guida/limen.md) (la guida nella mappa) | capitoli 4 e 7 |
| [README](https://github.com/agent-engineering-studio/limen/blob/main/README.md): librerie, misure, licenze | capitoli 2, 5 e 8 |

## Una promessa sui numeri

Ogni cifra di questo libro viene dal codice, dai file di configurazione o dai
report di misura del repository, e accanto c'è scritto dove controllarla. Dove
un numero non è verificabile non c'è. I risultati scomodi stanno accanto a
quelli buoni: un sistema di supporto alle decisioni che nasconde i propri
errori non merita fiducia.
