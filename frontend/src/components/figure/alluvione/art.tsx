import { Dots, Line, Solid } from "../../iso/react/draw";
import type { Fonte } from "./geometry";
import { BASE, CONDOTTA_FIUME, CONDOTTA_PIOGGIA, CONDOTTA_USCITA, CONDOTTA_VALLE, GATE, GAUGE, LABEL, RULER, SECTORS, VALVE } from "./geometry";
import { RISK_COLOR_BY_LEVEL } from "../../../lib/risk-colors";

export const BASE_ART = (
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
    <Solid paths={RULER.strip} tone="lo" crease="none" />
    <Line d={RULER.minor} tone="lo" />
    <Line d={RULER.major} tone="mid" />
    <Solid paths={LABEL.plate} tone="lo" crease="none" />
    <Line d={LABEL.inset} tone="faint" />
    <Line d={LABEL.rules} tone="lo" free />
    <Dots points={LABEL.screws} size={0.45} />
  </g>
);

export function fonteBack(fonte: Fonte, key: string) {
  return (
    <g key={key}>
      <Solid paths={fonte.flange} tone="lo" />
      <Solid paths={fonte.body} tone="mid" inner={<Line d={fonte.seams} tone="faint" />} />
      {fonte.head.map((head, i) => (
        <Solid key={i} paths={head} tone="mid" />
      ))}
      <Line d={fonte.headLines} tone="lo" />
      <Dots points={fonte.headDots} size={0.42} tone="lo" />
    </g>
  );
}

export function fonteFront(fonte: Fonte, key: string) {
  return (
    <g key={key}>
      <Solid paths={fonte.staff} tone="mid" />
      <Line d={fonte.staffMinor} tone="lo" />
      <Line d={fonte.staffMajor} tone="hi" />
      <Solid paths={fonte.staffCap} tone="mid" />
    </g>
  );
}

function condotta(c: typeof CONDOTTA_PIOGGIA, key: string) {
  return (
    <g key={key}>
      <Solid paths={c.saddle} tone="lo" />
      <Solid paths={c.flanges[0]!} tone="mid" />
      <Solid paths={c.duct} tone="mid" />
      <Solid paths={c.flanges[1]!} tone="mid" />
      <Dots points={c.bolts} size={0.42} />
    </g>
  );
}

export const DUCT_RAIN = condotta(CONDOTTA_PIOGGIA, "duct-rain");
export const DUCT_RIVER = condotta(CONDOTTA_FIUME, "duct-river");
export const DUCT_OUT = condotta(CONDOTTA_USCITA, "duct-out");
export const DUCT_DOWN = condotta(CONDOTTA_VALLE, "duct-down");

export const VALVE_BACK = (
  <g key="valve-back">
    <Solid paths={VALVE.capLeft} tone="mid" />
    <Solid paths={VALVE.body} tone="hi" crease="lo" inner={<Line d={VALVE.bodySeam} tone="faint" />} />
    <path className="valvola-fessura" d={VALVE.slot} />
    <Line d={VALVE.slot} tone="lo" />
  </g>
);

export const VALVE_FRONT = (
  <g key="valve-front">
    <Dots points={VALVE.bolts} size={0.5} />
    <Solid paths={VALVE.capRight} tone="mid" />
    <Dots points={VALVE.capBolts} size={0.45} />
    <Solid paths={VALVE.outlet} tone="mid" />
  </g>
);

export const GATE_BACK = (
  <g key="gate-back">
    <Solid paths={GATE.sill} tone="lo" />
    <Solid paths={GATE.postLeft} tone="mid" />
  </g>
);

export const GATE_FRONT = (
  <g key="gate-front">
    <Solid paths={GATE.postRight} tone="mid" />
    <Solid paths={GATE.collar} tone="mid" />
    <Solid paths={GATE.beam} tone="mid" />
    <Dots points={GATE.beamBolts} size={0.45} />
    <Solid paths={GATE.wheel} tone="hi" crease="lo" />
    <Line d={GATE.wheelKnurl} tone="lo" />
    <Line d={GATE.wheelRim} tone="lo" />
    <Line d={GATE.wheelSpokes} tone="mid" />
    <Solid paths={GATE.hub} tone="mid" />
  </g>
);

export const GAUGE_BACK = (
  <g key="gauge-back">
    <path className="iso-halo" d={GAUGE.halo} />
    <Solid paths={GAUGE.pedestal} tone="mid" inner={<Line d={GAUGE.pedestalSeam} tone="faint" />} />
    <Solid paths={GAUGE.puck} tone="hi" crease="lo" inner={<Line d={GAUGE.bandSeam} tone="faint" />} />
    <Line d={GAUGE.band} tone="lo" />
    <Line d={GAUGE.bezel} tone="lo" />
    {SECTORS.map((sector) => (
      <path key={sector.level} className="iso-line manometro-settore" d={sector.d} style={{ stroke: RISK_COLOR_BY_LEVEL[sector.level] }} />
    ))}
    <Line d={GAUGE.ticks.minor} tone="lo" />
    <Line d={GAUGE.ticks.major} tone="mid" />
  </g>
);

export const GAUGE_FRONT = (
  <g key="gauge-front">
    <Line d={GAUGE.hubRing} tone="mid" />
    <Dots points={[GAUGE.hub]} size={0.6} tone="hi" />
    <Solid paths={GAUGE.crown} tone="mid" />
    <Solid paths={GAUGE.crownKnob} tone="mid" />
  </g>
);
