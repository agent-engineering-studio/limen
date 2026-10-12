import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";

import { solidSvg } from "../../iso/iso-kit";
import { Line, Solid } from "../../iso/react/draw";
import { follow, useInView, useLoop, useReadout } from "../../iso/react/live";
import {
  BASE_ART,
  DUCT_DOWN,
  DUCT_OUT,
  DUCT_RAIN,
  DUCT_RIVER,
  GATE_BACK,
  GATE_FRONT,
  GAUGE_BACK,
  GAUGE_FRONT,
  VALVE_BACK,
  VALVE_FRONT,
  fonteBack,
  fonteFront,
} from "./art";
import {
  BLADE,
  BLADE_RIBS,
  GATE_CORSA,
  GATE_HUB_TOP,
  IDROMETRO,
  PLUVIOMETRO,
  SHUTTLE,
  SHUTTLE_GRIP,
  astaDi,
  needleDi,
  shift,
  stemDi,
} from "./geometry";
import type { Ingressi, Stato } from "./model";
import { FLOOR, GIRO, PIOGGIA_MAX_MM, RAPPORTO_MAX, RIPOSO, statoDi } from "./model";
import { ASTA_CORSA, CONDOTTA_Z, HEIGHT, NAVETTA_CORSA, PIASTRA_GATE_H, TRAVERSA_Z, WIDTH, at, FONTE_TOP, FONTE_Y, IDROMETRO_X, PLUVIOMETRO_X } from "./view";

const SEGUI = 0.45;
const PAUSA_DOPO_MANO = 4;
const PARTI = ["pioggia", "fiume", "paratoia"] as const;
type Parte = (typeof PARTI)[number];

const PASSO: Record<Parte, number> = { pioggia: 8, fiume: 0.6, paratoia: 0.05 };
const MASSIMO: Record<Parte, number> = { pioggia: PIOGGIA_MAX_MM, fiume: RAPPORTO_MAX, paratoia: 1 };
const CHIAVE: Record<Parte, keyof Ingressi> = { pioggia: "pioggiaMm", fiume: "rapporto", paratoia: "suscettibilita" };

const ANCORE: Record<Parte, [number, number]> = {
  pioggia: at([PLUVIOMETRO_X, FONTE_Y, FONTE_TOP + 20]),
  fiume: at([IDROMETRO_X, FONTE_Y, FONTE_TOP + 20]),
  paratoia: at([0, 14, TRAVERSA_Z]),
};
const ALTO = at([0, 0, FONTE_TOP + 4 + ASTA_CORSA])[1];
const BASSO = at([0, 0, 0])[1];

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function giroA(t: number): Ingressi {
  const totale = GIRO.reduce((s, passo) => s + passo.secondi, 0);
  let resto = t % totale;
  for (const passo of GIRO) {
    if (resto < passo.secondi) return passo;
    resto -= passo.secondi;
  }
  return RIPOSO;
}

interface Nodi {
  rodRain: SVGGElement | null;
  rodRiver: SVGGElement | null;
  armRain: SVGGElement | null;
  armRiver: SVGGElement | null;
  shuttle: SVGGElement | null;
  blade: SVGGElement | null;
  stemLow: SVGGElement | null;
  stemHigh: SVGGElement | null;
  needle: SVGPathElement | null;
}

function disegna(n: Nodi, s: Stato) {
  const pioggia = s.pluviale;
  const fiume = s.fluviale;
  if (n.rodRain) n.rodRain.innerHTML = solidSvg(astaDi(PLUVIOMETRO, pioggia), { tone: s.ramo === "pioggia" ? "hi" : "mid", crease: "none" });
  if (n.rodRiver) n.rodRiver.innerHTML = solidSvg(astaDi(IDROMETRO, fiume), { tone: s.ramo === "fiume" ? "hi" : "mid", crease: "none" });
  n.armRain?.setAttribute("transform", shift(0, ASTA_CORSA * pioggia));
  n.armRiver?.setAttribute("transform", shift(0, ASTA_CORSA * fiume));
  // La navetta scappa dal lato che spinge di più e chiude l'altro.
  n.shuttle?.setAttribute("transform", shift(NAVETTA_CORSA * clamp((pioggia - fiume) * 6, -1, 1)));
  const apertura = s.suscettibilita < FLOOR ? 0 : GATE_CORSA * s.suscettibilita;
  n.blade?.setAttribute("transform", shift(0, apertura));
  const testa = CONDOTTA_Z + PIASTRA_GATE_H + apertura;
  if (n.stemLow) n.stemLow.innerHTML = solidSvg(stemDi(testa, TRAVERSA_Z - 1.5), { tone: "mid", crease: "none" });
  if (n.stemHigh) n.stemHigh.innerHTML = solidSvg(stemDi(GATE_HUB_TOP, testa + 22), { tone: "mid", crease: "none" });
  n.needle?.setAttribute("d", needleDi(s.punteggio));
}

interface Props {
  label: string;
  readoutOf: (s: Stato) => string;
  spokenOf: (s: Stato) => string;
}

export function AlluvioneLive({ label, readoutOf, spokenOf }: Props) {
  const { anchor, say } = useReadout<HTMLDivElement>();
  const stage = useRef<HTMLDivElement | null>(null);
  const svg = useRef<SVGSVGElement | null>(null);
  const inView = useInView(stage);
  const nodi = useRef<Nodi>({ rodRain: null, rodRiver: null, armRain: null, armRiver: null, shuttle: null, blade: null, stemLow: null, stemHigh: null, needle: null });
  const ora = useRef<Ingressi>({ ...RIPOSO });
  const meta = useRef<Ingressi>({ ...RIPOSO });
  const orologio = useRef(0);
  const mano = useRef(-Infinity);
  const [scelta, setScelta] = useState<Parte>("pioggia");
  const [detto, setDetto] = useState(() => spokenOf(statoDi(RIPOSO)));
  const ultimoDetto = useRef(detto);

  const riposo = useMemo(() => statoDi(RIPOSO), []);

  const aggiorna = useCallback(
    (s: Stato) => {
      disegna(nodi.current, s);
      say(readoutOf(s));
      const frase = spokenOf(s);
      if (frase !== ultimoDetto.current) {
        ultimoDetto.current = frase;
        setDetto(frase);
      }
    },
    [readoutOf, say, spokenOf],
  );

  useEffect(() => aggiorna(riposo), [aggiorna, riposo]);

  const kick = useLoop((dt, calm) => {
    orologio.current += dt;
    if (!calm && orologio.current - mano.current > PAUSA_DOPO_MANO) meta.current = { ...giroA(orologio.current) };
    const prima = ora.current;
    const dopo: Ingressi = {
      pioggiaMm: follow(prima.pioggiaMm, meta.current.pioggiaMm, dt, SEGUI, calm),
      rapporto: follow(prima.rapporto, meta.current.rapporto, dt, SEGUI, calm),
      suscettibilita: follow(prima.suscettibilita, meta.current.suscettibilita, dt, SEGUI, calm),
    };
    ora.current = dopo;
    aggiorna(statoDi(dopo));
    return !calm || dopo.pioggiaMm !== meta.current.pioggiaMm || dopo.rapporto !== meta.current.rapporto || dopo.suscettibilita !== meta.current.suscettibilita;
  }, inView);

  const imposta = useCallback(
    (parte: Parte, valore: number) => {
      mano.current = orologio.current;
      meta.current = { ...meta.current, [CHIAVE[parte]]: clamp(valore, 0, MASSIMO[parte]) };
      kick();
    },
    [kick],
  );

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const box = svg.current?.getBoundingClientRect();
    if (!box || box.width === 0) return;
    const x = ((event.clientX - box.left) / box.width) * WIDTH;
    const y = ((event.clientY - box.top) / box.height) * HEIGHT;
    let vicina: Parte = "pioggia";
    let distanza = Infinity;
    for (const parte of PARTI) {
      const [ax, ay] = ANCORE[parte];
      const d = Math.hypot(ax - x, (ay - y) * 0.6);
      if (d < distanza) {
        distanza = d;
        vicina = parte;
      }
    }
    setScelta(vicina);
    imposta(vicina, clamp((BASSO - y) / (BASSO - ALTO), 0, 1) * MASSIMO[vicina]);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const i = PARTI.indexOf(scelta);
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      setScelta(PARTI[(i + (event.key === "ArrowRight" ? 1 : PARTI.length - 1)) % PARTI.length]!);
      mano.current = orologio.current;
    } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      const verso = event.key === "ArrowUp" ? 1 : -1;
      imposta(scelta, meta.current[CHIAVE[scelta]] + verso * PASSO[scelta]);
    } else return;
    event.preventDefault();
  };

  const legaNodo = <K extends keyof Nodi>(nome: K) => (el: Nodi[K]) => {
    nodi.current[nome] = el;
  };

  return (
    <div
      ref={(el) => {
        stage.current = el;
        anchor.current = el;
      }}
      className="iso-stage fig-alluvione-stage"
      tabIndex={0}
      onPointerMove={onPointerMove}
      onKeyDown={onKeyDown}
      data-scelta={scelta}
    >
      <svg ref={svg} className="iso-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label} focusable="false">
        {BASE_ART}
        {fonteBack(PLUVIOMETRO, "rain-back")}
        <g ref={legaNodo("rodRain")} />
        <g ref={legaNodo("armRain")}>
          <Arm fonte={PLUVIOMETRO} />
        </g>
        {fonteFront(PLUVIOMETRO, "rain-front")}
        {DUCT_RAIN}
        {VALVE_BACK}
        <g ref={legaNodo("shuttle")}>
          <ShuttleArt />
        </g>
        {VALVE_FRONT}
        {DUCT_RIVER}
        {fonteBack(IDROMETRO, "river-back")}
        <g ref={legaNodo("rodRiver")} />
        <g ref={legaNodo("armRiver")}>
          <Arm fonte={IDROMETRO} />
        </g>
        {fonteFront(IDROMETRO, "river-front")}
        {DUCT_OUT}
        {GATE_BACK}
        <g ref={legaNodo("blade")}>
          <BladeArt />
        </g>
        <g ref={legaNodo("stemLow")} />
        {GATE_FRONT}
        <g ref={legaNodo("stemHigh")} />
        {DUCT_DOWN}
        {GAUGE_BACK}
        <path ref={legaNodo("needle")} className="iso-line manometro-ago" data-tone="lit" data-free="start" d={needleDi(riposo.punteggio)} />
        {GAUGE_FRONT}
      </svg>
      <span className="fig-alluvione-detto" aria-live="polite">
        {detto}
      </span>
    </div>
  );
}


function Arm({ fonte }: { fonte: typeof PLUVIOMETRO }) {
  return (
    <>
      <Solid paths={fonte.arm} tone="mid" crease="none" />
      <Solid paths={fonte.armTip} tone="hi" crease="lo" />
    </>
  );
}

function ShuttleArt() {
  return (
    <>
      <Solid paths={SHUTTLE} tone="hi" crease="lo" />
      <Line d={SHUTTLE_GRIP} tone="mid" />
    </>
  );
}

function BladeArt() {
  return <Solid paths={BLADE} tone="hi" crease="lo" inner={<Line d={BLADE_RIBS} tone="faint" />} />;
}
