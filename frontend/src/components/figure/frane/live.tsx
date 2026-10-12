import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent, ReactNode } from "react";

import { Dots, Line, Solid } from "../../iso/react/draw";
import { follow, useInView, useLoop, useReadout } from "../../iso/react/live";
import { iso } from "../../iso/iso-kit";
import { RISK_COLOR_BY_LEVEL } from "../../../lib/risk-colors";
import { BASE, CARRELLI, CORSA, HEIGHT, LIVELLI, P, POINTER, RAIL, SCALE, WIDTH, shift } from "./geometry";
import type { Componente, Stato, Valori } from "./model";
import { COMPONENTI, GIRO, RIPOSO, statoDi } from "./model";

const SEGUI = 0.4;
const PAUSA_DOPO_MANO = 4;
const PASSO = 0.05;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function giroA(t: number): Valori {
  const totale = GIRO.reduce((s, passo) => s + passo.secondi, 0);
  let resto = t % totale;
  for (const passo of GIRO) {
    if (resto < passo.secondi) return passo;
    resto -= passo.secondi;
  }
  return RIPOSO;
}

// Lo spostamento di ogni carrello è la somma delle corse dei carrelli sotto di lui.
function spostamenti(valori: Valori): number[] {
  let somma = 0;
  return COMPONENTI.map((c) => (somma += CORSA[c] * valori[c]));
}

const BASE_ART = (
  <g key="base">
    <path className="iso-halo" d={BASE.halo} />
    {BASE.feet.map((foot, i) => (
      <g key={i}>
        <Solid paths={foot.flange} tone="lo" crease="none" />
        <Solid paths={foot.foot} tone="mid" crease="none" />
      </g>
    ))}
    <Solid paths={BASE.slab} tone="mid" inner={<Line d={BASE.seam} tone="faint" />} />
    <Line d={BASE.groove} tone="lo" />
    <Line d={BASE.screws} tone="lo" />
    <Dots points={BASE.screwDots} size={0.5} />
    <Solid paths={BASE.label} tone="lo" crease="none" />
    <Line d={BASE.labelInset} tone="faint" />
    <Line d={BASE.labelRules} tone="lo" free />
    <Dots points={BASE.labelScrews} size={0.45} />
    <Solid paths={SCALE.strip} tone="lo" crease="none" />
    {SCALE.bands.map((band) => (
      <path key={band.level} className="frane-fascia" d={band.d} style={{ fill: RISK_COLOR_BY_LEVEL[band.level] }} />
    ))}
    <Line d={SCALE.minor} tone="lo" />
    <Line d={SCALE.major} tone="mid" />
    <Solid paths={RAIL.body} tone="mid" inner={<Line d={RAIL.seam} tone="faint" />} />
    <Line d={RAIL.groove} tone="faint" />
    <Line d={RAIL.ticksMinor} tone="lo" />
    <Line d={RAIL.ticksMajor} tone="mid" />
    <Solid paths={RAIL.stopLeft} tone="mid" />
  </g>
);

const RAIL_RIGHT = (
  <g key="rail-right">
    <Solid paths={RAIL.stopRight} tone="mid" />
    <Dots points={RAIL.stopDots} size={0.45} />
  </g>
);

function corpo(i: number): ReactNode {
  const l = LIVELLI[i]!;
  return (
    <>
      <Solid paths={l.body} tone={i === 4 ? "hi" : "mid"} crease={i === 4 ? "lo" : "faint"} inner={<Line d={l.seam} tone="faint" />} />
      {l.groove ? <Line d={l.groove} tone="faint" /> : null}
      <Line d={l.ticksMinor} tone="lo" />
      <Line d={l.ticksMajor} tone="mid" />
      {i < 4 ? <Solid paths={l.stopLeft} tone="mid" /> : null}
      <Dots points={l.screws} size={0.42} />
    </>
  );
}

function coda(i: number): ReactNode {
  const l = LIVELLI[i]!;
  return (
    <>
      {i < 4 ? <Solid paths={l.stopRight} tone="mid" /> : null}
      <Dots points={l.stopDots} size={0.45} />
      <Solid paths={l.knob} tone="hi" crease="lo" />
      <Line d={l.knobKnurl} tone="lo" />
      <Line d={l.knobMark} tone="hi" />
    </>
  );
}

interface Props {
  label: string;
  readoutOf: (s: Stato) => string;
  spokenOf: (s: Stato, scelta: Componente) => string;
}

export function FraneLive({ label, readoutOf, spokenOf }: Props) {
  const { anchor, say } = useReadout<HTMLDivElement>();
  const stage = useRef<HTMLDivElement | null>(null);
  const svg = useRef<SVGSVGElement | null>(null);
  const inView = useInView(stage);
  const gruppi = useRef<(SVGGElement | null)[][]>(COMPONENTI.map(() => []));
  const ora = useRef<Valori>({ ...RIPOSO });
  const meta = useRef<Valori>({ ...RIPOSO });
  const orologio = useRef(0);
  const mano = useRef(-Infinity);
  const [scelta, setScelta] = useState<Componente>("m");
  const sceltaRef = useRef<Componente>("m");
  const [detto, setDetto] = useState("");

  const aggiorna = useCallback(
    (valori: Valori) => {
      const d = spostamenti(valori);
      gruppi.current.forEach((nodi, i) => nodi.forEach((n) => n?.setAttribute("transform", shift(d[i]!))));
      const s = statoDi(valori);
      say(readoutOf(s));
      const frase = spokenOf(s, sceltaRef.current);
      setDetto((prima) => (prima === frase ? prima : frase));
    },
    [readoutOf, say, spokenOf],
  );

  useEffect(() => aggiorna(ora.current), [aggiorna]);

  const kick = useLoop((dt, calm) => {
    orologio.current += dt;
    if (!calm && orologio.current - mano.current > PAUSA_DOPO_MANO) meta.current = { ...giroA(orologio.current) };
    const dopo = Object.fromEntries(COMPONENTI.map((c) => [c, follow(ora.current[c], meta.current[c], dt, SEGUI, calm)])) as Valori;
    ora.current = dopo;
    aggiorna(dopo);
    return !calm || COMPONENTI.some((c) => dopo[c] !== meta.current[c]);
  }, inView);

  const imposta = useCallback(
    (c: Componente, valore: number) => {
      mano.current = orologio.current;
      meta.current = { ...meta.current, [c]: clamp(valore, 0, 1) };
      kick();
    },
    [kick],
  );

  const scegli = (c: Componente) => {
    sceltaRef.current = c;
    setScelta(c);
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const box = svg.current?.getBoundingClientRect();
    if (!box || box.width === 0) return;
    const x = ((event.clientX - box.left) / box.width) * WIDTH;
    const y = ((event.clientY - box.top) / box.height) * HEIGHT;
    // La parte più vicina è il livello alla stessa altezza sullo schermo.
    const d = spostamenti(ora.current);
    let vicino: Componente = "m";
    let distanza = Infinity;
    CARRELLI.forEach((carrello, i) => {
      const [, ay] = iso([carrello.plan.x + carrello.plan.w / 2 + d[i]!, 0, carrello.z + 3], P);
      if (Math.abs(ay - y) < distanza) {
        distanza = Math.abs(ay - y);
        vicino = carrello.componente;
      }
    });
    scegli(vicino);
    imposta(vicino, (x - WIDTH * 0.2) / (WIDTH * 0.6));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const i = COMPONENTI.indexOf(scelta);
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      scegli(COMPONENTI[clamp(i + (event.key === "ArrowUp" ? 1 : -1), 0, COMPONENTI.length - 1)]!);
      mano.current = orologio.current;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      imposta(scelta, meta.current[scelta] + (event.key === "ArrowRight" ? PASSO : -PASSO));
    } else return;
    event.preventDefault();
  };

  const lega = (i: number, j: number) => (el: SVGGElement | null) => {
    gruppi.current[i]![j] = el;
  };

  return (
    <div
      ref={(el) => {
        stage.current = el;
        anchor.current = el;
      }}
      className="iso-stage fig-frane-stage"
      tabIndex={0}
      onPointerMove={onPointerMove}
      onKeyDown={onKeyDown}
      data-scelta={scelta}
    >
      <svg ref={svg} className="iso-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label} focusable="false">
        {BASE_ART}
        <g ref={lega(0, 0)}>{corpo(0)}</g>
        {RAIL_RIGHT}
        <g ref={lega(1, 0)}>{corpo(1)}</g>
        <g ref={lega(0, 1)}>{coda(0)}</g>
        <g ref={lega(2, 0)}>{corpo(2)}</g>
        <g ref={lega(1, 1)}>{coda(1)}</g>
        <g ref={lega(3, 0)}>{corpo(3)}</g>
        <g ref={lega(2, 1)}>{coda(2)}</g>
        <g ref={lega(4, 0)}>
          {corpo(4)}
          {coda(4)}
          <Solid paths={POINTER.arm} tone="mid" />
        </g>
        <g ref={lega(3, 1)}>{coda(3)}</g>
        <g ref={lega(4, 1)}>
          <Solid paths={POINTER.drop} tone="mid" />
          <Line d={POINTER.tip} tone="lit" className="frane-indice" />
        </g>
      </svg>
      <span className="fig-detto" aria-live="polite">
        {detto}
      </span>
    </div>
  );
}
