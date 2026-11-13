*English version: [finanziare-limen.en.md](./finanziare-limen.en.md)*

# Finanziare Limen

Questo documento serve a una fondazione, un'amministrazione o un programma
di finanziamento per sapere in cinque minuti che cosa compra, con quanto,
in quanto tempo e come si vedrà se ha funzionato. Le cifre sono datate e
ognuna rimanda al file del repository da cui viene. Redatto il 13 novembre
2026 (issue [#512](https://github.com/agent-engineering-studio/limen/issues/512)).

## 1. L'obiettivo, e a che punto siamo

Limen calcola ogni ora, per tutta Italia, il rischio di frana, alluvione e
incendio boschivo, con codice libero (licenza EUPL 1.2) che chiunque può
installare sul proprio server.

**L'obiettivo misurabile** (issue
[#345](https://github.com/agent-engineering-studio/limen/issues/345)):
prevedere entro 72 ore il **90 %** degli eventi riportati dalla cronaca,
tenendo in allerta al massimo il **10 %** dei comuni-giorno.

**Dove siamo oggi**, pericolo per pericolo:

| Pericolo | Misura | Data | Fonte |
|---|---|---|---|
| Frana | 49 % dei comuni colpiti presi con il 10 % di carico (153 su 313), sulle dodici finestre di prova. **Obiettivo non raggiunto.** | ottobre 2026 | `docs/book/05-misurare.md` (§ 8), issue #345 e #357 |
| Alluvione | 77 % delle celle allagate in allerta «alto» prima (Emilia-Romagna), 80 % (Lombardia), circa 50 ore di preavviso; ma falsi allarmi al 78 % e al 43 %, contro un obiettivo del 30 % | 8 nov 2026 | `docs/book/05-misurare.md` (§ 7) |
| Incendio | Italia, soglia «alto», 72 ore: 62 % delle celle bruciate prese contro un tasso di base dell'11 % nel 2024 (5,5 volte il caso), 68 % contro 12 % nel 2025 (5,5), 62 % contro 14 % nel 2026 fino al 10 novembre (4,5) | 12 nov 2026 | `docs/misure/backtest_wildfire_italia_*_High.md` |
| Eventi dalla cronaca | 8 eventi verificati (4 frane, 4 alluvioni), nessuno previsto sopra il livello abituale del comune. Sono troppo pochi per dire qualcosa | 29 ott 2026 | `docs/book/05-misurare.md` |

Il punto debole è la frana, e il motivo è misurato: la pioggia che arriva al
motore, presa dai modelli meteo, è circa il **62 %** di quella dei
pluviometri, e nelle Marche il 41 % (`docs/book/04-i-motori.md`, issue #122,
12 ottobre 2026). Le strade tentate per correggerlo sono scritte in
pubblico, con i loro numeri, nel capitolo 5 del libro.

## 2. Che cosa funziona già

- **Tre pericoli accesi** su tutta Italia: 20 regioni, 312.550 celle di
  1 km, ricalcolate ogni ora (`docs/analisi-offerta-pa.md`).
- **L'incendio distingue bene**: 4,5-5,5 volte il caso, con due-tre giorni
  di preavviso, sui perimetri ufficiali europei EFFIS.
- **Misure riproducibili**: ogni prova è un comando, e il suo report porta
  commit, versioni dei motori e ambiente (`docs/misure/`).
- **Nessun cloud obbligatorio**: gira in container Docker su un solo
  computer. L'intelligenza artificiale scrive solo i testi, mai i punteggi,
  e la spesa per Claude ha un tetto di **10 dollari al mese**, controllato a
  ogni richiesta (`docs/book/08-trasparenza.md`).
- **Il costo di esercizio di oggi non è misurato** (issue #492): l'istanza
  descritta nel libro gira su un computer da scrivania, non su un server
  (`docs/book/07-come-gira.md`). Su un cloud commerciale costerebbe fra
  4.000 e 12.000 dollari l'anno secondo la robustezza voluta (stima
  dell'11 ottobre 2026, `docs/analisi-costi-cloud.md`).

Che cosa **non** funziona ancora: la frana non supera la prova; l'alluvione
dà troppi falsi allarmi; il progetto dipende da **una sola persona** (una
modifica esterna su 311 accettate, novembre 2026, issue #514); la copia di
sicurezza sta sullo stesso computer e il ripristino non è mai stato provato
su una macchina pulita (issue #490 e #307).

## 3. Che cosa si compra

Cinque pacchetti, indipendenti: si può finanziarne uno solo. I costi sono
**stime**: le ore sono valutate a circa 300 euro a giornata e il personale a
60-70 mila euro l'anno di costo azienda per un tempo pieno senior, come
nell'analisi di offerta alla pubblica amministrazione
(`docs/analisi-offerta-pa.md`, 11 ottobre 2026); le altre basi sono
indicate riga per riga.

| # | Che cosa si compra | Costo stimato | Durata | Come si vede che ha funzionato |
|---|---|---|---|---|
| 1 | **Una seconda persona** che sviluppa e gestisce Limen, a metà tempo. Base: metà del costo di un tempo pieno senior | 30-35 k€ | 12 mesi | Modifiche esterne accettate (oggi 1 su 311); tempo di risposta alle segnalazioni; un aggiornamento e un ripristino fatti dalla seconda persona da sola |
| 2 | **Raccolta di eventi veri**: frane, allagamenti e incendi datati, regione per regione, dalla cronaca e dagli elenchi degli enti (formato già pronto, `limen importa-eventi`, issue #509). Base: 0,3 tempo pieno «assistenza e dati» | 18-22 k€ | 12 mesi | Eventi nel registro delle verifiche, per pericolo e regione (oggi 8); almeno un elenco di un ente importato con la sua licenza |
| 3 | **Un partner di ricerca per la frana** (università o istituto del CNR): pioggia misurata in ingresso al motore e soglie riviste con competenza geologica. Base: ordine di grandezza di un assegno di ricerca annuale più un contributo per i dati; stima non tratta dai documenti del progetto | 25-35 k€ | 12 mesi | Comuni colpiti presi con il 10 % di carico sulle dodici finestre, prima (49 %) e dopo; rapporto fra pioggia del motore e pluviometri (oggi circa 62 %) |
| 4 | **Un server di riserva e un archivio fuori sede**, con la prova di ripristino su una macchina pulita (issue #490, #307, #308). Base: 150-250 €/mese per una macchina virtuale su cloud italiano più 10-15 giornate di lavoro | 5-8 k€ | 3 mesi di lavoro, 12 mesi di servizio | Ripristino completo da zero su un server pulito, con il tempo misurato e pubblicato |
| 5 | **Un pilota con una Regione** per una stagione: installazione, taratura regionale, formazione di un ufficio di Protezione civile. Base: 40-70 giornate di lavoro, il costo di un'installazione regionale nell'analisi di offerta | 15-25 k€ | 6-9 mesi | Un rapporto d'uso di una stagione: chi l'ha aperto, per quali decisioni, quali eventi ha visto o mancato |
| | **Totale** | **93-125 k€** | | |

Limen resta **supporto alle decisioni**: non sostituisce l'allertamento dei
Centri Funzionali né IT-Alert. Nessun pacchetto cambia questo punto.

## 4. Canali di finanziamento

Verificati il **13 novembre 2026**. Requisiti e scadenze cambiano: vanno
ricontrollati prima di ogni domanda.

| Canale | Che cosa finanzia | Importo | Scadenza | Note |
|---|---|---|---|---|
| **NLnet**, bandi aperti (open call e fondi tematici) — <https://nlnet.nl/propose/> | Sviluppo tecnico di software libero e beni comuni digitali | 5.000-50.000 € per una prima sovvenzione | **3 gennaio 2027, 12:00 CET**; poi ogni due mesi, il 3 dei mesi dispari | Possono chiedere anche persone fisiche. Al 13/11 il modulo non accettava domande e la politica sull'uso dell'IA generativa era in revisione (<https://nlnet.nl/news/2026/20260903-call.html>). Il fondo NGI Zero Commons ha chiuso l'ultimo bando il 1° giugno 2026. Da verificare che un progetto di rischio territoriale rientri nei temi |
| **Horizon Europe, Cluster 3**, tema HORIZON-CL3-2027-01-DRS-03 «sistemi di supporto alle decisioni per le crisi» — <https://www.horizon-europe.gouv.fr/enhancing-decision-support-system-disaster-crises-leveraging-emerging-technologies-improved-civil> | Azioni di innovazione: sistemi di supporto alle decisioni, dall'allerta precoce all'azione, con IA spiegabile | 9 M€ per il tema; contributo per progetto non indicato | Apertura **5 maggio 2027**, chiusura **4 novembre 2027** | Serve un consorzio europeo; Limen vi entrerebbe come componente aperto accanto a un partner di ricerca. Date lette su un portale nazionale francese, da confermare sul portale Funding & Tenders della Commissione |

Controllati e **chiusi** alla data: programma LIFE, adattamento ai
cambiamenti climatici 2026 (chiuso il 22 settembre 2026; il bando 2027 non è
ancora verificato); Fondazione CRT «Piccoli Comuni» 2026 (30 settembre
2026); Compagnia di San Paolo «Simbiosi» 2026 (27 febbraio 2026). La ricerca non ha
trovato un bando aperto di fondazioni di origine bancaria sul rischio
idrogeologico; di solito escono a inizio anno.

Altri canali citati nei documenti del progetto e **non verificati** qui:
crediti cloud per progetti aperti o di ricerca (pagano server, non persone),
e dal lato degli enti i programmi regionali FESR 2021-2027, i fondi
regionali di protezione civile e Interreg (`docs/analisi-costi-cloud.md`,
`docs/analisi-offerta-pa.md`). Il PNRR chiude nel 2026.

## 5. Chi riceve i fondi

[da completare dal curatore: soggetto giuridico che riceve i fondi]

Qualunque sia il soggetto, il codice finanziato resta sotto EUPL 1.2: nessun
finanziamento può chiuderlo in un prodotto privato
(`docs/book/08-trasparenza.md`). Ogni risultato viene pubblicato con la sua
misura e il suo tasso di base, prima e dopo, in `docs/misure/`.
