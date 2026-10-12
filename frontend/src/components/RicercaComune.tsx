import { useRef } from "react";
import type { JSX } from "react";
import { Kbd, TextInput } from "@mantine/core";
import { useHotkeys } from "@mantine/hooks";

import { testi, useTesti } from "../lib/i18n";

const T = testi(
  { placeholder: "Cerca un comune…", aria: "Cerca un comune" },
  { placeholder: "Search a municipality…", aria: "Search a municipality" },
);

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
  const t = useTesti(T);
  useHotkeys([["mod+K", () => campo.current?.focus()]], []);
  return (
    <TextInput
      ref={campo}
      className="header-cerca"
      type="search"
      placeholder={t.placeholder}
      aria-label={t.aria}
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
