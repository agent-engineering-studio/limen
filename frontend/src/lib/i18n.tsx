import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { JSX, ReactNode } from "react";

/**
 * Le due lingue del sito.
 *
 * I testi stanno accanto al componente che li usa, in coppia: `testi(it, en)`
 * li dichiara e `useTesti` restituisce quelli della lingua attiva. Il tipo di
 * `en` è quello di `it`, quindi una voce dimenticata nella traduzione è un
 * errore di compilazione e non una stringa italiana in mezzo all'inglese.
 *
 * Il default è l'italiano: un componente montato senza provider — nei test,
 * per esempio — parla come ha sempre parlato.
 */
export type Lingua = "it" | "en";

export const LINGUE: readonly Lingua[] = ["it", "en"];

const CHIAVE = "limen.lingua";

/** La lingua con cui aprire la pagina: `?lang=` nel link, poi la scelta
 *  ricordata, poi quella del browser (inglese se non è italiano). */
export function linguaIniziale(): Lingua {
  const daLink = parametroLang(window.location.search) ?? parametroLang(queryDelHash());
  if (daLink) return daLink;
  try {
    const salvata = window.localStorage.getItem(CHIAVE);
    if (salvata === "it" || salvata === "en") return salvata;
  } catch {
    // Storage bloccato (navigazione privata, iframe): si va sul browser.
  }
  const preferite = navigator.languages?.length ? navigator.languages : [navigator.language];
  return preferite.some((l) => l?.toLowerCase().startsWith("it")) ? "it" : "en";
}

function queryDelHash(): string {
  const i = window.location.hash.indexOf("?");
  return i >= 0 ? window.location.hash.slice(i) : "";
}

function parametroLang(query: string): Lingua | null {
  const v = new URLSearchParams(query).get("lang");
  return v === "it" || v === "en" ? v : null;
}

interface StatoLingua {
  lingua: Lingua;
  imposta: (l: Lingua) => void;
}

const ContestoLingua = createContext<StatoLingua>({ lingua: "it", imposta: () => {} });

export function LinguaProvider({
  children,
  iniziale,
}: {
  children: ReactNode;
  iniziale?: Lingua;
}): JSX.Element {
  const [lingua, setLingua] = useState<Lingua>(() => iniziale ?? linguaIniziale());
  const imposta = useCallback((l: Lingua) => {
    setLingua(l);
    try {
      window.localStorage.setItem(CHIAVE, l);
    } catch {
      // Senza storage la scelta vale per la sessione: va bene lo stesso.
    }
  }, []);
  useEffect(() => {
    document.documentElement.lang = lingua;
  }, [lingua]);
  const valore = useMemo(() => ({ lingua, imposta }), [lingua, imposta]);
  return <ContestoLingua.Provider value={valore}>{children}</ContestoLingua.Provider>;
}

export function useLingua(): StatoLingua {
  return useContext(ContestoLingua);
}

/** Dichiara i testi di un componente nelle due lingue. */
export function testi<T>(it: T, en: NoInfer<T>): Record<Lingua, T> {
  return { it, en };
}

/** I testi del componente nella lingua attiva. */
export function useTesti<T>(t: Record<Lingua, T>): T {
  return t[useLingua().lingua];
}

/** La locale di `Intl` per la lingua: date e numeri all'italiana o
 *  all'inglese (britannico: giorno prima del mese, 24 ore, come in Europa). */
export function locale(lingua: Lingua): string {
  return lingua === "it" ? "it-IT" : "en-GB";
}

/** La locale della lingua attiva, per `toLocaleString` e `Intl.*`. */
export function useLocale(): string {
  return locale(useLingua().lingua);
}
