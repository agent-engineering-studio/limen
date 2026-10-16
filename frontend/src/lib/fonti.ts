// Le fonti dei dati di Limen (#277): l'elenco unico da cui nasce `#/fonti`.
//
// Una riga per insieme di dati, raggruppate per ruolo: cosa entra nel calcolo
// delle tre probabilità, cosa serve a verificarle, cosa è solo contesto sulla
// mappa. Le licenze stanno qui e non in una seconda tabella.
//
// I loghi solo dove le regole del titolare li concedono a chi usa i dati: oggi
// OpenStreetMap, e solo come link al progetto. Copernicus li concede dopo una
// registrazione (copernicus.eu/en/form/license-agreement-form); la Protezione
// Civile li riserva per legge (art. 30 D.Lgs. 1/2018); ISTAT, EEA, ECMWF, NASA
// ed EFFIS li escludono dal riuso. Per tutti gli altri, il nome.

import type { HazardType } from "../types";
import type { Lingua } from "./i18n";

export type RuoloFonte = "calcolo" | "verifica" | "contesto" | "base" | "valutazione";

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
  licenza: string;
  /** La dicitura che la licenza chiede, quando ne chiede una precisa. */
  attribuzione?: Testo;
  url: string;
  /** Gira solo dove chi ospita Limen ha il file o la chiave. */
  facoltativa?: boolean;
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
    "Gli eventi accaduti davvero: servono a tarare le soglie e a misurare se Limen li aveva previsti, mai a calcolare il punteggio di oggi.",
    "Events that actually happened: they calibrate the thresholds and measure whether Limen had forecast them, never today's score.",
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
    "Reti verificate ma non ancora acquisite (#248): non entrano in nessun numero.",
    "Networks checked but not yet acquired (#248): they are in no number.",
  ),
};

export const ORDINE_RUOLI: readonly RuoloFonte[] = [
  "calcolo",
  "verifica",
  "contesto",
  "base",
  "valutazione",
];

const COPERNICUS_CEMS = t(
  "Contiene informazioni modificate del Copernicus Emergency Management Service",
  "Contains modified Copernicus Emergency Management Service information",
);

export const FONTI: readonly Fonte[] = [
  // --- calcolo: il tempo -----------------------------------------------------
  {
    id: "open-meteo",
    ente: "Open-Meteo",
    dataset: t(
      "Previsioni meteo (modelli ECMWF IFS e DWD ICON; per la forbice fra modelli anche Météo-France e NOAA GFS)",
      "Weather forecasts (ECMWF IFS and DWD ICON models; Météo-France and NOAA GFS for the spread between models)",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide", "flood", "wildfire"],
    cosa: t(
      "Pioggia oraria per nodo, umidità del suolo, neve, temperatura, umidità dell'aria e vento: la pioggia delle frane, il ramo pluviale delle alluvioni, gli ingressi dell'indice incendi.",
      "Hourly rain per node, soil moisture, snow, temperature, humidity and wind: the rain for landslides, the pluvial branch of floods, the inputs of the fire index.",
    ),
    licenza: "CC BY 4.0",
    attribuzione: t("Weather data by Open-Meteo.com", "Weather data by Open-Meteo.com"),
    url: "https://open-meteo.com",
  },
  {
    id: "open-meteo-marine",
    ente: "Open-Meteo",
    dataset: t("Previsione del moto ondoso (Marine API)", "Wave forecast (Marine API)"),
    ruolo: "calcolo",
    pericoli: ["landslide"],
    cosa: t(
      "L'altezza d'onda per le frane costiere: una mareggiata scalza il piede del versante.",
      "Wave height for coastal landslides: a storm surge undercuts the toe of the slope.",
    ),
    licenza: "CC BY 4.0",
    attribuzione: t("Weather data by Open-Meteo.com", "Weather data by Open-Meteo.com"),
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
      "La pioggia già caduta, ogni cinque minuti: entra nel ramo pluviale delle alluvioni e nell'indice incendi, e fa ricalcolare subito la regione dove piove forte.",
      "The rain already fallen, every five minutes: it enters the pluvial branch of floods and the fire index, and triggers an immediate recomputation where it rains hard.",
    ),
    licenza: "CC BY-SA 4.0",
    url: "https://radar.protezionecivile.it",
  },
  {
    id: "glofas",
    ente: "Copernicus Emergency Management Service",
    dataset: t(
      "GloFAS, previsione di portata dei fiumi (via Open-Meteo Flood API o EWDS)",
      "GloFAS, river discharge forecast (via Open-Meteo Flood API or EWDS)",
    ),
    ruolo: "calcolo",
    pericoli: ["flood", "landslide"],
    cosa: t(
      "La portata prevista a sette giorni per nodo, confrontata con la piena ordinaria di quel fiume: il ramo fluviale delle alluvioni.",
      "The seven-day discharge forecast per node, compared with that river's ordinary high flow: the fluvial branch of floods.",
    ),
    licenza: "Licenza CEMS-Floods",
    attribuzione: COPERNICUS_CEMS,
    url: "https://global-flood.emergency.copernicus.eu",
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
    cosa: t(
      "Quante frane sono già state censite attorno a ogni cella: il predittore più forte della suscettibilità.",
      "How many landslides have already been mapped around each cell: the strongest predictor of susceptibility.",
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
      "La classe ufficiale di pericolosità (P1-P4) delle Autorità di bacino, per cella.",
      "The official hazard class (P1-P4) of the River Basin Authorities, per cell.",
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
    pericoli: ["flood"],
    cosa: t(
      "Dove l'acqua è già stata studiata arrivare: la suscettibilità all'allagamento che moltiplica la spinta della pioggia e del fiume.",
      "Where water has been studied to reach: the flood susceptibility that multiplies the push from rain and river.",
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
    cosa: t(
      "La roccia sotto la cella: argille e flysch franano più del calcare.",
      "The rock under the cell: clays and flysch slide more than limestone.",
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
    pericoli: ["landslide", "wildfire"],
    cosa: t(
      "Pendenza, esposizione e curvatura di ogni cella: il terreno della frana e la corsa del fuoco in salita.",
      "Slope, aspect and curvature of each cell: the ground of a landslide and fire running uphill.",
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
    cosa: t(
      "L'uso del suolo: il combustibile per l'incendio, e cosa c'è da proteggere (case, infrastrutture) per l'esposizione.",
      "Land use: the fuel for wildfire, and what there is to protect (houses, infrastructure) for exposure.",
    ),
    licenza: "Copernicus, uso libero con attribuzione",
    url: "https://land.copernicus.eu/en/products/corine-land-cover",
    facoltativa: true,
  },
  {
    id: "imperviousness",
    ente: "Copernicus Land Monitoring Service",
    dataset: t(
      "HRL Imperviousness Density 2018",
      "HRL Imperviousness Density 2018",
    ),
    ruolo: "calcolo",
    pericoli: ["flood"],
    cosa: t(
      "Quanto suolo è asfaltato o costruito: dove l'acqua non entra nel terreno, la pioggia allaga prima.",
      "How much soil is sealed: where water cannot soak in, rain floods sooner.",
    ),
    licenza: "Copernicus, uso libero con attribuzione",
    url: "https://land.copernicus.eu/en/products/high-resolution-layer-imperviousness",
    facoltativa: true,
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
    cosa: t(
      "Di quanti millimetri all'anno si muove il suolo: lo usa solo il modello di apprendimento automatico sfidante, non la mappa.",
      "How many millimetres a year the ground moves: used only by the machine-learning challenger, not by the map.",
    ),
    licenza: "Copernicus, uso libero con attribuzione",
    url: "https://egms.land.copernicus.eu",
    facoltativa: true,
  },
  {
    id: "osm-reti",
    ente: "OpenStreetMap",
    dataset: t("Strade principali e ferrovie (estratto Geofabrik)", "Main roads and railways (Geofabrik extract)"),
    ruolo: "calcolo",
    pericoli: ["landslide", "flood", "wildfire"],
    cosa: t(
      "Quanto una cella è vicina a strade e ferrovie: una parte dell'esposizione.",
      "How close a cell is to roads and railways: part of the exposure.",
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
    cosa: t(
      "I terremoti dell'ultima settimana e lo scuotimento per cella: un versante appena scosso frana con meno pioggia.",
      "Earthquakes of the last week and the shaking per cell: a slope just shaken slides with less rain.",
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
    cosa: t(
      "Dove è bruciato: un versante senza vegetazione frana e scarica acqua più facilmente per mesi. Servono anche a verificare il pericolo incendio e come livello «Aree bruciate».",
      "Where it burnt: a slope stripped of vegetation slides and sheds water more easily for months. Also used to verify the wildfire hazard and as the \"Burnt areas\" layer.",
    ),
    licenza: "CC BY 4.0",
    url: "https://forest-fire.emergency.copernicus.eu",
  },
  {
    id: "firms",
    ente: "NASA FIRMS",
    dataset: t(
      "Punti caldi da satellite VIIRS e MODIS (LANCE)",
      "VIIRS and MODIS satellite hotspots (LANCE)",
    ),
    ruolo: "calcolo",
    pericoli: ["landslide", "wildfire"],
    cosa: t(
      "Un incendio visto dal satellite entro qualche ora: apre la finestra post-incendio prima che arrivi il perimetro, e l'archivio serve a tarare la severità.",
      "A fire seen from space within hours: it opens the post-fire window before the perimeter arrives, and the archive calibrates severity.",
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
    id: "italica",
    ente: "CNR-IRPI",
    dataset: t(
      "ITALICA, catalogo delle frane innescate dalla pioggia (1996-2021)",
      "ITALICA, catalogue of rainfall-induced landslides (1996-2021)",
    ),
    ruolo: "verifica",
    pericoli: ["landslide"],
    cosa: t(
      "Oltre seimila frane con data e luogo: tarano le soglie di pioggia e misurano quante Limen ne avrebbe viste.",
      "Over six thousand landslides with date and place: they calibrate the rain thresholds and measure how many Limen would have seen.",
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
      "Le alluvioni mappate da satellite durante le emergenze: la verità contro cui si misura il pericolo alluvione, e il livello «Alluvioni osservate».",
      "Floods mapped from satellite during emergencies: the truth the flood hazard is measured against, and the \"Observed floods\" layer.",
    ),
    licenza: "Copernicus, uso libero con attribuzione",
    attribuzione: t("© European Union, Copernicus EMS", "© European Union, Copernicus EMS"),
    url: "https://rapidmapping.emergency.copernicus.eu",
  },
  {
    id: "rianalisi",
    ente: "ECMWF / Copernicus Climate Change Service",
    dataset: t(
      "Rianalisi ERA5, ERA5-Land e CERRA (via Open-Meteo)",
      "ERA5, ERA5-Land and CERRA reanalyses (via Open-Meteo)",
    ),
    ruolo: "verifica",
    pericoli: ["landslide", "flood", "wildfire"],
    cosa: t(
      "Il tempo del passato, ricostruito: per rigiocare gli eventi storici e per avviare la catena dell'indice incendi.",
      "Past weather, reconstructed: to replay historical events and to start the fire-index chain.",
    ),
    licenza: "Licenza Copernicus",
    attribuzione: t(
      "Contiene informazioni modificate del Copernicus Climate Change Service",
      "Contains modified Copernicus Climate Change Service information",
    ),
    url: "https://cds.climate.copernicus.eu",
  },
  {
    id: "it-dpc-sri",
    ente: "FBK su dati del Dipartimento della Protezione Civile",
    dataset: t("IT-DPC-SRI, archivio radar 2010-2025", "IT-DPC-SRI, radar archive 2010-2025"),
    ruolo: "verifica",
    pericoli: ["landslide"],
    cosa: t(
      "Quindici anni di pioggia da radar per rigiocare le frane del catalogo con la pioggia osservata invece di quella prevista.",
      "Fifteen years of radar rain to replay the catalogued landslides with observed instead of forecast rain.",
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
    cosa: t(
      "Le allerte ufficiali di oggi, accanto a quelle stimate da Limen: sono quelle che contano per la sicurezza.",
      "Today's official warnings, next to Limen's estimates: they are the ones that count for safety.",
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
      "Pluviometri e sonde costruiti da cittadini, scuole ed enti: oggi sulla mappa e nelle verifiche; quelli degli enti possono entrare nel calcolo.",
      "Rain gauges and probes built by citizens, schools and institutions: on the map and in the checks today; institutional ones can enter the computation.",
    ),
    licenza: "CC BY 4.0",
    url: "#/sensori",
  },
  // --- base ------------------------------------------------------------------
  {
    id: "istat",
    ente: "ISTAT",
    dataset: t("Confini amministrativi di regioni e comuni", "Administrative boundaries of regions and municipalities"),
    ruolo: "base",
    pericoli: [],
    cosa: t(
      "Le regioni, i comuni e il contorno d'Italia su cui si costruiscono la griglia e la lista dei comuni.",
      "The regions, municipalities and outline of Italy on which the grid and the list of municipalities are built.",
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
    cosa: t(
      "Strade, città e nomi sotto le celle colorate.",
      "Roads, towns and names under the coloured cells.",
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
    id: "meteonetwork",
    ente: "Associazione MeteoNetwork OdV",
    dataset: t("Stazioni meteo amatoriali", "Amateur weather stations"),
    ruolo: "valutazione",
    pericoli: ["landslide", "flood"],
    cosa: t(
      "L'unica rete cittadina italiana con pluviometri e licenza aperta. Per leggerla per regione serve un accesso dedicato, chiesto all'associazione.",
      "The only Italian citizen network with rain gauges and an open licence. Reading it by region needs dedicated access, requested from the association.",
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
      "Molti sensori in Emilia-Romagna, pochissimi al Sud, e nessun pluviometro: utili al più per l'indice incendi.",
      "Many sensors in Emilia-Romagna, very few in the South, and no rain gauges: useful at most for the fire index.",
    ),
    licenza: "DbCL (da confermare)",
    url: "https://sensor.community",
  },
];

/** Le fonti di un ruolo, nell'ordine dell'elenco. */
export function fontiDelRuolo(ruolo: RuoloFonte): readonly Fonte[] {
  return FONTI.filter((f) => f.ruolo === ruolo);
}
