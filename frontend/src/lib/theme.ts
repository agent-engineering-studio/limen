import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Il tema Mantine eredita i colori che il progetto aveva già: non è una
// ri-tintura, è la stessa tavolozza espressa dove i componenti la leggono.
//
// **La scala del rischio resta fuori.** Il giallo-rosso delle classi vive in
// `risk-colors.ts` ed è l'unica cosa che la mappa e la colonna devono
// condividere byte per byte: passarla dentro al tema vorrebbe dire due
// sorgenti per lo stesso colore, e un tema che cambia cambierebbe il
// significato di una cella.

/** L'accento del progetto (#2456a3), nelle dieci tinte che Mantine si aspetta. */
const accento: MantineColorsTuple = [
  "#eef3fb",
  "#dae4f4",
  "#b2c6e8",
  "#87a6dc",
  "#638cd2",
  "#4d7ccc",
  "#4074ca",
  "#3163b3",
  "#2456a3",
  "#123f83",
];

export const theme = createTheme({
  primaryColor: "limen",
  colors: { limen: accento },
  fontFamily: 'Archivo, system-ui, -apple-system, sans-serif',
  fontFamilyMonospace: 'IBM Plex Mono, ui-monospace, SFMono-Regular, Menlo, monospace',
  defaultRadius: "md",
  // I riquadri della colonna sono fitti: i default di Mantine sono pensati
  // per pagine larghe e qui sprecherebbero la metà dello spazio.
  spacing: { xs: "6px", sm: "10px", md: "14px", lg: "20px", xl: "28px" },
  headings: { fontWeight: "650" },
});
