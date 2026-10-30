// Lo stato della mappa condiviso (#317): pericolo, orizzonte, soglia,
// selezione, livelli di contesto, area inquadrata e vista.
//
// Un contesto e non props: una seconda vista (il rilievo, o una scena 3D)
// deve leggere lo **stesso** stato, o cambiando pericolo in 3D si torna in
// 2D su un altro pericolo. Lo stato fa il giro dell'URL
// (`#/mappa?vista=…&hazard=…&h=…`), così un link condiviso apre la stessa
// vista.
//
// Il pericolo non sta nel reducer: lo tiene `HazardProvider`, che lo risolve
// da `/api/hazards` e che una dozzina di pannelli legge già. Qui lo si
// espone accanto al resto, e lo si legge e scrive nell'URL.

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useState,
  type JSX,
  type ReactNode,
} from "react";

import { ORIZZONTI } from "../components/Timeline";
import type { CellSelection, ComuneGeometry, HazardView, RiskLevel } from "../types";
import { useHazard } from "./hazard";
import { cellaDaHash } from "./link-cella";
import { OVERLAYS } from "./overlays";

export type Vista = "2d" | "rilievo" | "3d";
const VISTE: readonly Vista[] = ["2d", "rilievo", "3d"];
const PERICOLI: readonly HazardView[] = ["multi", "landslide", "flood", "wildfire"];

/** L'area inquadrata. Il bbox non va nell'URL: centro e zoom bastano a
 *  riaprire la stessa vista, e il bbox dipende dalla finestra di chi apre. */
export interface Area {
  lon: number;
  lat: number;
  zoom: number;
}

/** Ciò che la tile della previsione dice della cella cliccata. */
export interface CellaPrevista {
  orizzonte: number;
  score: number;
  level: RiskLevel;
  hazard: string;
  target: string | null;
}

export type CellaScelta = CellSelection & { previsto?: CellaPrevista };

export interface StatoMappa {
  vista: Vista;
  /** Ore nel futuro: 0 è adesso, 24/48/72 la previsione per cella. */
  orizzonte: number;
  soloSoglia: boolean;
  overlayAttivi: ReadonlySet<string>;
  cella: CellaScelta | null;
  comune: ComuneGeometry | null;
  /** `null` è la vista di partenza della mappa. */
  area: Area | null;
}

export const STATO_INIZIALE: StatoMappa = {
  vista: "2d",
  orizzonte: 0,
  // Acceso di default, come nel design: con un quarto d'Italia in classe
  // bassa la mappa era una coperta, e si cercava il moderato sotto di essa.
  soloSoglia: true,
  overlayAttivi: new Set(),
  cella: null,
  comune: null,
  area: null,
};

/** Ciò che un link dice dello stato. Un campo assente non dice niente. */
export interface StatoDaLink {
  vista?: Vista;
  pericolo?: HazardView;
  orizzonte?: number;
  soloSoglia?: boolean;
  overlayAttivi?: ReadonlySet<string>;
  area: Area | null;
}

/** Le rotte che mostrano la mappa. `#/italia` è un vecchio deep-link. */
export function rottaMappa(hash: string): boolean {
  const rotta = hash.split("?")[0] ?? "";
  return rotta === "#/dashboard" || rotta === "#/mappa" || rotta === "#/italia";
}

export function statoDaHash(hash: string): StatoDaLink {
  const p = new URLSearchParams(hash.split("?")[1] ?? "");
  const out: StatoDaLink = { area: null };
  const vista = p.get("vista");
  if (VISTE.includes(vista as Vista)) out.vista = vista as Vista;
  const pericolo = p.get("hazard");
  if (PERICOLI.includes(pericolo as HazardView)) out.pericolo = pericolo as HazardView;
  const h = Number(p.get("h") ?? "");
  if (p.get("h") && (ORIZZONTI as readonly number[]).includes(h)) out.orizzonte = h;
  const soglia = p.get("soglia");
  if (soglia === "0" || soglia === "1") out.soloSoglia = soglia === "1";
  const livelli = p.get("livelli");
  if (livelli !== null) {
    const noti = new Set(OVERLAYS.map((o) => o.id));
    out.overlayAttivi = new Set(livelli.split(",").filter((id) => noti.has(id)));
  }
  const [lon, lat] = (p.get("centro") ?? "").split(",").map(Number);
  const zoom = Number(p.get("z") ?? "");
  // MapLibre lancia su una latitudine fuori scala, e al primo caricamento
  // un link sbagliato smonterebbe l'app invece di aprire la vista di default.
  const valida =
    [lon, lat, zoom].every(Number.isFinite) &&
    Math.abs(lat as number) <= 90 &&
    Math.abs(lon as number) <= 180 &&
    zoom >= 0 &&
    zoom <= 24;
  if (p.get("centro") && p.get("z") && valida) {
    out.area = { lon: lon as number, lat: lat as number, zoom };
  }
  return out;
}

const CHIAVI = ["vista", "hazard", "h", "soglia", "livelli", "centro", "z"];

/** L'hash con lo stato dentro. Solo i campi lontani dal default, così la
 *  mappa di chi non tocca niente resta `#/dashboard`; gli altri parametri
 *  (`cella`, `lang`) restano dove sono. */
export function hashDaStato(hash: string, stato: StatoMappa, pericolo: HazardView): string {
  const [rotta = "", query = ""] = hash.split("?");
  const p = new URLSearchParams(query);
  for (const k of CHIAVI) p.delete(k);
  if (stato.vista !== STATO_INIZIALE.vista) p.set("vista", stato.vista);
  if (pericolo !== "multi") p.set("hazard", pericolo);
  if (stato.orizzonte !== 0) p.set("h", String(stato.orizzonte));
  if (stato.soloSoglia !== STATO_INIZIALE.soloSoglia) p.set("soglia", stato.soloSoglia ? "1" : "0");
  if (stato.overlayAttivi.size > 0) {
    p.set("livelli", OVERLAYS.filter((o) => stato.overlayAttivi.has(o.id)).map((o) => o.id).join(","));
  }
  if (stato.area) {
    p.set("centro", `${stato.area.lon.toFixed(4)},${stato.area.lat.toFixed(4)}`);
    p.set("z", stato.area.zoom.toFixed(2));
  }
  // La virgola è lecita in un frammento: `%2C` renderebbe il link illeggibile.
  const q = p.toString().replace(/%2C/gi, ",");
  return q ? `${rotta}?${q}` : rotta;
}

type Azione =
  | { tipo: "vista"; vista: Vista }
  | { tipo: "orizzonte"; orizzonte: number }
  | { tipo: "soloSoglia"; valore: boolean }
  | { tipo: "overlay"; id: string }
  | { tipo: "cella"; cella: CellaScelta | null }
  | { tipo: "clic"; cellId: string; lngLat?: { lng: number; lat: number }; proprieta?: Record<string, unknown> }
  | { tipo: "comune"; comune: ComuneGeometry | null }
  | { tipo: "area"; area: Area | null }
  | { tipo: "link"; link: StatoDaLink };

export function riduci(stato: StatoMappa, a: Azione): StatoMappa {
  switch (a.tipo) {
    case "vista":
      return { ...stato, vista: a.vista };
    case "orizzonte":
      return { ...stato, orizzonte: a.orizzonte };
    case "soloSoglia":
      return { ...stato, soloSoglia: a.valore };
    case "overlay": {
      const dopo = new Set(stato.overlayAttivi);
      if (dopo.has(a.id)) dopo.delete(a.id);
      else dopo.add(a.id);
      return { ...stato, overlayAttivi: dopo };
    }
    case "cella":
      return { ...stato, cella: a.cella };
    case "clic": {
      // Il punto cliccato, non il centro della cella: l'ispettore si apre lì
      // accanto, dove l'occhio già sta.
      const p = a.proprieta;
      const previsto: CellaPrevista | undefined =
        stato.orizzonte > 0 && p && typeof p["risk_score"] === "number"
          ? {
              orizzonte: stato.orizzonte,
              score: p["risk_score"],
              level: p["risk_level"] as RiskLevel,
              hazard: String(p["worst_hazard"] ?? ""),
              target: typeof p["target_at"] === "string" ? p["target_at"] : null,
            }
          : undefined;
      return {
        ...stato,
        cella: { cellId: a.cellId, lon: a.lngLat?.lng ?? null, lat: a.lngLat?.lat ?? null, previsto },
      };
    }
    case "comune":
      return { ...stato, comune: a.comune };
    case "area":
      return { ...stato, area: a.area };
    case "link": {
      // Un campo che il link non nomina resta com'è: tornando dalla guida a
      // `#/dashboard` pericolo e orizzonte erano quelli lasciati, e devono
      // restarlo. L'area no: la mappa riparte dalla vista del link, o da
      // quella di default.
      const l = a.link;
      return {
        ...stato,
        vista: l.vista ?? stato.vista,
        orizzonte: l.orizzonte ?? stato.orizzonte,
        soloSoglia: l.soloSoglia ?? stato.soloSoglia,
        overlayAttivi: l.overlayAttivi ?? stato.overlayAttivi,
        area: l.area,
      };
    }
  }
}

/** Ciò che l'ultimo hash diceva di un posto: la cella di un link diretto e
 *  l'area inquadrata. Cambia solo a un `hashchange`, non a ogni movimento. */
export interface LinkPosto {
  cella: ReturnType<typeof cellaDaHash>;
  area: Area | null;
}

function linkDaHash(hash: string): LinkPosto {
  return {
    cella: cellaDaHash(hash),
    area: rottaMappa(hash) ? statoDaHash(hash).area : null,
  };
}

export interface MapStateValue extends StatoMappa {
  pericolo: HazardView;
  link: LinkPosto;
  /** Alla prima apertura la mappa va sulla posizione del browser, a meno
   *  che un link non abbia già un posto da mostrare. */
  geolocalizza: boolean;
  impostaVista: (v: Vista) => void;
  impostaPericolo: (v: HazardView) => void;
  impostaOrizzonte: (h: number) => void;
  impostaSoloSoglia: (v: boolean) => void;
  commutaOverlay: (id: string) => void;
  selezionaCella: (c: CellaScelta | null) => void;
  cliccaCella: (
    cellId: string,
    lngLat?: { lng: number; lat: number },
    proprieta?: Record<string, unknown>,
  ) => void;
  evidenziaComune: (c: ComuneGeometry | null) => void;
  impostaArea: (a: Area | null) => void;
}

const MapStateContext = createContext<MapStateValue | null>(null);

function statoIniziale(): StatoMappa {
  const hash = window.location.hash;
  return rottaMappa(hash) ? riduci(STATO_INIZIALE, { tipo: "link", link: statoDaHash(hash) }) : STATO_INIZIALE;
}

/** Il pericolo di un link, per aprire `HazardProvider` già su quello. */
export function pericoloDaHash(hash: string): HazardView | undefined {
  return rottaMappa(hash) ? statoDaHash(hash).pericolo : undefined;
}

export function MapStateProvider({ children }: { children: ReactNode }): JSX.Element {
  const { view, select, available } = useHazard();
  const [stato, dispatch] = useReducer(riduci, undefined, statoIniziale);
  const [link, setLink] = useState<LinkPosto>(() => linkDaHash(window.location.hash));
  // Un hash che riporta sulla mappa va riscritto anche se lo stato non
  // cambia: il link della testata è `#/dashboard`, senza parametri.
  const [arrivi, setArrivi] = useState(0);
  // Il pericolo di un link arrivato a mappa aperta. Si applica solo se il
  // deployment lo offre, come per il link d'apertura (`HazardProvider`):
  // altrimenti mappa e pannelli chiederebbero dati che non esistono, e con
  // un pericolo solo non ci sarebbe nemmeno il selettore per tornare indietro.
  const [pericoloChiesto, setPericoloChiesto] = useState<HazardView | null>(null);

  useEffect(() => {
    const onHash = (): void => {
      const hash = window.location.hash;
      setLink(linkDaHash(hash));
      if (!rottaMappa(hash)) return;
      const l = statoDaHash(hash);
      dispatch({ tipo: "link", link: l });
      if (l.pericolo) setPericoloChiesto(l.pericolo);
      setArrivi((n) => n + 1);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    // Finché `/api/hazards` non risponde non si sa cosa c'è: si aspetta.
    if (!pericoloChiesto || available.length === 0) return;
    setPericoloChiesto(null);
    if (pericoloChiesto === view) return;
    const offerto =
      pericoloChiesto === "multi"
        ? available.length >= 2
        : available.some((h) => h.hazard === pericoloChiesto);
    if (offerto) select(pericoloChiesto);
  }, [pericoloChiesto, available, view, select]);

  useEffect(() => {
    const hash = window.location.hash;
    if (!rottaMappa(hash)) return;
    const nuovo = hashDaStato(hash, stato, view);
    // `replaceState` e non `location.hash`: niente `hashchange`, niente voce
    // nella cronologia a ogni trascinamento della mappa.
    if (nuovo !== hash) window.history.replaceState(window.history.state, "", nuovo);
  }, [stato, view, arrivi]);

  const azioni = useMemo(
    () => ({
      impostaVista: (vista: Vista) => dispatch({ tipo: "vista", vista }),
      impostaOrizzonte: (orizzonte: number) => dispatch({ tipo: "orizzonte", orizzonte }),
      impostaSoloSoglia: (valore: boolean) => dispatch({ tipo: "soloSoglia", valore }),
      commutaOverlay: (id: string) => dispatch({ tipo: "overlay", id }),
      selezionaCella: (cella: CellaScelta | null) => dispatch({ tipo: "cella", cella }),
      cliccaCella: (
        cellId: string,
        lngLat?: { lng: number; lat: number },
        proprieta?: Record<string, unknown>,
      ) => dispatch({ tipo: "clic", cellId, lngLat, proprieta }),
      evidenziaComune: (comune: ComuneGeometry | null) => dispatch({ tipo: "comune", comune }),
      impostaArea: (area: Area | null) => dispatch({ tipo: "area", area }),
    }),
    [],
  );
  const value = useMemo(
    () => ({
      ...stato,
      ...azioni,
      pericolo: view,
      impostaPericolo: select,
      link,
      geolocalizza: !link.cella && !link.area,
    }),
    [stato, azioni, view, select, link],
  );
  return <MapStateContext.Provider value={value}>{children}</MapStateContext.Provider>;
}

export function useMapState(): MapStateValue {
  const ctx = useContext(MapStateContext);
  if (ctx === null) throw new Error("useMapState fuori da MapStateProvider");
  return ctx;
}

/** Per `RiskMap`, che i test montano anche senza provider: `null` lì, e le
 *  props fanno da sole come prima. */
export function useMapStateOpzionale(): MapStateValue | null {
  return useContext(MapStateContext);
}
