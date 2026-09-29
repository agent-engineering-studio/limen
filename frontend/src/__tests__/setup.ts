import "@testing-library/jest-dom/vitest";

// MapLibre GL JS requires WebGL + a DOM canvas; jsdom doesn't provide
// them. Tests that exercise <RiskMap /> mock the constructor explicitly,
// but a global stub keeps unrelated imports from crashing on load.
import { vi } from "vitest";

vi.mock("maplibre-gl", () => {
  class FakeMap {
    on() {
      return this;
    }
    off() {
      return this;
    }
    addSource() {}
    addLayer() {}
    addControl() {
      return this;
    }
    removeControl() {
      return this;
    }
    setStyle() {}
    fitBounds() {}
    flyTo() {}
    getCanvas() {
      return document.createElement("canvas");
    }
    remove() {}
    setLayoutProperty() {}
    setPaintProperty() {}
  }
  return {
    default: { Map: FakeMap, NavigationControl: class {}, Popup: class {} },
    Map: FakeMap,
    NavigationControl: class {},
    Popup: class {},
  };
});

// jsdom non implementa `matchMedia` né `ResizeObserver`, e Mantine li usa
// entrambi: il provider interroga lo schema di colori del sistema, e i
// componenti che misurano lo spazio osservano il proprio contenitore. Senza
// questi due, il provider non monta e ogni componente figlio riporta
// «MantineProvider was not found» — un messaggio che manda a cercare nel
// posto sbagliato.
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

if (!("ResizeObserver" in window)) {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
}
