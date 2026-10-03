import { useRef } from "react";
import type { JSX } from "react";
import { Kbd, TextInput } from "@mantine/core";
import { useHotkeys } from "@mantine/hooks";

/** La ricerca del comune, nella barra in alto (#155).
 *
 *  Controllata: il testo filtra la lista dei comuni nella colonna, che è
 *  dove si vede il risultato; Invio porta la mappa sul primo trovato. ⌘K (o
 *  Ctrl+K) la raggiunge da qualunque punto della pagina. */
export function RicercaComune({
  valore,
  onCambia,
  onInvio,
}: {
  valore: string;
  onCambia: (v: string) => void;
  onInvio: (v: string) => void;
}): JSX.Element {
  const campo = useRef<HTMLInputElement | null>(null);
  useHotkeys([["mod+K", () => campo.current?.focus()]], []);
  return (
    <TextInput
      ref={campo}
      className="header-cerca"
      type="search"
      placeholder="Cerca un comune…"
      aria-label="Cerca un comune"
      value={valore}
      onChange={(e) => onCambia(e.currentTarget.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && valore.trim()) onInvio(valore.trim());
        if (e.key === "Escape") onCambia("");
      }}
      leftSection={
        <svg width={15} height={15} viewBox="0 0 24 24" fill="none" aria-hidden>
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
          <path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="2" />
        </svg>
      }
      rightSection={<Kbd size="xs">⌘K</Kbd>}
      rightSectionWidth={44}
      rightSectionPointerEvents="none"
    />
  );
}

export default RicercaComune;
