import { useState } from "react";
import type maplibregl from "maplibre-gl";

const OVERLAYS = [
  { id: "wms-pai-layer", label: "PAI pericolosità frana" },
  { id: "wms-iffi-layer", label: "IFFI frane storiche" },
] as const;

export interface OverlayControlProps {
  readonly mapRef: { current: maplibregl.Map | null };
}

/** On-map toggles for the ISPRA WMS overlays served by GeoServer. */
export function OverlayControl(props: OverlayControlProps): JSX.Element {
  const [on, setOn] = useState<Record<string, boolean>>({});

  const toggle = (id: string): void => {
    const next = !on[id];
    setOn((prev) => ({ ...prev, [id]: next }));
    props.mapRef.current?.setLayoutProperty(
      id,
      "visibility",
      next ? "visible" : "none",
    );
  };

  return (
    <div className="overlay-control" role="group" aria-label="Overlay ISPRA">
      <span className="eyebrow" style={{ marginBottom: 4 }}>
        Overlay
      </span>
      {OVERLAYS.map((o) => (
        <label key={o.id}>
          <input
            type="checkbox"
            checked={on[o.id] ?? false}
            onChange={() => toggle(o.id)}
          />{" "}
          {o.label}
        </label>
      ))}
    </div>
  );
}

export default OverlayControl;
