import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Il tema della sala operativa (#155): fondo scuro a gradini, un solo
// accento arancio per ciò che si può premere. Sono gli stessi valori dei
// token in styles.css, espressi dove i componenti Mantine li leggono.
//
// **La scala del rischio resta fuori.** Le classi vivono in
// `risk-colors.ts` ed è l'unica cosa che la mappa e la colonna devono
// condividere byte per byte: passarla dentro al tema vorrebbe dire due
// sorgenti per lo stesso colore, e un tema che cambia cambierebbe il
// significato di una cella.

/** L'accento (#ff8a1f), nelle dieci tinte che Mantine si aspetta. */
const segnale: MantineColorsTuple = [
  "#fff3e6",
  "#ffe2c4",
  "#ffc690",
  "#ffa552",
  "#ff9433",
  "#ff8a1f",
  "#f07c10",
  "#cc6608",
  "#a35104",
  "#7a3c02",
];

/**
 * La scala `dark` di Mantine, dal testo al fondo: 0-2 testo, 4 bordi,
 * 5 rilievo, 6 pannello, 7 fondo. Mantine la usa per ogni superficie del
 * colour scheme scuro, quindi è qui che i componenti prendono i gradini.
 */
const fondo: MantineColorsTuple = [
  "#e6ecf2",
  "#c3ccd6",
  "#94a3b4",
  "#5b6878",
  "#1e2733",
  "#111821",
  "#0d1218",
  "#0a0e13",
  "#070a0e",
  "#040608",
];

export const theme = createTheme({
  primaryColor: "segnale",
  primaryShade: 5,
  colors: { segnale, dark: fondo },
  // Testo scuro sul bottone arancio: il bianco ci starebbe a 2,3:1.
  autoContrast: true,
  luminanceThreshold: 0.45,
  fontFamily: 'Archivo, system-ui, -apple-system, sans-serif',
  fontFamilyMonospace: 'IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, monospace',
  defaultRadius: "md",
  // I riquadri della colonna sono fitti: i default di Mantine sono pensati
  // per pagine larghe e qui sprecherebbero la metà dello spazio.
  spacing: { xs: "6px", sm: "10px", md: "14px", lg: "20px", xl: "28px" },
  headings: { fontWeight: "800" },
});
