# Limen, spiegato per gradi

**Limen** (in latino «soglia») è un sistema aperto che, ogni ora, stima
quanto ogni chilometro quadrato d'Italia è esposto a **frane, alluvioni e
incendi boschivi**. Divide il Paese in 312.550 quadrati da un chilometro di
lato, che chiamiamo **celle**. Per ognuna mette insieme quello che si sa del
posto (quanto è ripido, se è già franato, se può allagarsi, quanto bosco c'è)
con il tempo che fa e che farà. Il risultato è una mappa a cinque colori, con
uno sguardo ai tre giorni successivi. Ogni numero ha una regola scritta e una
fonte dichiarata. Il programma è libero e gira su un solo computer del
progetto, senza affittare servizi dai grandi fornitori di cloud.

## Che cosa vuole diventare

L'obiettivo di Limen è uno solo: **previsioni di altissima affidabilità**,
costruite con calcoli e modelli **messi alla prova** sugli eventi veri, così
da poter essere usato come strumento di monitoraggio per la **protezione del
territorio**. E vuole arrivarci usando modelli e dati che esistono già, aperti
e pubblici, invece di reinventarli.

L'affidabilità non si dichiara: si misura. Per questo il libro mette accanto a
ogni promessa la misura che dice quanto siamo vicini o lontani, e i risultati
scomodi accanto a quelli buoni.

!!! warning "Prima di tutto"
    Limen **non è un sistema di allertamento ufficiale**. Le allerte che
    contano le emettono il Dipartimento della Protezione Civile e i Centri
    Funzionali delle Regioni. Limen è uno strumento di supporto, aperto e
    controllabile da chiunque: i suoi avvisi non hanno valore legale.

## Perché questo libro

Il libro ha due scopi.

Il primo è **spiegare** come funziona Limen a chiunque: un assessore
comunale, un volontario di Protezione civile, un insegnante, un giornalista,
chi finanzia progetti per il territorio. Non serve sapere di informatica, di
statistica o di geologia. Ogni parola difficile viene spiegata la prima volta
che compare e raccolta nel glossario.

Il secondo è **cercare compagni di strada**. Limen migliora solo se ha dati
migliori e persone che li controllano. Ogni capitolo si chiude con una
sezione **«Gap e come chiuderli»**: che cosa manca ancora, perché conta e,
quando c'è, quale dato aperto lo colmerebbe. È un invito esplicito a enti,
ricercatori, aziende e cittadini: se avete sensori, studi o archivi di eventi,
condividerli come dati aperti rende migliore Limen e chiunque altro lavori sul
rischio.

## Come leggerlo

Ogni capitolo si apre con un riquadro **«In breve»** e si chiude con
**«Per approfondire»** (link e letture) e con i **gap**. I riquadri chiusi
**«Per chi sviluppa»** contengono i dettagli tecnici (nomi dei file, comandi,
formule): chi non scrive programmi può ignorarli senza perdere il filo.

| Se sei… | Leggi | Perché |
|---|---|---|
| **Chi decide o finanzia** (un ente, una fondazione, un'amministrazione) | 1 → 5 → 9 → 10 | cosa fa Limen, come si misura se funziona, cosa manca, come partecipare |
| **Chi lavora sul territorio** (un Comune, la Protezione civile, un tecnico, un ricercatore) | 1 → 3 → 4 → 5 → 9 | da dove vengono i dati, come diventano un colore, dove sbaglia, quali dati servono |
| **Chi sviluppa** (programmatori, analisti di dati, chi vuole contribuire) | tutto, in ordine | dai mattoni al cuore: è l'ordine in cui il sistema è costruito |

## Indice

| # | Capitolo | Di che cosa parla |
|---|---|---|
| 1 | [Il problema e cosa fa Limen](01-il-problema.md) | il rischio in Italia, cosa fa Limen e cosa non fa, i principi, a che punto siamo |
| 2 | [I mattoni: le librerie e perché ci sono](02-le-librerie.md) | i pezzi di programma che parlano con le fonti dei dati, e gli strumenti liberi su cui Limen si appoggia |
| 3 | [I dati: cosa misurano, da dove vengono, con quale licenza](03-i-dati.md) | territorio, meteo, satelliti, eventi veri; licenze e attribuzioni |
| 4 | [Dal dato al punteggio: frana, alluvione, incendio](04-i-motori.md) | come un dato diventa un colore; perché il meteo «comanda» e il territorio «modula» |
| 5 | [Misurare prima di cambiare](05-misurare.md) | come si controlla una previsione sugli eventi veri, con tre esempi di questo autunno |
| 6 | [Machine learning e intelligenza artificiale](06-ml-e-ai.md) | il modello che impara e resta in prova; l'intelligenza artificiale che scrive e non calcola |
| 7 | [Come gira](07-come-gira.md) | il ritmo orario, notturno e dei tre giorni; l'archivio, la mappa, gli avvisi |
| 8 | [Trasparenza, licenze, riproducibilità, costi](08-trasparenza.md) | come rifare tutto da zero, come controllare un punteggio, quanto costa tenerlo acceso |
| 9 | [Cosa manca: dati da aggiungere, standard e formati da diffondere](09-cosa-manca.md) | i dati che renderebbero Limen più affidabile, chi li ha, e i formati comuni per scambiarli |
| 10 | [Partecipare](10-partecipare.md) | collaboratori, enti, cittadini, finanziatori; la strada davanti |
| A | [Glossario](appendice-a-glossario.md) | ogni parola non ovvia |
| B | [Bibliografia](appendice-b-bibliografia.md) | articoli, rapporti, dati |
| C | [Indice delle librerie](appendice-c-librerie.md) | una riga per ogni libreria, con licenza e link |
| D | [Registro dei gap](appendice-d-gap.md) | tutti i gap del libro, con la proposta di open data e la issue |

## Una promessa sui numeri

Ogni cifra di questo libro viene dal codice, dai file di configurazione o dai
rapporti di misura del progetto, e accanto c'è scritto dove controllarla e
quando è stata misurata. Dove un numero non è verificabile non c'è. Un sistema
di supporto alle decisioni che nasconde i propri errori non merita fiducia.

??? note "Per chi sviluppa"
    - Sorgente del libro: `docs/book/`; configurazione del sito:
      `zensical.toml` (Zensical). Anteprima locale:
      `uv run --group docs zensical serve`; costruzione come nella CI:
      `uv run --group docs zensical build --strict`.
    - Le figure si rifanno con gli script in `scripts/libro/` (uno per
      figura, con fonte e data dei dati in testa).
    - Il libro riordina materiale che esiste già nel repository:
      `docs/divulgazione/` (sei schede e un glossario), `docs/guida/`,
      `docs/scoring-model.md`, `docs/ml.md`, `docs/architecture.md`,
      `docs/runbook.md`, il `README.md` e i commenti degli YAML in
      `src/limen/config/hazards/`.
