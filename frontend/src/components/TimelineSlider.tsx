import { useState } from "react";

export interface TimelineSliderProps {
  /** Maximum hours of history the slider covers (default 24). */
  readonly maxHours?: number;
  /** Called with the selected hour offset (0 = now). */
  readonly onChange?: (hoursAgo: number) => void;
}

/**
 * Hour-resolution slider that scrubs the recent history of the
 * deterministic engine. V1 only refetches the latest assessment (the
 * matview is a single snapshot); a hooked-up time-travel reader will
 * arrive when `risk_assessments` indexing for time queries is in
 * place. Hide by default unless `VITE_ENABLE_TIMELINE=true`.
 */
export function TimelineSlider(props: TimelineSliderProps): JSX.Element {
  const maxHours = props.maxHours ?? 24;
  const onChange = props.onChange;
  const [hoursAgo, setHoursAgo] = useState(0);

  return (
    <section className="legend-panel" aria-label="Linea temporale">
      <h2>Linea temporale</h2>
      <label htmlFor="timeline-slider" style={{ fontSize: 12 }}>
        {hoursAgo === 0
          ? "Stato corrente"
          : `${hoursAgo} ore fa`}
      </label>
      <input
        id="timeline-slider"
        type="range"
        min={0}
        max={maxHours}
        step={1}
        value={hoursAgo}
        onChange={(e) => {
          const next = Number(e.currentTarget.value);
          setHoursAgo(next);
          onChange?.(next);
        }}
        style={{ width: "100%" }}
      />
    </section>
  );
}

export default TimelineSlider;
