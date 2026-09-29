import type { ReactElement } from "react";
import { MantineProvider } from "@mantine/core";
import { render as renderBase, type RenderOptions } from "@testing-library/react";

import { theme } from "./lib/theme";

/**
 * `render` con il provider di Mantine intorno.
 *
 * I componenti Mantine leggono il tema da un contesto e senza provider
 * lanciano — quindi un test che monta un componente migrato deve passare da
 * qui. Il tema è quello vero, non uno finto: un test che passa con colori
 * diversi da quelli in pagina non dice niente sulla pagina.
 */
export function render(ui: ReactElement, options?: RenderOptions) {
  return renderBase(ui, {
    wrapper: ({ children }) => (
      <MantineProvider theme={theme} defaultColorScheme="light">
        {children}
      </MantineProvider>
    ),
    ...options,
  });
}

// Esportazioni elencate e non `export *`: la stella ri-esporta anche
// `render`, e con il nostro omonimo accanto il test finiva per prendere
// quello di testing-library — cioè senza provider, che è esattamente il
// guasto che questo file esiste per evitare.
export { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
