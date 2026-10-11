# Analisi di offerta — Limen alla PA come SaaS o self-hosted

> Redatta il 2026-10-11. Complementare a [`analisi-costi-cloud.md`](./analisi-costi-cloud.md),
> da cui riprende i costi infrastrutturali (in USD; qui trattati ≈ EUR, la
> differenza è sotto la precisione delle stime). I clienti considerati sono
> **Regioni** e **Comuni**. I prezzi di vendita e i costi di personale sono
> **ipotesi di lavoro**, non dati di mercato; i riferimenti normativi vanno
> verificati con un legale prima di un'offerta reale.

---

## 0. Cosa si vende

Limen è Apache-2.0: **la licenza non si vende**. Qualunque PA può
riusarlo gratis (CAD artt. 68-69), e qualunque integratore può installarlo.
Il ricavo viene da ciò che il codice non dà:

- **gestione del servizio** (SaaS) o **installazione e manutenzione** (self-host);
- **calibrazione regionale** delle soglie (`macroregion_by_aoi`, curve Caine,
  `classes`) e backtest sugli eventi storici del cliente;
- **SLA, assistenza, formazione**, integrazione con i sistemi del cliente;
- **responsabilità contrattuale**: un fornitore identificato che risponde.

L'open source è un vantaggio commerciale verso la PA (riuso, nessun lock-in,
pubblicabile su Developers Italia), ma toglie la rendita da licenza: il
margine sta nel servizio.

---

## 1. Vincoli del mercato PA

| Tema | Vincolo | Impatto su Limen |
|---|---|---|
| **Qualificazione ACN** dei servizi cloud | Una PA può acquistare solo servizi cloud (IaaS/PaaS/SaaS) qualificati da ACN, con livello coerente con la classificazione dei dati (ordinari / critici / strategici; livelli QC1–QC4 del regolamento ACN 2024) | **Il SaaS va qualificato** e deve girare su infrastruttura qualificata. Limen tratta dati ambientali pubblici: probabile classe *ordinari* → livello base. Hetzner non è qualificato; AWS/Azure/GCP (region Italia), Aruba, OVH lo sono — verificare sul catalogo ACN |
| **Strategia Cloud Italia / PSN** | Le PA devono dismettere i CED non adeguati e migrare in cloud qualificato o sul Polo Strategico Nazionale | Il self-host **presso un Comune** va contro la strategia: realistico solo presso una Regione (in-house, CED regionale qualificato) o sul PSN/cloud del cliente |
| **Codice appalti** (D.Lgs. 36/2023) | Affidamento diretto per servizi sotto 140.000 €; MePA (Consip) come canale ordinario | Ogni offerta annua sotto soglia si chiude senza gara. Serve l'iscrizione al MePA con il servizio a catalogo |
| **Riuso** (CAD art. 69, Linee guida AgID) | Il software per la PA va pubblicato in riuso | Già soddisfatto. Pubblicare su Developers Italia aiuta la scoperta |
| **GDPR** | Nel SaaS il fornitore è responsabile del trattamento (art. 28): servono DPA, registro dei trattamenti e dati in UE | Limen tratta pochi dati personali, ma qualcuno sì: destinatari degli alert (email, Telegram) e il modulo «Sei un esperto?» (#197). Servono DPIA leggera e informativa |
| **Accessibilità** (L. 4/2004, Linee guida AgID) | WCAG 2.1 AA e dichiarazione di accessibilità pubblicata | Il contrasto della rampa di rischio è già testato; serve un audit completo della SPA |
| **AI Act + L. 132/2025** | Trasparenza sui contenuti generati (art. 50); nella PA l'IA è di supporto, la decisione resta al funzionario | Il motore V1 è deterministico; i testi LLM sono già separati dal ripiego. Va fatta una valutazione formale della categoria di rischio (Allegato III) |
| **Protezione civile** (D.Lgs. 1/2018, DPCM 27/02/2004) | L'allertamento ufficiale spetta ai Centri Funzionali; alla popolazione arriva IT-Alert | Limen va venduto come **supporto alle decisioni**, mai come sistema di allerta. Va scritto nel contratto, insieme alla limitazione di responsabilità |
| **Licenze dei dati** | ISPRA, INGV, Copernicus, CORINE, TINITALY: aperti con attribuzione. **L'API pubblica Open-Meteo è solo per uso non commerciale** | Un servizio a pagamento deve usare l'istanza Open-Meteo self-hosted (già presente) **e** un piano commerciale per ciò che non si può ospitare (portata GloFAS, onde). Open-Meteo è AGPL-3.0: va bene usarlo non modificato; se lo si modifica, le modifiche vanno pubblicate |

---

## 2. Cosa manca per poterlo vendere

| Gap | Perché serve | Stima una tantum |
|---|---|---|
| **Area operatore con login** (SPID/CIE o SSO del cliente) | Ogni cliente configura i propri destinatari, soglie e canali di alert, e vede dati non pubblici (contributi degli esperti) | 20–30 gg-persona |
| **Multi-tenancy** | Tenant = insieme di AOI + configurazione degli alert + branding; i dati di rischio restano condivisi | 10–15 gg (sopra l'area operatore) |
| **Esercizio da produzione** | HA, monitoraggio, backup fuori sede, runbook di incidente, pagina di stato | 10–15 gg |
| **Dossier di qualificazione ACN** | Documentazione di sicurezza, misure, SLA, localizzazione dei dati | 10–20 k€ di consulenza (stima) + 10 gg interni |
| **Conformità** | DPA, DPIA, dichiarazione di accessibilità, test di penetrazione | 8–15 k€ (stima) |
| **Integrazione con il Centro Funzionale** | Esportazione CAP (Common Alerting Protocol), feed verso i sistemi regionali | 10–20 gg per Regione |
| **Piano commerciale Open-Meteo** | Licenza per uso commerciale di GloFAS e onde | costo da chiedere a Open-Meteo |

> L'area operatore va contro la decisione `auth-decision` (#69: nessun
> login). Quella decisione escludeva il login **per un bisogno ipotetico**;
> un contratto con un cliente è il bisogno reale che la memoria stessa
> indica come condizione per riaprirla.

**Totale per arrivare alla prima vendita: ~60–90 gg-persona + 20–35 k€ di
costi esterni.** Con un costo interno di ~300 €/gg sono **40–60 k€**.

---

## 3. Modello A — SaaS

### Architettura

Limen calcola già **tutta l'Italia in un solo sweep** (312.550 celle, 20
regioni). Ogni cliente in più non aggiunge calcolo: aggiunge una vista
filtrata sulle sue AOI e una configurazione degli alert. **Il costo
marginale per cliente è quasi zero**: è il punto di forza del SaaS.

### Costi annui fissi (ipotesi)

| Voce | €/anno | Note |
|---|---|---|
| Produzione in HA su cloud qualificato ACN | 10–12 k | scenario B con DB in HA di `analisi-costi-cloud.md` (~850 $/mese) |
| Ambiente di staging | 3–4 k | scenario A ridotto |
| Backup fuori sede, monitoraggio, dominio, certificati | 1–2 k | |
| LLM (Claude via gateway) | < 1 k | tetto attuale 50 $/30 gg |
| Piano commerciale Open-Meteo | da quotare | |
| Personale: 1 FTE dev/ops | 60–70 k | costo azienda, senior |
| Personale: 0,3 FTE assistenza e dati | 18–22 k | |
| Reperibilità fuori orario (opzionale) | 15–25 k | solo se lo SLA la chiede |
| Test di penetrazione annuale, audit | 5–8 k | |
| Assicurazione RC professionale | 3–6 k | stima |
| **Totale** | **~100–125 k** (senza reperibilità) · **~120–150 k** (con) | |

### Listino ipotetico

| Cliente | Canone annuo | Cosa include |
|---|---|---|
| Comune < 5.000 ab. | 1.000–1.500 € | mappa del territorio comunale, alert email/Telegram, report mensile |
| Comune 5.000–50.000 ab. | 3.000–6.000 € | come sopra, più trend storico, esportazione dati e assistenza |
| Comune > 50.000 / capoluogo | 8.000–15.000 € | come sopra, più API, integrazione con il piano comunale di protezione civile e formazione |
| **Regione** | **40.000–90.000 €** + 10–25 k€ di attivazione | piattaforma regionale, **tutti i Comuni della Regione inclusi**, calibrazione e backtest regionale, integrazione con il Centro Funzionale, SLA, formazione |

Tutto resta **sotto i 140 k€**: affidamento diretto o MePA, senza gara.

### Punto di pareggio (costi fissi ~110 k€)

| Mix di clienti | Ricavo annuo |
|---|---|
| 2 Regioni | 80–180 k€ ✅ |
| 1 Regione + 15 Comuni medi | 85–180 k€ ✅ |
| Solo Comuni | ~25–35 Comuni medi o ~100 piccoli |

Vendere ai singoli Comuni costa molto (un contatto commerciale per poche
migliaia di euro). **La Regione è il cliente naturale**: compra una volta e
distribuisce ai propri Comuni, come soggetto aggregatore o in convenzione.

---

## 4. Modello B — self-hosted presso il cliente

### Dove

| Cliente | Fattibile? |
|---|---|
| Regione con CED o società in-house (es. InnovaPuglia) | **Sì** |
| Regione su PSN o su un cloud qualificato contrattualizzato | **Sì**: il cliente fornisce la VM, noi installiamo |
| Comune | **No, in pratica**: la Strategia Cloud chiede di dismettere i CED comunali e le competenze sistemistiche mancano. Un Comune va servito via SaaS o tramite la Regione |

### Requisiti per un'installazione regionale

Una regione media ha ~15.600 celle, cioè il 5 % della griglia nazionale
(dalla Valle d'Aosta, ~3 k, alla Sicilia, ~25 k).

| Risorsa | Regionale | Nazionale (oggi) |
|---|---|---|
| vCPU / RAM | 4 / 16 GB | 8 / 32 GB |
| DB | ~3–5 GB (stima in proporzione, con lo storico) | 39 GB |
| Dati statici (DTM, CORINE, geologia ritagliati) | ~3–6 GB | ~47 GB |
| Open-Meteo self-hosted | 8–10 GB e CPU per l'ingestione: il volume dipende dai modelli scaricati, non dall'area | 8,6 GB |
| GPU | no | no |
| Costo infrastruttura per il cliente | ~150–250 €/mese su cloud qualificato; marginale su un CED esistente | |

**LLM in self-host**, a scelta del cliente:

- **nessuno**: il testo deterministico di ripiego è già completo e la mappa non cambia;
- **chiave Claude del cliente**, tramite il gateway (Bedrock `eu.*` o Vertex `eu` per la residenza UE);
- **modello locale su CPU**: lento, adatto solo al briefing asincrono.

**Dati meteo:** ogni installazione deve avere la propria istanza Open-Meteo,
o un piano commerciale. L'API gratuita non si può usare: è solo per uso
non commerciale, e anche una sola regione supererebbe il tetto (~500 località
per tick × 24 tick = ~12 k chiamate al giorno, contro un tetto di 10 k).

### Ricavi e costi per installazione (ipotesi)

| Voce | Cliente paga | Costo nostro |
|---|---|---|
| Installazione, calibrazione, integrazione, formazione | 25–45 k€ una tantum | 40–70 gg-persona (12–21 k€) |
| Manutenzione e assistenza annuale (aggiornamenti, SLA in orario d'ufficio) | 20–35 k€/anno | ~0,1–0,15 FTE (8–12 k€) |
| Infrastruttura | a carico del cliente | — |

Margine unitario buono, ma il costo **cresce con ogni installazione**:
versioni che divergono, accessi in VPN, aggiornamenti da coordinare con IT
diversi, problemi che si riproducono solo da loro. Oltre le 4–5
installazioni serve una persona dedicata solo al rilascio.

---

## 5. Confronto

| | SaaS | Self-hosted |
|---|---|---|
| Cliente adatto | Comuni (tutti), Regioni | Solo Regioni |
| Costo annuo per il cliente | 1–15 k€ (Comune) · 40–90 k€ (Regione) | 20–35 k€ + infrastruttura propria + 25–45 k€ di avvio |
| Costo marginale nostro per cliente | quasi zero | ~8–12 k€/anno |
| Tempo di attivazione | giorni | 1–3 mesi |
| Aggiornamenti | continui, uno per tutti | per installazione, lenti |
| Prerequisiti | **qualificazione ACN**, HA, DPA | nessuna qualificazione nostra; integrazione con l'IT del cliente |
| Calcolo nazionale | sì: un evento al confine tra regioni si vede da entrambe | solo l'AOI del cliente |
| Sovranità percepita | media (dati sul cloud del fornitore) | alta (dati in casa) |
| Rischio principale | costi fissi da coprire prima di avere clienti | supporto che cresce linearmente |

---

## 6. Raccomandazione

1. **Modello ibrido, con la Regione al centro.**
   - **SaaS** come offerta standard: una piattaforma nazionale qualificata ACN.
     Si vende alla Regione con i suoi Comuni inclusi; i Comuni di Regioni
     non clienti comprano direttamente da listino.
   - **Self-host** solo per le Regioni che lo richiedono per sovranità o
     policy interna, a prezzo pieno di avvio e manutenzione.
2. **Primo cliente pilota: Puglia o Basilicata.** Il pilota è già calibrato
   lì, ci sono i backtest sugli incendi e le verifiche (`#/verifiche`)
   mostrano casi concreti.
3. **Investimento prima della vendita: ~40–60 k€.** Copre area operatore,
   multi-tenancy, qualificazione ACN e conformità. Si rientra con 1 Regione
   oppure 10–15 Comuni medi nel primo anno.
4. **Il SaaS su infrastruttura italiana qualificata non tradisce la scelta
   «no hyperscaler»**: Aruba e OVH sono qualificati e restano coerenti con
   `deploy-target`. AWS, Azure e GCP servono solo se i crediti cloud lo rendono
   conveniente (vedi `analisi-costi-cloud.md`).
5. **Posizionamento contrattuale non negoziabile**: supporto alle
   decisioni, non sostituto dell'allertamento del Centro Funzionale né di
   IT-Alert; limitazione di responsabilità; RC professionale.

### Finanziamento lato cliente

La PA compra più facilmente se il servizio rientra in una linea già
finanziata:

- programmi regionali **FESR 2021-27** (obiettivo «adattamento ai cambiamenti climatici e prevenzione dei rischi»);
- fondi di **protezione civile** regionali;
- **Interreg**, per i progetti transfrontalieri;
- il **PNRR** si chiude nel 2026: non conviene contarci per nuovi contratti.

---

## 7. Dati da raccogliere prima di un'offerta reale

- Quotazione del piano commerciale Open-Meteo (GloFAS, onde).
- Verifica sul catalogo ACN del livello richiesto e dell'iter per un SaaS
  di dati ambientali pubblici.
- Parere legale su AI Act (categoria di rischio), clausole di
  responsabilità e posizionamento rispetto alla protezione civile.
- Prezzi reali di soluzioni comparabili già acquistate da Regioni e Comuni
  (MePA, albo pretorio, ANAC open data sugli affidamenti).
- Interviste a 2–3 Centri Funzionali e uffici comunali di protezione civile:
  cosa userebbero davvero, e su quale linea di bilancio.
