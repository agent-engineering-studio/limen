import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { Dots, Line, Solid, Wire } from "../../iso/react/draw";
import { follow, useInView, useLoop, useReadout } from "../../iso/react/live";
import { COLORE_IGNOTO, RISK_COLOR_BY_LEVEL } from "../../../lib/risk-colors";
import {
  BASE,
  BOX,
  CAVO_A,
  CAVO_B_DIETRO,
  CENTRI,
  HEIGHT,
  PRESA_B,
  SPINA_A,
  SPINA_B,
  SPINA_CORSA,
  STRUMENTI,
  WIDTH,
  agoDi,
  bandieraDi,
  cavoBDavanti,
  shiftX,
} from "./geometry";
import type { Lettura } from "./model";
import { GIRO, letturaDi } from "./model";

const SEGUI = 0.35;
const PAUSA_DOPO_MANO = 5;
const PASSO = 0.05;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function giroA(t: number) {
  const totale = GIRO.reduce((s, passo) => s + passo.secondi, 0);
  let resto = t % totale;
  for (const passo of GIRO) {
    if (resto < passo.secondi) return passo;
    resto -= passo.secondi;
  }
  return GIRO[0]!;
}

interface Meta {
  a: number;
  b: number;
  bAttaccato: boolean;
}

interface Mostrato {
  a: number;
  b: number;
  // 0 = spina dentro e bandiera su, 1 = spina fuori e bandiera giù.
  stacco: number;
}

const metaDa = (passo: (typeof GIRO)[number]): Meta => ({ a: passo.a, b: passo.b ?? passo.a, bAttaccato: passo.b !== null });

const ARTE_BASE = (
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
    <Solid paths={BOX.body} tone="mid" inner={<Line d={BOX.seam} tone="faint" />} />
    <Line d={BOX.lid} tone="faint" />
    <Line d={BOX.ledRings} tone="lo" />
    <Dots points={BOX.screws} size={0.45} />
    <Solid paths={BOX.mastCollar} tone="mid" />
    <Solid paths={BOX.mast} tone="mid" crease="none" />
    <Solid paths={BOX.mastCap} tone="mid" />
    {BOX.sockets.map((socket, i) => (
      <Solid key={i} paths={socket} tone="mid" />
    ))}
  </g>
);

function quadrante(s: typeof STRUMENTI.a, key: string) {
  return (
    <g key={key}>
      <Solid paths={s.pedestal} tone="mid" inner={<Line d={s.pedestalSeam} tone="faint" />} />
      <Solid paths={s.puck} tone="hi" crease="lo" inner={<Line d={s.bandSeam} tone="faint" />} />
      <Line d={s.band} tone="lo" />
      <Line d={s.bezel} tone="lo" />
      {s.sectors.map((sector) => (
        <path key={sector.level} className="iso-line nm-settore" d={sector.d} style={{ stroke: RISK_COLOR_BY_LEVEL[sector.level] }} />
      ))}
      <Line d={s.ticks.minor} tone="lo" />
      <Line d={s.ticks.major} tone="mid" />
    </g>
  );
}

function cerniera(s: typeof STRUMENTI.a) {
  return (
    <>
      <Solid paths={s.posts[0]!} tone="mid" />
      <Solid paths={s.bar} tone="mid" />
      <Solid paths={s.posts[1]!} tone="mid" />
    </>
  );
}

interface Props {
  label: string;
  readoutOf: (a: Lettura, b: Lettura) => string;
  spokenOf: (b: Lettura) => string;
}

export function NonMisuratoLive({ label, readoutOf, spokenOf }: Props) {
  const { anchor, say } = useReadout<HTMLDivElement>();
  const stage = useRef<HTMLDivElement | null>(null);
  const inView = useInView(stage);
  const nodi = useRef<Record<string, SVGElement | null>>({});
  const primo = metaDa(GIRO[0]!);
  const meta = useRef<Meta>(primo);
  const ora = useRef<Mostrato>({ a: primo.a, b: primo.b, stacco: primo.bAttaccato ? 0 : 1 });
  const orologio = useRef(0);
  const mano = useRef(-Infinity);
  const [detto, setDetto] = useState("");

  const aggiorna = useCallback(
    (m: Mostrato, bAttaccato: boolean) => {
      const n = nodi.current;
      const giuA = 0;
      n.needleA?.setAttribute("d", agoDi(CENTRI.a, m.a));
      // Senza segnale l'ago di B torna a zero, come quello di una cella calma:
      // a dire la differenza resta solo la bandiera.
      const valoreB = m.b * (1 - m.stacco);
      n.needleB?.setAttribute("d", agoDi(CENTRI.b, valoreB));
      for (const [chiave, cx, giu] of [
        ["A", CENTRI.a, giuA],
        ["B", CENTRI.b, m.stacco],
      ] as const) {
        const { piastra, righe } = bandieraDi(cx, giu);
        n[`flag${chiave}`]?.setAttribute("d", piastra);
        n[`flagEdge${chiave}`]?.setAttribute("d", piastra);
        n[`flagRules${chiave}`]?.setAttribute("d", righe);
      }
      n.plugB?.setAttribute("transform", shiftX(SPINA_CORSA * m.stacco));
      const cavo = cavoBDavanti(SPINA_CORSA * m.stacco);
      n.cableB?.setAttribute("d", cavo.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(""));
      const fine = cavo[cavo.length - 1]!;
      n.cableBEnd?.setAttribute("cx", fine[0].toFixed(1));
      n.cableBEnd?.setAttribute("cy", fine[1].toFixed(1));
      n.ledB?.setAttribute("data-tone", m.stacco > 0.5 ? "faint" : "hi");
      const a = letturaDi({ segnale: m.a });
      const b = letturaDi({ segnale: bAttaccato ? m.b : null });
      say(readoutOf(a, b));
      const frase = spokenOf(b);
      setDetto((prima) => (prima === frase ? prima : frase));
    },
    [readoutOf, say, spokenOf],
  );

  useEffect(() => aggiorna(ora.current, meta.current.bAttaccato), [aggiorna]);

  const kick = useLoop((dt, calm) => {
    orologio.current += dt;
    if (!calm && orologio.current - mano.current > PAUSA_DOPO_MANO) meta.current = metaDa(giroA(orologio.current));
    const m = meta.current;
    const dopo: Mostrato = {
      a: follow(ora.current.a, m.a, dt, SEGUI, calm),
      b: follow(ora.current.b, m.b, dt, SEGUI, calm),
      stacco: follow(ora.current.stacco, m.bAttaccato ? 0 : 1, dt, SEGUI, calm),
    };
    ora.current = dopo;
    aggiorna(dopo, m.bAttaccato);
    return !calm || dopo.a !== m.a || dopo.b !== m.b || dopo.stacco !== (m.bAttaccato ? 0 : 1);
  }, inView);

  const tocca = useCallback(
    (cambia: (m: Meta) => Meta) => {
      mano.current = orologio.current;
      meta.current = cambia(meta.current);
      kick();
    },
    [kick],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") tocca((m) => ({ ...m, bAttaccato: !m.bAttaccato }));
    else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      const verso = event.key === "ArrowRight" ? PASSO : -PASSO;
      tocca((m) => ({ ...m, a: clamp(m.a + verso, 0, 1), b: clamp(m.b + verso, 0, 1) }));
    } else return;
    event.preventDefault();
  };

  const lega = (nome: string) => (el: SVGElement | null) => {
    nodi.current[nome] = el;
  };

  const flag = (chiave: "A" | "B") => (
    <g key={`flag${chiave}`}>
      <path ref={lega(`flag${chiave}`)} className="nm-bandiera" style={{ fill: COLORE_IGNOTO }} />
      <path ref={lega(`flagRules${chiave}`)} className="iso-line" data-tone="faint" />
      <path ref={lega(`flagEdge${chiave}`)} className="iso-line nm-bandiera-bordo" data-tone={chiave === "B" ? "lit" : "mid"} />
    </g>
  );

  return (
    <div
      ref={(el) => {
        stage.current = el;
        anchor.current = el;
      }}
      className="iso-stage fig-nm-stage"
      tabIndex={0}
      onClick={() => tocca((m) => ({ ...m, bAttaccato: !m.bAttaccato }))}
      onKeyDown={onKeyDown}
    >
      <svg className="iso-svg" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={label} focusable="false">
        {ARTE_BASE}
        <circle className="nm-led" cx={BOX.leds.a[0]} cy={BOX.leds.a[1]} r={0.9} data-tone="hi" />
        <circle ref={lega("ledB")} className="nm-led" cx={BOX.leds.b[0]} cy={BOX.leds.b[1]} r={0.9} data-tone="hi" />
        <Wire from={CAVO_B_DIETRO[0]!} to={CAVO_B_DIETRO[CAVO_B_DIETRO.length - 1]!} via={CAVO_B_DIETRO.slice(1, -1)} tone="mid" ends="from" />
        {quadrante(STRUMENTI.a, "gauge-a")}
        <path ref={lega("needleA")} className="iso-line nm-ago" data-tone="hi" data-free="start" />
        <Dots points={[STRUMENTI.a.hub]} size={0.6} tone="hi" />
        {cerniera(STRUMENTI.a)}
        {flag("A")}
        <Wire from={CAVO_A[0]!} to={CAVO_A[CAVO_A.length - 1]!} via={CAVO_A.slice(1, -1)} tone="mid" />
        <Solid paths={SPINA_A} tone="mid" />
        {quadrante(STRUMENTI.b, "gauge-b")}
        <path ref={lega("needleB")} className="iso-line nm-ago" data-tone="hi" data-free="start" />
        <Dots points={[STRUMENTI.b.hub]} size={0.6} tone="hi" />
        {cerniera(STRUMENTI.b)}
        {flag("B")}
        <path className="nm-presa" d={PRESA_B} />
        <g className="iso-wire" data-tone="mid">
          <path ref={lega("cableB")} className="iso-line" data-tone="mid" />
          <circle ref={lega("cableBEnd")} className="iso-wire-end" r={1.2} />
        </g>
        <g ref={lega("plugB")}>
          <Solid paths={SPINA_B} tone="mid" />
        </g>
      </svg>
      <span className="fig-detto" aria-live="polite">
        {detto}
      </span>
    </div>
  );
}
