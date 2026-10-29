import type { JSX, ReactNode } from "react";
import { SegmentedControl, Tooltip } from "@mantine/core";

import { testi, useLingua, useTesti } from "../lib/i18n";
import { useMapState, type Vista } from "../lib/map-state";
import { motivoSenza3d, useMotivoSenzaRilievo } from "../lib/rilievo";

const T = testi(
  { gruppo: "Vista della mappa", rilievo: "Rilievo" },
  { gruppo: "Map view", rilievo: "Relief" },
);

/** Una voce spenta dice perché, a chi passa sopra e a chi usa un lettore di
 *  schermo: il motivo sta nel nome stesso del pulsante, non solo nel tooltip. */
function Voce({ testo, motivo }: { testo: string; motivo: string | null }): ReactNode {
  if (!motivo) return testo;
  return (
    <Tooltip label={motivo} multiline w={260} withinPortal={false}>
      <span>
        {testo}
        <span className="sr-only"> — {motivo}</span>
      </span>
    </Tooltip>
  );
}

/** `[ 2D | Rilievo | 3D ]` sopra la mappa (#319). Scrive `vista` nello stato
 *  condiviso, e da lì nell'URL. */
export function SelettoreVista(): JSX.Element {
  const { vista, impostaVista } = useMapState();
  const { lingua } = useLingua();
  const t = useTesti(T);
  const motivoRilievo = useMotivoSenzaRilievo();
  const motivo3d = motivoSenza3d(lingua);
  // Un link a una vista che qui non c'è mostra la mappa piatta, e il
  // selettore deve dire quella, non la vista chiesta.
  const mostrata: Vista = vista === "rilievo" && !motivoRilievo ? "rilievo" : "2d";
  return (
    <SegmentedControl
      className="map-vista"
      aria-label={t.gruppo}
      size="xs"
      value={mostrata}
      onChange={(v) => impostaVista(v as Vista)}
      data={[
        { value: "2d", label: "2D" },
        {
          value: "rilievo",
          label: <Voce testo={t.rilievo} motivo={motivoRilievo} />,
          disabled: motivoRilievo !== null,
        },
        { value: "3d", label: <Voce testo="3D" motivo={motivo3d} />, disabled: true },
      ]}
    />
  );
}

export default SelettoreVista;
