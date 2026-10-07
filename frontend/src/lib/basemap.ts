// Lo sfondo cartografico della sala operativa, condiviso fra le mappe.
//
// La sala è scura (#155) e le tile OSM sono chiare: le si inverte in pittura.
// Con `brightness-min` sopra `max` il bianco della carta va al fondo e le
// strade escono chiare; desaturate, perché il colore della mappa deve restare
// quello del rischio. L'inversione porta l'azzurro del mare al marrone: mezzo
// giro di tinta lo riporta freddo.

export const BASEMAP_SOURCE = {
  type: "raster" as const,
  tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
  tileSize: 256,
  attribution: "© OpenStreetMap contributors",
};

export const BASEMAP_LAYER = {
  id: "osm",
  type: "raster" as const,
  source: "osm",
  paint: {
    "raster-brightness-min": 0.5,
    "raster-brightness-max": 0.05,
    "raster-saturation": -0.85,
    "raster-hue-rotate": 180,
    "raster-contrast": 0.1,
  },
};
