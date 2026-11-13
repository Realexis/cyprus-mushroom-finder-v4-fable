// Our data layers on top of the basemap.
import type { ExpressionSpecification, FilterSpecification, Map as MlMap } from "maplibre-gl";
import type { Theme } from "./style";

export type Mode = "conditions" | "rain7" | "rain30" | "replay" | "soilw" | "soilph";
export const isRain = (m: Mode) => m === "rain7" || m === "rain30" || m === "replay";
export const isSoil = (m: Mode) => m === "soilw" || m === "soilph";

/** What the map is coloured for: the general map or one species' habitat. */
export interface Filter {
  code: string | null;               // null = general map
  trees: number[]; bands: number[];  // species habitat (private 250 m cells)
  inSeason: boolean;                 // species season window on the chosen day
  seasonShare: number;               // points the season factor is worth (species: full)
  engine: boolean;                   // v0.3: squares are coloured from score files (feature-state "v"), never grey
}

export interface View { day: number; mode: Mode; priv: boolean; filter: Filter; replayIndex: number; }

// Score colours: calm at the low end, warm glow at the top (same as the previews).
export const SCORE_STOPS: [number, string][] = [
  [0, "#23413f"], [30, "#3e6b57"], [50, "#7e9f55"], [70, "#d9b44a"], [85, "#ee8e4a"], [100, "#ff6a4d"],
];
export const RAIN7_STOPS: [number, string][] = [[0, "#d9e8f2"], [10, "#9cc9e8"], [25, "#4f97d1"], [50, "#2a5fae"], [80, "#1b2f7a"]];
export const RAIN30_STOPS: [number, string][] = [[0, "#d9e8f2"], [20, "#9cc9e8"], [50, "#4f97d1"], [80, "#2a5fae"], [120, "#1b2f7a"]];
export const RAIN1_STOPS: [number, string][] = [[0, "rgba(217,232,242,0)"], [0.5, "#cfe3f0"], [3, "#9cc9e8"], [8, "#4f97d1"], [15, "#2a5fae"], [30, "#1b2f7a"]];
// Shade (50 m hotspot zoom): sunny = pale sand, deep shade = deep teal.
export const SHADE_STOPS: [number, string][] = [[0, "#f1e3b5"], [35, "#b9c98f"], [55, "#5f9e86"], [75, "#2f6f78"], [100, "#183a5a"]];
const OUT_OF_SEASON = "#8c928f";
/** Draw the ~2 km top-zone hexagons on the map? Off: people read them as "mushrooms here". */
const SHOW_ZONE_OUTLINES = false;
// Soil views (v0.3): water held in the top 30 cm (mm) and soil pH. Estimates from SoilGrids.
export const SOILW_STOPS: [number, string][] = [[15, "#efe0b4"], [22, "#c9d98f"], [27, "#7fbf8e"], [32, "#3f9a8a"], [40, "#1d5f7a"]];   // Cyprus forest soils: p10 20 mm, p90 34 mm
export const SOILPH_STOPS: [number, string][] = [[5.0, "#d7642c"], [6.0, "#ebb76c"], [7.0, "#f2ede0"], [7.6, "#a9a9dc"], [8.3, "#5e56a8"]];
function soilColor(v: View): ExpressionSpecification {
  return v.mode === "soilph" ? ramp(["/", ["to-number", ["get", "ph"], 70], 10], SOILPH_STOPS)
    : ramp(["to-number", ["get", "awc"], 0], SOILW_STOPS);
}

function ramp(prop: ExpressionSpecification, stops: [number, string][]): ExpressionSpecification {
  return ["interpolate", ["linear"], prop, ...stops.flat()] as unknown as ExpressionSpecification;
}

/** Property holding the hexagon score for this day and filter. */
export const hexProp = (day: number, f: Filter) => (f.code ? `${f.code}${day}` : `s${day}`);

function hexColor(v: View): ExpressionSpecification | string {
  if (v.filter.code && !v.filter.inSeason && !v.filter.engine) return OUT_OF_SEASON;
  return ramp(["to-number", ["get", hexProp(v.day, v.filter)], 0], SCORE_STOPS);
}

function hexFilter(v: View): FilterSpecification {
  return ["has", hexProp(v.day, v.filter)];
}

function cellColor(v: View): ExpressionSpecification | string {
  if (v.filter.engine) {                // v0.3: the score file for this species / general map, via feature-state
    return ["case", ["==", ["feature-state", "v"], null], "rgba(0,0,0,0)",
      ramp(["to-number", ["feature-state", "v"], 0], SCORE_STOPS)] as unknown as ExpressionSpecification;
  }
  if (!v.filter.code) return ramp(["to-number", ["get", `s${v.day}`], 0], SCORE_STOPS);
  if (!v.filter.inSeason) return OUT_OF_SEASON;
  return ramp(["+", ["to-number", ["get", `b${v.day}`], 0], v.filter.seasonShare], SCORE_STOPS);
}

function cellFilter(v: View): FilterSpecification {
  if (v.filter.engine) return ["==", ["get", "closed"], 0];
  if (!v.filter.code) return ["all", ["==", ["get", "closed"], 0], ["==", ["get", "g"], 1]];
  return ["all", ["==", ["get", "closed"], 0],
    ["in", ["get", "tree"], ["literal", v.filter.trees]],
    ["in", ["get", "band"], ["literal", v.filter.bands]]];
}

function rainColor(v: View): ExpressionSpecification {
  if (v.mode === "replay") return ramp(["to-number", ["at", v.replayIndex, ["get", "d"]], 0], RAIN1_STOPS);
  return v.mode === "rain30" ? ramp(["get", "r30"], RAIN30_STOPS) : ramp(["get", "r7"], RAIN7_STOPS);
}

function hatch(theme: Theme): ImageData {
  const s = 16, c = document.createElement("canvas");
  c.width = c.height = s;
  const g = c.getContext("2d")!;
  g.fillStyle = theme === "dark" ? "rgba(140,146,143,0.30)" : "rgba(120,126,123,0.25)";
  g.fillRect(0, 0, s, s);
  g.strokeStyle = theme === "dark" ? "rgba(214,219,216,0.85)" : "rgba(70,76,73,0.85)";
  g.lineWidth = 2;
  for (const o of [-s, 0, s]) { g.beginPath(); g.moveTo(o, s); g.lineTo(o + s, 0); g.stroke(); }
  return g.getImageData(0, 0, s, s);
}

export interface LayerUrls {
  terrain: string; hexes: string; rain: string; reserves: string;
  cells?: string; hotspots?: string; hotspotZones?: GeoJSON.FeatureCollection;
}

export function addOverlays(map: MlMap, theme: Theme, urls: LayerUrls, v: View) {
  const firstSymbol = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  if (!map.hasImage("hatch")) map.addImage("hatch", hatch(theme));
  const dem = { type: "raster-dem" as const, url: `pmtiles://${urls.terrain}`, encoding: "terrarium" as const,
    tileSize: 256, attribution: "Copernicus DEM © DLR e.V., © Airbus" };

  // Two sources on the same tiles: MapLibre recommends one for hillshade, one for 3D.
  map.addSource("terrain", dem);
  const { attribution: _credit, ...dem3d } = dem;      // credit is shown once, by the hillshade source
  map.addSource("terrain3d", dem3d);
  map.addLayer({
    id: "hillshade", type: "hillshade", source: "terrain",
    paint: {
      "hillshade-exaggeration": theme === "dark" ? 0.55 : 0.45,
      "hillshade-shadow-color": theme === "dark" ? "#050a08" : "#5b5340",
      "hillshade-highlight-color": theme === "dark" ? "#3a4a41" : "#ffffff",
      "hillshade-accent-color": theme === "dark" ? "#0c1612" : "#8a8270",
    },
  }, firstSymbol);

  map.addSource("rain", { type: "geojson", data: urls.rain, attribution: "Weather: Open-Meteo.com (CC BY 4.0)" });
  map.addLayer({
    id: "rain-fill", type: "fill", source: "rain",
    layout: { visibility: isRain(v.mode) ? "visible" : "none" },
    paint: { "fill-color": rainColor(v), "fill-opacity": 0.72, "fill-antialias": false },
  }, firstSymbol);

  map.addSource("hexes", { type: "geojson", data: urls.hexes, generateId: true,
    attribution: "Copernicus Land Monitoring Service · EEA" });
  map.addLayer({
    id: "hex-fill", type: "fill", source: "hexes", filter: hexFilter(v),
    layout: { visibility: v.mode === "conditions" && !v.priv ? "visible" : "none" },
    paint: { "fill-color": hexColor(v), "fill-opacity": 0.78 },
  }, firstSymbol);
  map.addLayer({
    id: "hex-line", type: "line", source: "hexes", filter: hexFilter(v),
    layout: { visibility: v.mode === "conditions" && !v.priv ? "visible" : "none" },
    paint: { "line-color": theme === "dark" ? "#0c1612" : "#f3f0e7", "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.3, 12, 1.2], "line-opacity": 0.7 },
  }, firstSymbol);
  // The tapped zone: a wide contrasting halo with a bright core, readable at every zoom.
  const SEL_HALO = theme === "dark" ? "#0c1612" : "#ffffff";
  const SEL_CORE = theme === "dark" ? "#ffffff" : "#1b2620";
  const selW = (a: number, b: number) => ["interpolate", ["linear"], ["zoom"], 7, a, 12, b] as unknown as ExpressionSpecification;
  map.addLayer({ id: "hex-selected-halo", type: "line", source: "hexes", filter: ["==", ["id"], -1],
    paint: { "line-color": SEL_HALO, "line-width": selW(7, 10), "line-opacity": 0.9 } }, firstSymbol);
  map.addLayer({ id: "hex-selected", type: "line", source: "hexes", filter: ["==", ["id"], -1],
    paint: { "line-color": SEL_CORE, "line-width": selW(3, 4.5) } }, firstSymbol);

  if (urls.cells) {
    map.addSource("cells", { type: "vector", url: `pmtiles://${urls.cells}`, promoteId: "i",
      attribution: "Copernicus Land Monitoring Service · EEA" });
    map.addLayer({
      id: "cells-fill", type: "fill", source: "cells", "source-layer": "cells", filter: cellFilter(v),
      layout: { visibility: v.mode === "conditions" && v.priv ? "visible" : "none" },
      paint: { "fill-color": cellColor(v), "fill-opacity": 0.72, "fill-antialias": false },
    }, firstSymbol);
    map.addLayer({
      id: "soil-fill", type: "fill", source: "cells", "source-layer": "cells",
      filter: ["all", ["==", ["get", "closed"], 0], ["has", "awc"]],
      layout: { visibility: isSoil(v.mode) ? "visible" : "none" },
      paint: { "fill-color": soilColor(v), "fill-opacity": 0.85, "fill-antialias": false },
    }, firstSymbol);
    map.addLayer({ id: "cells-selected-halo", type: "line", source: "cells", "source-layer": "cells",
      filter: ["==", ["get", "i"], -1], paint: { "line-color": SEL_HALO, "line-width": selW(5, 8) } }, firstSymbol);
    map.addLayer({ id: "cells-selected", type: "line", source: "cells", "source-layer": "cells",
      filter: ["==", ["get", "i"], -1], paint: { "line-color": SEL_CORE, "line-width": selW(2, 3.5) } }, firstSymbol);
  }

  // 50 m shade (island-wide, terrain only) when zoomed in, and the top-zone outlines.
  const on = v.mode === "conditions" && v.priv ? "visible" : "none";
  if (urls.hotspots) {
    map.addSource("hotspots", { type: "vector", url: `pmtiles://${urls.hotspots}` });
    map.addLayer({
      id: "hot-fill", type: "fill", source: "hotspots", "source-layer": "hotspots", minzoom: 11.5, layout: { visibility: on },
      paint: { "fill-color": ramp(["get", "sh"], SHADE_STOPS),
        "fill-opacity": ["interpolate", ["linear"], ["zoom"], 11.5, 0, 12.3, 0.85], "fill-antialias": false },
    }, firstSymbol);
  }
  // Top-zone hexagon outlines: hidden (user, 2026-11-13: the hexagons confused people).
  if (urls.hotspotZones && SHOW_ZONE_OUTLINES) {
    map.addSource("hotzones", { type: "geojson", data: urls.hotspotZones });
    map.addLayer({
      // Top zones: a thin solid ring from far away (so you can see where to zoom), dashed up close.
      id: "hot-zone", type: "line", source: "hotzones", layout: { visibility: on },
      paint: { "line-color": theme === "dark" ? "#f6dfa6" : "#8a5d00",
        "line-width": ["interpolate", ["linear"], ["zoom"], 7, 1.2, 10, 2, 12, 2.5],
        "line-dasharray": ["step", ["zoom"], ["literal", [1, 0]], 9.5, ["literal", [2, 1.2]]] as unknown as ExpressionSpecification },
    }, firstSymbol);
    map.addLayer({
      id: "hot-label", type: "symbol", source: "hotzones", minzoom: 9, layout: { visibility: on,
        "text-field": ["concat", "Top zone · ", ["get", "where"]], "text-font": ["Noto Sans Medium"], "text-size": 13,
        "symbol-placement": "line", "text-max-angle": 30 },
      paint: { "text-color": theme === "dark" ? "#f6dfa6" : "#5a3d00",
        "text-halo-color": theme === "dark" ? "#0c1612" : "#ffffff", "text-halo-width": 1.6 },
    });
  }

  map.addSource("reserves", { type: "geojson", data: urls.reserves,
    attribution: "Nature reserves: EEA NatDA (CC BY 4.0)" });
  map.addLayer({ id: "reserve-fill", type: "fill", source: "reserves", paint: { "fill-pattern": "hatch" } }, firstSymbol);
  map.addLayer({ id: "reserve-line", type: "line", source: "reserves",
    paint: { "line-color": theme === "dark" ? "#d6dbd8" : "#464c49", "line-width": 1.4 } }, firstSymbol);
  map.addLayer({
    id: "reserve-label", type: "symbol", source: "reserves", minzoom: 9.5,
    layout: { "text-field": ["concat", "CLOSED\n", ["get", "name"]], "text-font": ["Noto Sans Medium"],
      "text-size": 13, "text-max-width": 9, "symbol-placement": "point" },
    paint: { "text-color": theme === "dark" ? "#f2f4f3" : "#1b2620",
      "text-halo-color": theme === "dark" ? "#3a403d" : "#ffffff", "text-halo-width": 1.6 },
  });
}

/** Apply day, layer mode, square/zone view and species filter to the existing layers. */
export function applyView(map: MlMap, v: View) {
  const vis = (on: boolean) => (on ? "visible" : "none");
  const cond = v.mode === "conditions";
  map.setLayoutProperty("rain-fill", "visibility", vis(isRain(v.mode)));
  if (isRain(v.mode)) map.setPaintProperty("rain-fill", "fill-color", rainColor(v));
  if (map.getLayer("soil-fill")) {
    map.setLayoutProperty("soil-fill", "visibility", vis(isSoil(v.mode)));
    if (isSoil(v.mode)) map.setPaintProperty("soil-fill", "fill-color", soilColor(v));
  }
  for (const id of ["hex-fill", "hex-line"]) {
    map.setLayoutProperty(id, "visibility", vis(cond && !v.priv));
    map.setFilter(id, hexFilter(v));
  }
  map.setPaintProperty("hex-fill", "fill-color", hexColor(v));
  if (map.getLayer("cells-fill")) {
    map.setLayoutProperty("cells-fill", "visibility", vis(cond && v.priv));
    map.setFilter("cells-fill", cellFilter(v));
    map.setPaintProperty("cells-fill", "fill-color", cellColor(v));
  }
  for (const id of ["hot-fill", "hot-zone", "hot-label"]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis(cond && v.priv));
  }
}

/** Fast path for the rain replay: only the colour changes. */
export function setReplayFrame(map: MlMap, v: View) {
  map.setPaintProperty("rain-fill", "fill-color", rainColor(v));
}

// ---------------------------------------------------------------- 3D terrain
// Heights are stretched on purpose, so the shape of the mountains is easy to see
// (Cyprus only reaches ~1,950 m, which looks flat at true scale). Not accurate.
export const HEIGHTS = [3, 6, 10] as const;
export const EXAGGERATION = 10;      // the user's pick: "10× (extreme)"
let height: number = EXAGGERATION;
export const terrainHeight = () => height;

/** Change the mountain height while 3D is on (no camera move). */
export function setTerrainHeight(map: MlMap, h: number) {
  height = h;
  if (map.getTerrain()) map.setTerrain({ source: "terrain3d", exaggeration: h });
}

// The score colours that sit on the ground; in 3D the ridge shading goes on top of them.
const GROUND_FILLS = ["rain-fill", "hex-fill", "cells-fill", "hot-fill"];

export function set3D(map: MlMap, on: boolean, theme: Theme, animate = true) {
  // Pressed before the map has loaded: nothing to do yet. main.ts re-applies 3D once the layers exist.
  if (!map.getSource("terrain3d")) return;
  const dark = theme === "dark";
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // In 3D, let the mountain shading show through the colours a little more.
  if (map.getLayer("hex-fill")) map.setPaintProperty("hex-fill", "fill-opacity", on ? 0.62 : 0.78);
  if (map.getLayer("cells-fill")) map.setPaintProperty("cells-fill", "fill-opacity", on ? 0.6 : 0.72);
  if (map.getLayer("hillshade")) {
    const ids = map.getStyle().layers.map((l) => l.id);
    if (on) {
      // Shade on top of the colours, lit from the left so the slopes facing you stay bright.
      const top = Math.max(...GROUND_FILLS.map((id) => ids.indexOf(id)));
      const above = ids.slice(top + 1).find((id) => id !== "hillshade");   // the layer just above the top fill
      if (top >= 0 && above) map.moveLayer("hillshade", above);
      map.setPaintProperty("hillshade", "hillshade-method", "combined");
      map.setPaintProperty("hillshade", "hillshade-exaggeration", 0.9);
      map.setPaintProperty("hillshade", "hillshade-illumination-direction", 250);
      map.setPaintProperty("hillshade", "hillshade-illumination-altitude", 35);
      map.setPaintProperty("hillshade", "hillshade-shadow-color", dark ? "rgba(0,0,0,0.7)" : "rgba(40,30,15,0.55)");
      map.setPaintProperty("hillshade", "hillshade-highlight-color", dark ? "rgba(255,240,210,0.35)" : "rgba(255,255,255,0.5)");
      map.setPaintProperty("hillshade", "hillshade-accent-color", "rgba(0,0,0,0)");
    } else {
      // Back to the flat-map shading (same values as addOverlays).
      if (ids.includes("rain-fill")) map.moveLayer("hillshade", "rain-fill");
      for (const p of ["hillshade-method", "hillshade-illumination-direction", "hillshade-illumination-altitude"] as const) {
        map.setPaintProperty("hillshade", p, undefined);
      }
      map.setPaintProperty("hillshade", "hillshade-exaggeration", dark ? 0.55 : 0.45);
      map.setPaintProperty("hillshade", "hillshade-shadow-color", dark ? "#050a08" : "#5b5340");
      map.setPaintProperty("hillshade", "hillshade-highlight-color", dark ? "#3a4a41" : "#ffffff");
      map.setPaintProperty("hillshade", "hillshade-accent-color", dark ? "#0c1612" : "#8a8270");
    }
  }
  if (on) {
    map.setTerrain({ source: "terrain3d", exaggeration: height });
    map.setSky({
      "sky-color": dark ? "#0f1d1a" : "#cfe0e6",
      "horizon-color": dark ? "#24362f" : "#f3f0e7",
      "fog-color": dark ? "#0c1612" : "#ece7da",
      "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.4,
    });
    if (animate) map.easeTo({ pitch: 65, bearing: map.getBearing() || -12, duration: still ? 0 : 900 });
  } else {
    map.setTerrain(null);
    if (animate) map.easeTo({ pitch: 0, bearing: 0, duration: still ? 0 : 700 });
  }
}

/** Outline the tapped hexagon (by feature id) or private square (by cell index). */
export function setSelection(map: MlMap, hexId: number | null, cellIndex: number | null) {
  for (const id of ["hex-selected", "hex-selected-halo"]) {
    if (map.getLayer(id)) map.setFilter(id, ["==", ["id"], hexId ?? -1]);
  }
  for (const id of ["cells-selected", "cells-selected-halo"]) {
    if (map.getLayer(id)) map.setFilter(id, ["==", ["get", "i"], cellIndex ?? -1]);
  }
}
