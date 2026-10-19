// Le fonti dei dati di Limen (#277, #280): l'elenco unico da cui nasce `#/fonti`.
//
// Una riga per insieme di dati, raggruppate per ruolo: cosa entra nel calcolo
// delle tre probabilità, cosa serve a verificarle, cosa è solo contesto sulla
// mappa. Per ognuna **come si legge** (protocollo, cadenza, dove finisce) e
// **come la usa Limen** (la trasformazione e i numeri, dai YAML dei pericoli:
// cambiare un peso là senza cambiarlo qui rende la pagina falsa). Le licenze
// stanno qui e non in una seconda tabella.
//
// I loghi solo dove le regole del titolare li concedono a chi usa i dati: oggi
// OpenStreetMap, e solo come link al progetto. Copernicus li concede dopo una
// registrazione; la Protezione Civile li riserva per legge (art. 30 D.Lgs.
// 1/2018); ISTAT, EEA, ECMWF, NASA ed EFFIS li escludono dal riuso. Per tutti
// gli altri, il nome.

import type { HazardType } from "../types";
import type { Lingua } from "./i18n";

export type RuoloFonte = "calcolo" | "verifica" | "contesto" | "base" | "valutazione";

/** Il servizio Copernicus da cui viene il dato, per il riquadro di provenienza. */
export type ServizioCopernicus = "CEMS" | "CLMS" | "C3S" | "EFFIS";

type Testo = Record<Lingua, string>;

export interface Logo {
  /** Sotto `public/`. */
  file: string;
  /** Le regole d'uso del titolare, che ne permettono l'uso qui. */
  regole: string;
  /** La nota che le regole chiedono accanto al logo. */
  nota: Testo;
}

export interface Fonte {
  id: string;
  ente: string;
  dataset: Testo;
  ruolo: RuoloFonte;
  /** I pericoli a cui serve; vuoto per la geografia di base. */
  pericoli: readonly HazardType[];
  cosa: Testo;
  /** Protocollo, cadenza, dove finisce in Limen. */
  accesso: Testo;
  /** Come Limen trasforma il dato e quanto pesa. */
  interpretazione: Testo;
  licenza: string;
  /** La dicitura che la licenza chiede, quando ne chiede una precisa. */
  attribuzione?: Testo;
  url: string;
  /** Gira solo dove chi ospita Limen ha il file o la chiave. */
  facoltativa?: boolean;
  /** Dato aperto del programma europeo Copernicus. */
  copernicus?: ServizioCopernicus;
  logo?: Logo;
}

const t = (it: string, en: string): Testo => ({ it, en });

export const NOME_RUOLO: Record<RuoloFonte, Testo> = {
  calcolo: t("Entrano nel calcolo", "Used in the computation"),
  verifica: t("Servono a verificare", "Used to verify"),
  contesto: t("Contesto sulla mappa", "Context on the map"),
  base: t("Geografia di base", "Base geography"),
  valutazione: t("In valutazione", "Under evaluation"),
};

export const SPIEGAZIONE_RUOLO: Record<RuoloFonte, Testo> = {
  calcolo: t(
    "Questi dati diventano i numeri della mappa: senza, il punteggio di una cella cambia o diventa «non misurato».",
    "These data become the numbers on the map: without them, a cell's score changes or becomes \"not measured\".",
  ),
  verifica: t(
    "Gli eventi accaduti davvero e i calcoli ufficiali: servono a tarare le soglie e a misurare Limen, mai a calcolare il punteggio di oggi.",
    "Events that actually happened and official computations: they calibrate the thresholds and measure Limen, never today's score.",
  ),
  contesto: t(
    "Si accendono sulla mappa accanto ai punteggi, per confrontarli; non li cambiano.",
    "They can be switched on next to the scores, to compare; they do not change them.",
  ),
  base: t(
    "La geografia su cui tutto il resto si appoggia.",
    "The geography everything else rests on.",
  ),
  valutazione: t(
    "Fonti verificate ma non ancora acquisite: non entrano in nessun numero finché un backtest non dice che servono.",
    "Sources checked but not yet acquired: they are in no number until a backtest says they help.",
  ),
};

export const ORDINE_RUOLI: readonly RuoloFonte[] = [
  "calcolo",
  "verifica",
  "contesto",
  "base",
  "valutazione",
];

export const NOME_SERVIZIO: Record<ServizioCopernicus, Testo> = {
  CEMS: t("Emergency Management Service", "Emergency Management Service"),
  CLMS: t("Land Monitoring Service", "Land Monitoring Service"),
  C3S: t("Climate Change Service", "Climate Change Service"),
  EFFIS: t("European Forest Fire Information System", "European Forest Fire Information System"),
};

const COPERNICUS_CEMS = t(
  "Contiene informazioni modificate del Copernicus Emergency Management Service",
  "Contains modified Copernicus Emergency Management Service information",
);
const COPERNICUS_C3S = t(
  "Contiene informazioni modificate del Copernicus Climate Change Service",
  "Contains modified Copernicus Climate Change Service information",
);
const OPEN_METEO = t("Weather data by Open-Meteo.com", "Weather data by Open-Meteo.com");

export const FONTI: readonly Fonte[] = [
  // --- calcolo: il tempo -----------------------------------------------------
  {
    id: "open-meteo",
    ente: "Open-Meteo",
    dataset: t(
      "Previsioni meteo dei modelli europei (ECMWF, DWD ICON) e, per la forbice fra modelli, Météo-France, NOAA GFS ed ECMWF AIFS",
      "Weather forecasts from European models (ECMWF, DWD ICON) and, for the spread between models, Météo-France, NOAA GFS and ECMWF AIFS",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide", "flood", "wildfire"],
    cosa: t(
      "Pioggia oraria, umidità del suolo, neve, temperatura, umidità dell'aria e vento.",
      "Hourly rain, soil moisture, snow, temperature, humidity and wind.",
    ),
    accesso: t(
      "API REST, da un'istanza propria sul server quando c'è. A ogni giro orario: 48 ore di pioggia per nodo e umidità del suolo; a mezzogiorno temperatura, umidità, vento e pioggia per la catena dell'indice incendi (tabella fwi_state).",
      "REST API, from a self-hosted instance when there is one. Every hourly run: 48 hours of rain per node and soil moisture; at noon temperature, humidity, wind and rain for the fire-index chain (fwi_state table).",
    ),
    interpretazione: t(
      "Frana, componente meteo M = 0,45 pioggia oltre la soglia di Caine (curve per Nord, Centro, Sud) + 0,30 pioggia dei 30 giorni + 0,25 umidità del suolo, più la pioggia sulla neve (fino a +0,15). Alluvione: la pioggia delle 72 ore per nodo, da 40 mm (inizio) a 120 mm (pieno), smorzata se il suolo è asciutto. Incendio: gli ingressi della catena FWI canadese (Van Wagner 1987).",
      "Landslide, weather component M = 0.45 rain above the Caine threshold (curves for North, Centre, South) + 0.30 rain of the last 30 days + 0.25 soil moisture, plus rain on snow (up to +0.15). Flood: 72-hour rain per node, from 40 mm (onset) to 120 mm (full), damped when the soil is dry. Wildfire: the inputs of the Canadian FWI chain (Van Wagner 1987).",
    ),
    licenza: "CC BY 4.0",
    attribuzione: OPEN_METEO,
    url: "https://open-meteo.com",
  },
  {
    id: "rianalisi",
    ente: "ECMWF / Copernicus Climate Change Service",
    dataset: t(
      "Rianalisi ERA5, ERA5-Land e CERRA (via Open-Meteo)",
      "ERA5, ERA5-Land and CERRA reanalyses (via Open-Meteo)",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide", "flood", "wildfire"],
    cosa: t(
      "Il tempo del passato, ricostruito.",
      "Past weather, reconstructed.",
    ),
    accesso: t(
      "Archivio di Open-Meteo. A ogni giro: la pioggia degli ultimi 30 giorni. Una tantum: l'avvio della catena incendi (limen fwi-backfill), le climatologie, i backtest.",
      "Open-Meteo archive. Every run: the rain of the last 30 days. One-off: the fire-chain start (limen fwi-backfill), the climatologies, the backtests.",
    ),
    interpretazione: t(
      "La pioggia dei 30 giorni entra nella componente M delle frane con una sigmoide centrata su 80 mm. Lo storico avvia la catena FWI dal 1° aprile e dà i percentili mensili per il «rispetto al solito»; nei backtest rigioca gli eventi del catalogo.",
      "The 30-day rain enters the landslide M component through a sigmoid centred on 80 mm. The archive starts the FWI chain on 1 April and gives the monthly percentiles for \"compared with usual\"; in the backtests it replays the catalogued events.",
    ),
    licenza: "Licenza Copernicus",
    attribuzione: COPERNICUS_C3S,
    url: "https://cds.climate.copernicus.eu",
    copernicus: "C3S",
  },
  {
    id: "open-meteo-marine",
    ente: "Open-Meteo",
    dataset: t("Previsione del moto ondoso (Marine API)", "Wave forecast (Marine API)"),
    ruolo: "calcolo",
    pericoli: ["landslide"],
    cosa: t("L'altezza d'onda dei prossimi tre giorni.", "Wave height for the next three days."),
    accesso: t(
      "API REST, a ogni giro delle frane, al centro della regione.",
      "REST API, every landslide run, at the centre of the region.",
    ),
    interpretazione: t(
      "Mareggiata = altezza massima / 4 m. Entra solo nel termine idrologico H delle frane (peso 0,03), insieme a pioggia e fiumi; il motore dell'alluvione non la usa.",
      "Storm surge = maximum height / 4 m. It enters only the landslide hydrological term H (weight 0.03), together with rain and rivers; the flood engine does not use it.",
    ),
    licenza: "CC BY 4.0",
    attribuzione: OPEN_METEO,
    url: "https://open-meteo.com/en/docs/marine-weather-api",
  },
  {
    id: "dpc-radar",
    ente: "Dipartimento della Protezione Civile",
    dataset: t(
      "Radar meteorologico nazionale: SRI e «Merging» (radar corretto con i pluviometri)",
      "National weather radar: SRI and \"Merging\" (radar corrected with rain gauges)",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide", "flood", "wildfire"],
    cosa: t(
      "La pioggia che sta cadendo e quella già caduta.",
      "The rain falling now and the rain already fallen.",
    ),
    accesso: t(
      "API REST della Protezione Civile. L'intensità SRI ogni 15 minuti; la cumulata «Merging» delle 24 ore a ogni giro dell'alluvione e ogni notte per la catena incendi; un archivio locale per le verifiche.",
      "Civil Protection REST API. SRI intensity every 15 minutes; the 24-hour \"Merging\" accumulation every flood run and every night for the fire chain; a local archive for the checks.",
    ),
    interpretazione: t(
      "Oltre 30 mm/h su almeno tre pixel di una regione, Limen la ricalcola subito. Alluvione: pioggia = il massimo fra le 72 ore previste e le 24 ore osservate più le 48 previste (mediana 3×3 sul centro della cella; un salto oltre 150 mm diventa «non misurato»). Incendio: rifà gli ultimi tre giorni della catena con la pioggia misurata.",
      "Above 30 mm/h on at least three pixels of a region, Limen recomputes it at once. Flood: rain = the larger of the 72 forecast hours and the 24 observed hours plus the 48 forecast (3×3 median at the cell centre; a jump above 150 mm becomes \"not measured\"). Wildfire: it redoes the last three days of the chain with measured rain.",
    ),
    licenza: "CC BY-SA 4.0",
    url: "https://radar.protezionecivile.it",
  },
  {
    id: "glofas",
    ente: "Copernicus Emergency Management Service",
    dataset: t(
      "GloFAS, previsione di portata dei fiumi",
      "GloFAS, river discharge forecast",
    ),
    ruolo: "calcolo",
    pericoli: ["flood", "landslide"],
    cosa: t(
      "La portata dei fiumi prevista a sette giorni e quella ordinaria di ogni fiume.",
      "River discharge forecast at seven days and each river's ordinary flow.",
    ),
    accesso: t(
      "Due strade aperte: la Flood API di Open-Meteo, e l'Early Warning Data Store di Copernicus (API con chiave gratuita) che serve la stessa corsa a griglia: una corsa al giorno (00 UTC), che Limen cerca a ogni previsione per cella (02, 08, 14, 20 UTC). La piena ordinaria di ogni nodo (90° percentile di due anni) si costruisce di notte (tabella glofas_riferimento).",
      "Two open routes: the Open-Meteo Flood API, and the Copernicus Early Warning Data Store (API with a free key) that serves the same run as a grid: one run a day (00 UTC), which Limen looks for at every per-cell forecast (02, 08, 14, 20 UTC). Each node's ordinary high flow (90th percentile of two years) is built at night (glofas_riferimento table).",
    ),
    interpretazione: t(
      "Rapporto = picco previsto / piena ordinaria di quel nodo: da 1,6 il ramo fluviale si accende, a 10 è pieno. Un nodo senza riferimento non dà zero, dà «non so quanto è grande questo fiume». Alluvione = suscettibilità × il massimo fra pioggia e fiume.",
      "Ratio = forecast peak / that node's ordinary high flow: the fluvial branch starts at 1.6 and is full at 10. A node without a reference does not give zero, it gives \"I don't know how big this river is\". Flood = susceptibility × the larger of rain and river.",
    ),
    licenza: "Licenza CEMS-Floods",
    attribuzione: COPERNICUS_CEMS,
    url: "https://global-flood.emergency.copernicus.eu",
    copernicus: "CEMS",
  },
  // --- calcolo: il terreno ---------------------------------------------------
  {
    id: "ispra-iffi",
    ente: "ISPRA",
    dataset: t(
      "IFFI, Inventario dei Fenomeni Franosi in Italia (IdroGEO)",
      "IFFI, Italian Landslide Inventory (IdroGEO)",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide"],
    cosa: t("Le frane già censite.", "The landslides already mapped."),
    accesso: t(
      "Servizio WFS di IdroGEO ogni lunedì, oppure il database nazionale caricato sul server; il valore per cella si ricalcola quando la fonte cambia.",
      "IdroGEO WFS service every Monday, or the national database loaded on the server; the per-cell value is recomputed when the source changes.",
    ),
    interpretazione: t(
      "Quante frane cadono entro 500 m dalla cella, saturando a 8. È il peso più grande della suscettibilità S delle frane: 0,375.",
      "How many landslides fall within 500 m of the cell, saturating at 8. It is the largest weight of the landslide susceptibility S: 0.375.",
    ),
    licenza: "CC BY 4.0",
    url: "https://idrogeo.isprambiente.it",
  },
  {
    id: "ispra-pai",
    ente: "ISPRA",
    dataset: t(
      "Mosaicatura nazionale della pericolosità da frana PAI",
      "National mosaic of PAI landslide hazard",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide"],
    cosa: t(
      "La classe ufficiale di pericolosità delle Autorità di bacino.",
      "The official hazard class of the River Basin Authorities.",
    ),
    accesso: t(
      "Come l'IFFI: WFS di IdroGEO o database nazionale, valore per cella al bootstrap.",
      "As for IFFI: IdroGEO WFS or national database, per-cell value at bootstrap.",
    ),
    interpretazione: t(
      "La classe più alta che tocca la cella: aree di attenzione 0,20, P1 0,40, P2 0,60, P3 0,80, P4 1,00. Peso nella suscettibilità S: 0,225.",
      "The highest class touching the cell: attention areas 0.20, P1 0.40, P2 0.60, P3 0.80, P4 1.00. Weight in susceptibility S: 0.225.",
    ),
    licenza: "CC BY 4.0",
    url: "https://idrogeo.isprambiente.it",
  },
  {
    id: "ispra-idraulica",
    ente: "ISPRA",
    dataset: t(
      "Mosaicatura nazionale della pericolosità idraulica",
      "National mosaic of hydraulic hazard",
    ),
    ruolo: "calcolo",
    pericoli: ["flood", "landslide"],
    cosa: t("Dove l'acqua è già stata studiata arrivare.", "Where water has been studied to reach."),
    accesso: t(
      "Dal database nazionale caricato sul server, valore per cella al bootstrap.",
      "From the national database loaded on the server, per-cell value at bootstrap.",
    ),
    interpretazione: t(
      "Suscettibilità all'allagamento: P3 0,80, P2 0,60, P1 0,40; una cella non studiata vale 0,15 (non studiata non vuol dire non allagabile), sotto 0,05 l'acqua non arriva e il punteggio è zero. Moltiplica la spinta di pioggia e fiume. Nelle frane pesa 0,03 nel termine H.",
      "Flood susceptibility: P3 0.80, P2 0.60, P1 0.40; an unstudied cell is 0.15 (unstudied does not mean it cannot flood), below 0.05 water does not reach and the score is zero. It multiplies the push of rain and river. In landslides it weighs 0.03 in term H.",
    ),
    licenza: "CC BY 4.0",
    url: "https://idrogeo.isprambiente.it",
    facoltativa: true,
  },
  {
    id: "ispra-geologia",
    ente: "ISPRA",
    dataset: t("Carta geolitologica d'Italia", "Geolithological map of Italy"),
    ruolo: "calcolo",
    pericoli: ["landslide"],
    cosa: t("La roccia sotto la cella.", "The rock under the cell."),
    accesso: t("File locale, al bootstrap.", "Local file, at bootstrap."),
    interpretazione: t(
      "La litologia che copre più area della cella, con un peso: argille e complessi caotici 0,85, flysch 0,80, marne 0,70, calcari 0,30, graniti 0,20; ignota 0,5. Peso nella suscettibilità S: 0,10.",
      "The lithology covering most of the cell, with a weight: clays and chaotic complexes 0.85, flysch 0.80, marls 0.70, limestones 0.30, granites 0.20; unknown 0.5. Weight in susceptibility S: 0.10.",
    ),
    licenza: "CC BY 4.0",
    url: "https://www.isprambiente.gov.it",
    facoltativa: true,
  },
  {
    id: "ingv-tinitaly",
    ente: "INGV",
    dataset: t("Modello digitale del terreno TINITALY", "TINITALY digital elevation model"),
    ruolo: "calcolo",
    pericoli: ["landslide", "wildfire", "flood"],
    cosa: t("La forma del terreno.", "The shape of the ground."),
    accesso: t(
      "File locale, al bootstrap: pendenza media, esposizione e curvatura per cella.",
      "Local file, at bootstrap: mean slope, aspect and curvature per cell.",
    ),
    interpretazione: t(
      "Frana: pendenza / 45°, peso 0,30 nella suscettibilità. Incendio: pendenza / 35°, peso 0,15 (il fuoco corre in salita). Alluvione: dove il terreno è piatto (sotto 15°) e costruito, una cella non studiata sale fino a 0,80.",
      "Landslide: slope / 45°, weight 0.30 in susceptibility. Wildfire: slope / 35°, weight 0.15 (fire runs uphill). Flood: where the ground is flat (below 15°) and built up, an unstudied cell rises up to 0.80.",
    ),
    licenza: "CC BY 4.0",
    url: "https://tinitaly.pi.ingv.it",
    facoltativa: true,
  },
  {
    id: "corine",
    ente: "Copernicus Land Monitoring Service / EEA",
    dataset: t("CORINE Land Cover 2018", "CORINE Land Cover 2018"),
    ruolo: "calcolo",
    pericoli: ["wildfire", "landslide", "flood"],
    cosa: t("L'uso del suolo.", "Land use."),
    accesso: t(
      "File locale, al bootstrap: la classe prevalente di ogni cella.",
      "Local file, at bootstrap: the prevailing class of each cell.",
    ),
    interpretazione: t(
      "Incendio, combustibile (peso 0,60): conifere 1,00, macchia e sclerofille 0,85-0,90, boschi di latifoglie 0,65, coltivi 0,35, città 0,05, rocce nude 0,05, acque 0. Incendio = FWI normalizzato × (0,25 + 0,60 combustibile + 0,15 pendenza). Città e infrastrutture vicine alzano la priorità di un'allerta, non il punteggio.",
      "Wildfire, fuel (weight 0.60): conifers 1.00, scrub and sclerophyll 0.85-0.90, broadleaf woods 0.65, crops 0.35, towns 0.05, bare rock 0.05, water 0. Wildfire = normalised FWI × (0.25 + 0.60 fuel + 0.15 slope). Nearby towns and infrastructure raise an alert's priority, not the score.",
    ),
    licenza: "Copernicus, uso libero con attribuzione",
    url: "https://land.copernicus.eu/en/products/corine-land-cover",
    facoltativa: true,
    copernicus: "CLMS",
  },
  {
    id: "imperviousness",
    ente: "Copernicus Land Monitoring Service",
    dataset: t("HRL Imperviousness Density 2018", "HRL Imperviousness Density 2018"),
    ruolo: "calcolo",
    pericoli: ["flood"],
    cosa: t("Quanto suolo è asfaltato o costruito.", "How much soil is sealed."),
    accesso: t(
      "Servizio ImageServer dell'Agenzia europea dell'ambiente, aperto e senza account, a 100 m; poi il bootstrap fa la media per cella.",
      "European Environment Agency ImageServer, open and without an account, at 100 m; then the bootstrap averages it per cell.",
    ),
    interpretazione: t(
      "Solo il ramo pluviale dell'alluvione: la pioggia vale fino a 1,6 volte dove il suolo è tutto sigillato (1 + 0,6 × quota impermeabile); e una cella non studiata, piatta e costruita per almeno il 30 %, ha suscettibilità fino a 0,80.",
      "Only the pluvial branch of floods: rain counts up to 1.6 times where the soil is fully sealed (1 + 0.6 × sealed share); and an unstudied cell that is flat and at least 30% built up has susceptibility up to 0.80.",
    ),
    licenza: "Copernicus, uso libero con attribuzione",
    url: "https://land.copernicus.eu/en/products/high-resolution-layer-imperviousness",
    facoltativa: true,
    copernicus: "CLMS",
  },
  {
    id: "egms",
    ente: "Copernicus Land Monitoring Service",
    dataset: t(
      "EGMS, European Ground Motion Service (interferometria radar)",
      "EGMS, European Ground Motion Service (radar interferometry)",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide"],
    cosa: t("Di quanti millimetri all'anno si muove il suolo.", "How many millimetres a year the ground moves."),
    accesso: t(
      "API dell'archivio CLMS con chiave di servizio, una volta per release (oggi 2020-2024).",
      "CLMS archive API with a service key, once per release (today 2020-2024).",
    ),
    interpretazione: t(
      "Velocità per cella (90° percentile) e numero di punti misurati: solo per il modello di apprendimento automatico sfidante, non per la mappa.",
      "Velocity per cell (90th percentile) and number of measured points: only for the machine-learning challenger, not for the map.",
    ),
    licenza: "Copernicus, uso libero con attribuzione",
    url: "https://egms.land.copernicus.eu",
    facoltativa: true,
    copernicus: "CLMS",
  },
  {
    id: "osm-reti",
    ente: "OpenStreetMap",
    dataset: t(
      "Strade principali e ferrovie (estratto Geofabrik)",
      "Main roads and railways (Geofabrik extract)",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide", "flood", "wildfire"],
    cosa: t("Strade e ferrovie.", "Roads and railways."),
    accesso: t("File locale, al bootstrap: la distanza di ogni cella.", "Local file, at bootstrap: each cell's distance."),
    interpretazione: t(
      "Esposizione: una strada entro 250 m aggiunge 0,6, entro 1 km 0,3; una ferrovia 0,5 e 0,25. Alza la priorità di un'allerta, non il punteggio.",
      "Exposure: a road within 250 m adds 0.6, within 1 km 0.3; a railway 0.5 and 0.25. It raises an alert's priority, not the score.",
    ),
    licenza: "ODbL",
    attribuzione: t("© OpenStreetMap contributors", "© OpenStreetMap contributors"),
    url: "https://www.openstreetmap.org",
    facoltativa: true,
  },
  // --- calcolo: eventi in corso ---------------------------------------------
  {
    id: "ingv-terremoti",
    ente: "INGV",
    dataset: t("Terremoti (servizio FDSN) e ShakeMap", "Earthquakes (FDSN service) and ShakeMap"),
    ruolo: "calcolo",
    pericoli: ["landslide"],
    cosa: t("I terremoti dell'ultima settimana.", "Earthquakes of the last week."),
    accesso: t(
      "Servizio FDSN e ShakeMap dell'INGV. Oggi la sincronizzazione non è attiva (#284): la componente sismica vale zero.",
      "INGV FDSN service and ShakeMap. Today the synchronisation is not active (#284): the seismic component is zero.",
    ),
    interpretazione: t(
      "Componente E delle frane (peso 0,15): un terremoto di magnitudo almeno 3,5 nell'ultima settimana scuote il versante, e l'effetto cala in pochi giorni (costante di due giorni). Da correggere con lo scuotimento per cella e la distanza (#284).",
      "Landslide component E (weight 0.15): an earthquake of magnitude 3.5 or more in the last week shakes the slope, and the effect fades within days (two-day constant). To be fixed with per-cell shaking and distance (#284).",
    ),
    licenza: "CC BY 4.0",
    url: "https://terremoti.ingv.it",
  },
  {
    id: "effis",
    ente: "EFFIS (Copernicus, JRC)",
    dataset: t("Perimetri delle aree bruciate", "Burnt-area perimeters"),
    ruolo: "calcolo",
    pericoli: ["landslide", "flood", "wildfire"],
    cosa: t("Dove è bruciato e quando.", "Where it burnt and when."),
    accesso: t(
      "Servizio WFS (MapServer) di EFFIS, pubblico e senza credenziali, ogni notte con 90 giorni di ritorno (tabella fire_perimeters).",
      "EFFIS WFS (MapServer) service, public and without credentials, every night with a 90-day look-back (fire_perimeters table).",
    ),
    interpretazione: t(
      "Frana, componente F (peso 0,07): un versante bruciato è più fragile, con un picco verso il sesto mese e per due anni, più forte se l'incendio è stato severo. Alluvione: per 18 mesi la pioggia su un bruciato vale fino a 1,6 volte. Incendio: la verità del backtest (alta allerta nelle 72 ore prima?).",
      "Landslide, component F (weight 0.07): a burnt slope is weaker, peaking around the sixth month and lasting two years, stronger after a severe fire. Flood: for 18 months rain on a burnt area counts up to 1.6 times. Wildfire: the truth of the backtest (high alert in the 72 hours before?).",
    ),
    licenza: "CC BY 4.0",
    url: "https://forest-fire.emergency.copernicus.eu",
    copernicus: "EFFIS",
  },
  {
    id: "firms",
    ente: "NASA FIRMS",
    dataset: t(
      "Punti caldi da satellite VIIRS e MODIS (LANCE)",
      "VIIRS and MODIS satellite hotspots (LANCE)",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide", "flood"],
    cosa: t("Un incendio visto dal satellite.", "A fire seen from space."),
    accesso: t(
      "API REST con chiave gratuita, ogni 45 minuti; l'archivio storico per paese è aperto.",
      "REST API with a free key, every 45 minutes; the historical archive per country is open.",
    ),
    interpretazione: t(
      "Due punti caldi in 24 ore fanno ricalcolare la regione e aprono la finestra post-incendio prima del perimetro EFFIS. La potenza radiativa dentro il perimetro dà la severità dell'incendio. Non entra nel pericolo incendio, che guarda il tempo.",
      "Two hotspots in 24 hours trigger a recomputation and open the post-fire window before the EFFIS perimeter. The radiative power inside the perimeter gives the fire's severity. It does not enter the wildfire hazard, which looks at the weather.",
    ),
    licenza: "Dati NASA, uso libero con attribuzione",
    attribuzione: t(
      "We acknowledge the use of data and/or imagery from NASA's LANCE, part of NASA's ESDIS",
      "We acknowledge the use of data and/or imagery from NASA's LANCE, part of NASA's ESDIS",
    ),
    url: "https://firms.modaps.eosdis.nasa.gov",
    facoltativa: true,
  },
  // --- verifica --------------------------------------------------------------
  {
    id: "cems-fire",
    ente: "Copernicus Emergency Management Service",
    dataset: t(
      "Indice di pericolo incendio ufficiale (CEMS Fire, storico)",
      "Official fire danger index (CEMS Fire, historical)",
    ),
    ruolo: "verifica",
    pericoli: ["wildfire"],
    cosa: t(
      "La stessa catena FWI che Limen calcola, calcolata da Copernicus su ERA5 dal 1940 a pochi giorni fa.",
      "The same FWI chain Limen computes, computed by Copernicus on ERA5 from 1940 to a few days ago.",
    ),
    accesso: t(
      "Early Warning Data Store di Copernicus, dataset cems-fire-historical-v1: API con la stessa chiave gratuita del GloFAS, NetCDF a 0,25° ritagliato sull'Italia; comando limen fwi-confronto.",
      "Copernicus Early Warning Data Store, dataset cems-fire-historical-v1: API with the same free key as GloFAS, NetCDF at 0.25° clipped to Italy; command limen fwi-confronto.",
    ),
    interpretazione: t(
      "Per ogni nodo e giorno fuori dall'avvio della catena: scarto medio, errore e correlazione per FWI, FFMC, DMC, DC, ISI, BUI, e quanti giorni cadono nella stessa classe di pericolo. Dice se la nostra catena deriva; non cambia il punteggio.",
      "For each node and day past the chain's start-up: mean difference, error and correlation for FWI, FFMC, DMC, DC, ISI, BUI, and how many days fall in the same danger class. It tells whether our chain drifts; it does not change the score.",
    ),
    licenza: "CC BY 4.0",
    attribuzione: COPERNICUS_CEMS,
    url: "https://ewds.climate.copernicus.eu/datasets/cems-fire-historical-v1",
    copernicus: "CEMS",
  },
  {
    id: "effis-fwi",
    ente: "EFFIS (Copernicus, JRC)",
    dataset: t(
      "Previsione del pericolo incendio EFFIS (meteo Météo-France)",
      "EFFIS fire danger forecast (Météo-France weather)",
    ),
    ruolo: "verifica",
    pericoli: ["wildfire"],
    cosa: t(
      "FWI e componenti dei giorni passati, di oggi e dei due seguenti.",
      "FWI and components for past days, today and the next two.",
    ),
    accesso: t(
      "Servizio WMS pubblico di EFFIS (layer mf010.fwi e componenti), chiesto come GeoTIFF con i valori numerici a 0,05°; comando limen fwi-confronto. Oltre dopodomani EFFIS risponde con un raster vuoto, che Limen legge come assenza del dato, non come giorno calmo.",
      "Public EFFIS WMS service (layer mf010.fwi and components), requested as a GeoTIFF with numeric values at 0.05°; command limen fwi-confronto. Beyond the day after tomorrow EFFIS answers with an empty raster, which Limen reads as missing data, not as a calm day.",
    ),
    interpretazione: t(
      "Lo stesso confronto della riga sopra, con un secondo modello meteo: se due calcoli ufficiali concordano fra loro e non con Limen, lo scarto è nostro.",
      "The same comparison as the row above, with a second weather model: if two official computations agree with each other and not with Limen, the gap is ours.",
    ),
    licenza: "CC BY 4.0",
    url: "https://forest-fire.emergency.copernicus.eu/applications/data-and-services",
    copernicus: "EFFIS",
  },
  {
    id: "italica",
    ente: "CNR-IRPI",
    dataset: t(
      "ITALICA, catalogo delle frane innescate dalla pioggia (1996-2021)",
      "ITALICA, catalogue of rainfall-induced landslides (1996-2021)",
    ),
    ruolo: "verifica",
    pericoli: ["landslide"],
    cosa: t("Oltre seimila frane con data e luogo.", "Over six thousand landslides with date and place."),
    accesso: t("Zenodo, con limen ingest-events.", "Zenodo, with limen ingest-events."),
    interpretazione: t(
      "Ha tarato le soglie di pioggia di Caine su 5.974 eventi. Nel backtest una frana è «vista» se la sua cella era almeno in classe Alta nelle ore prima; si chiede almeno il 70 % di frane viste con 18 ore d'anticipo, e una capacità di distinguerle almeno doppia del caso.",
      "It calibrated the Caine rain thresholds on 5,974 events. In the backtest a landslide is \"seen\" if its cell was at least High in the hours before; the target is at least 70% seen with 18 hours' lead, and a discrimination at least twice chance.",
    ),
    licenza: "CC BY 4.0",
    url: "https://zenodo.org/records/14204473",
  },
  {
    id: "cems-rapid-mapping",
    ente: "Copernicus Emergency Management Service",
    dataset: t("Rapid Mapping: le aree allagate osservate", "Rapid Mapping: observed flooded areas"),
    ruolo: "verifica",
    pericoli: ["flood"],
    cosa: t(
      "Le alluvioni mappate da satellite durante le emergenze.",
      "Floods mapped from satellite during emergencies.",
    ),
    accesso: t(
      "API pubblica del Rapid Mapping, senza credenziali, con limen ingest-events.",
      "Public Rapid Mapping API, without credentials, with limen ingest-events.",
    ),
    interpretazione: t(
      "La verità del backtest alluvione: almeno il 70 % di eventi visti con 12 ore d'anticipo e non più del 30 % di falsi allarmi, contati solo dove il satellite ha davvero guardato. Ha tarato le soglie 40/120 mm e 1,6/10. È anche il livello «Alluvioni osservate».",
      "The truth of the flood backtest: at least 70% of events seen with 12 hours' lead and at most 30% false alarms, counted only where the satellite actually looked. It calibrated the 40/120 mm and 1.6/10 thresholds. It is also the \"Observed floods\" layer.",
    ),
    licenza: "Copernicus, uso libero con attribuzione",
    attribuzione: t("© European Union, Copernicus EMS", "© European Union, Copernicus EMS"),
    url: "https://rapidmapping.emergency.copernicus.eu",
    copernicus: "CEMS",
  },
  {
    id: "it-dpc-sri",
    ente: "FBK su dati del Dipartimento della Protezione Civile",
    dataset: t("IT-DPC-SRI, archivio radar 2010-2025", "IT-DPC-SRI, radar archive 2010-2025"),
    ruolo: "verifica",
    pericoli: ["landslide"],
    cosa: t("Quindici anni di pioggia da radar.", "Fifteen years of radar rain."),
    accesso: t("Copia locale dell'archivio Zenodo.", "Local copy of the Zenodo archive."),
    interpretazione: t(
      "Rigioca le frane del catalogo con la pioggia osservata invece di quella prevista, per sapere se un mancato allarme è colpa della pioggia in ingresso o del modello.",
      "It replays the catalogued landslides with observed instead of forecast rain, to tell whether a missed alarm is due to the input rain or to the model.",
    ),
    licenza: "CC BY-SA 4.0",
    url: "https://zenodo.org/records/18637608",
    facoltativa: true,
  },
  // --- contesto --------------------------------------------------------------
  {
    id: "dpc-bollettini",
    ente: "Dipartimento della Protezione Civile",
    dataset: t(
      "Bollettino di criticità idrogeologica e idraulica nazionale",
      "National hydrogeological and hydraulic criticality bulletin",
    ),
    ruolo: "contesto",
    pericoli: ["landslide", "flood"],
    cosa: t("Le allerte ufficiali di oggi.", "Today's official warnings."),
    accesso: t(
      "Repository GitHub della Protezione Civile, ogni ora.",
      "Civil Protection GitHub repository, every hour.",
    ),
    interpretazione: t(
      "Non entra nel punteggio: si mostra accanto a quello di Limen (gialla, arancione, rossa). Sono le allerte che contano per la sicurezza.",
      "It does not enter the score: it is shown next to Limen's (yellow, orange, red). They are the warnings that count for safety.",
    ),
    licenza: "CC BY 4.0",
    url: "https://github.com/pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica",
  },
  {
    id: "sensori-cittadini",
    ente: "Rete dei sensori di Limen",
    dataset: t("Stazioni dei cittadini e degli enti", "Citizen and institutional stations"),
    ruolo: "contesto",
    pericoli: ["landslide", "flood"],
    cosa: t(
      "Pluviometri e sonde costruiti da cittadini, scuole ed enti.",
      "Rain gauges and probes built by citizens, schools and institutions.",
    ),
    accesso: t(
      "MQTT con un certificato per dispositivo; aggregati ogni ora.",
      "MQTT with one certificate per device; aggregated every hour.",
    ),
    interpretazione: t(
      "Solo le stazioni degli enti (livello 2) entrano nel calcolo delle frane; quelle dei cittadini stanno sulla mappa e nelle verifiche, e non fanno mai scattare un'allerta.",
      "Only institutional stations (level 2) enter the landslide computation; citizen ones are on the map and in the checks, and never trigger an alert.",
    ),
    licenza: "CC BY 4.0",
    url: "#/sensori",
  },
  // --- base ------------------------------------------------------------------
  {
    id: "istat",
    ente: "ISTAT",
    dataset: t(
      "Confini amministrativi di regioni e comuni",
      "Administrative boundaries of regions and municipalities",
    ),
    ruolo: "base",
    pericoli: [],
    cosa: t("Regioni, comuni e il contorno d'Italia.", "Regions, municipalities and the outline of Italy."),
    accesso: t("Caricati una volta nel database.", "Loaded once into the database."),
    interpretazione: t(
      "Ogni cella appartiene a un comune; la lista dei comuni e il riepilogo per regione nascono da qui. Nessun peso nel punteggio.",
      "Each cell belongs to a municipality; the municipalities list and the regional summary come from here. No weight in the score.",
    ),
    licenza: "CC BY 4.0",
    url: "https://www.istat.it",
  },
  {
    id: "osm-mappa",
    ente: "OpenStreetMap",
    dataset: t("La mappa di sfondo", "The background map"),
    ruolo: "base",
    pericoli: [],
    cosa: t("Strade, città e nomi.", "Roads, towns and names."),
    accesso: t("Tile raster di openstreetmap.org.", "Raster tiles from openstreetmap.org."),
    interpretazione: t(
      "Solo lo sfondo, scurito perché i colori del rischio si leggano.",
      "Only the background, darkened so the risk colours can be read.",
    ),
    licenza: "ODbL",
    attribuzione: t("© OpenStreetMap contributors", "© OpenStreetMap contributors"),
    url: "https://www.openstreetmap.org",
    logo: {
      file: "fonti/openstreetmap.svg",
      regole: "https://osmfoundation.org/wiki/Trademark_Policy",
      nota: t(
        "OpenStreetMap è un marchio della OpenStreetMap Foundation, usato con il suo permesso. Limen non è approvato né affiliato alla OpenStreetMap Foundation.",
        "OpenStreetMap is a trademark of the OpenStreetMap Foundation, and is used with their permission. Limen is not endorsed by or affiliated with the OpenStreetMap Foundation.",
      ),
    },
  },
  // --- valutazione -----------------------------------------------------------
  {
    id: "edo-cdi",
    ente: "Copernicus Emergency Management Service",
    dataset: t(
      "European Drought Observatory: indicatore combinato di siccità",
      "European Drought Observatory: combined drought indicator",
    ),
    ruolo: "valutazione",
    pericoli: ["wildfire"],
    cosa: t(
      "Quanto è secca la stagione, tre volte al mese, a circa 5 km.",
      "How dry the season is, three times a month, at about 5 km.",
    ),
    accesso: t(
      "Cartella HTTP aperta dell'osservatorio, un NetCDF di pochi MB l'anno, senza account.",
      "Open HTTP folder of the observatory, a NetCDF of a few MB a year, without an account.",
    ),
    interpretazione: t(
      "Da provare nel backtest incendio come aridità di stagione (#281): entra nel motore solo se migliora la capacità di distinguere i giorni pericolosi.",
      "To be tried in the wildfire backtest as seasonal dryness (#281): it enters the engine only if it improves how well dangerous days are told apart.",
    ),
    licenza: "CC BY 4.0",
    url: "https://drought.emergency.copernicus.eu",
    copernicus: "CEMS",
  },
  {
    id: "edo-umidita",
    ente: "Copernicus Emergency Management Service",
    dataset: t(
      "European Drought Observatory: umidità del suolo e sua anomalia",
      "European Drought Observatory: soil moisture and its anomaly",
    ),
    ruolo: "valutazione",
    pericoli: ["landslide"],
    cosa: t(
      "Quanto è bagnato il terreno rispetto al solito, dal 1995.",
      "How wet the ground is compared with usual, since 1995.",
    ),
    accesso: t(
      "Stessa cartella aperta, un NetCDF di circa 500 MB l'anno.",
      "Same open folder, a NetCDF of about 500 MB a year.",
    ),
    interpretazione: t(
      "Da confrontare nel backtest frane con l'umidità di Open-Meteo che la componente M usa oggi (#282).",
      "To be compared in the landslide backtest with the Open-Meteo soil moisture the M component uses today (#282).",
    ),
    licenza: "CC BY 4.0",
    url: "https://drought.emergency.copernicus.eu",
    copernicus: "CEMS",
  },
  {
    id: "effis-combustibile",
    ente: "EFFIS (Copernicus, JRC)",
    dataset: t("Mappa europea del combustibile", "European fuel map"),
    ruolo: "valutazione",
    pericoli: ["wildfire"],
    cosa: t("I tipi di vegetazione che bruciano.", "The kinds of vegetation that burn."),
    accesso: t(
      "WMS di EFFIS per vederla; per i valori serve lo shapefile, da recuperare.",
      "EFFIS WMS to view it; the values need the shapefile, still to be obtained.",
    ),
    interpretazione: t(
      "Candidata a sostituire CORINE nel termine combustibile dell'incendio, dopo un backtest (#283).",
      "Candidate to replace CORINE in the wildfire fuel term, after a backtest (#283).",
    ),
    licenza: "CC BY 4.0",
    url: "https://forest-fire.emergency.copernicus.eu/applications/data-and-services",
    copernicus: "EFFIS",
  },
  {
    id: "meteonetwork",
    ente: "Associazione MeteoNetwork OdV",
    dataset: t("Stazioni meteo amatoriali", "Amateur weather stations"),
    ruolo: "valutazione",
    pericoli: ["landslide", "flood"],
    cosa: t(
      "L'unica rete cittadina italiana con pluviometri e licenza aperta.",
      "The only Italian citizen network with rain gauges and an open licence.",
    ),
    accesso: t(
      "API v3 con un token gratuito per le stazioni singole; per leggere una regione serve un accesso dedicato, da chiedere all'associazione (#248).",
      "API v3 with a free token for single stations; reading a region needs dedicated access, requested from the association (#248).",
    ),
    interpretazione: t(
      "Entrerebbe come osservatore (livello 0): sulla mappa e nel confronto con il radar, mai nel punteggio.",
      "It would enter as an observer (level 0): on the map and in the comparison with radar, never in the score.",
    ),
    licenza: "CC BY 4.0",
    url: "https://www.meteonetwork.it",
  },
  {
    id: "sensor-community",
    ente: "Sensor.Community",
    dataset: t("Sensori di temperatura e umidità", "Temperature and humidity sensors"),
    ruolo: "valutazione",
    pericoli: ["wildfire"],
    cosa: t(
      "Molti sensori in Emilia-Romagna, pochissimi al Sud, nessun pluviometro.",
      "Many sensors in Emilia-Romagna, very few in the South, no rain gauges.",
    ),
    accesso: t("API aperta, aggiornata ogni pochi minuti.", "Open API, updated every few minutes."),
    interpretazione: t(
      "Utile al più come temperatura e umidità per l'indice incendi, come osservatore.",
      "Useful at most as temperature and humidity for the fire index, as an observer.",
    ),
    licenza: "DbCL (da confermare)",
    url: "https://sensor.community",
  },
];

/** Le fonti di un ruolo, nell'ordine dell'elenco. */
export function fontiDelRuolo(ruolo: RuoloFonte): readonly Fonte[] {
  return FONTI.filter((f) => f.ruolo === ruolo);
}

/** Le fonti aperte del programma Copernicus, per il riquadro di provenienza. */
export function fontiCopernicus(): readonly Fonte[] {
  return FONTI.filter((f) => f.copernicus !== undefined);
}
