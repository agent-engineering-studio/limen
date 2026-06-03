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
