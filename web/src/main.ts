import "@fontsource/atkinson-hyperlegible/400.css";
import "@fontsource/atkinson-hyperlegible/700.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles/app.css";

import * as maplibregl from "maplibre-gl";
import type { MapGeoJSONFeature } from "maplibre-gl";
import { Protocol } from "pmtiles";
import { pmtiles } from "./map/files";
import { ScoreStore } from "./map/scores";
import { addOverlays, applyView, hexProp, set3D, setReplayFrame, setSelection, type LayerUrls } from "./map/layers";
import { baseStyle, type Theme } from "./map/style";
import { Panel, type HotZone, type Meta } from "./ui/controls";
import { mountEmergency, mountSafetyToggle } from "./ui/safety";
import { mountSpecies, speciesByCode, type SpeciesNow } from "./ui/species";
import { CellInfo, cellSpot, fmtDay, hexSpot, type SpotData, type Spots } from "./ui/spot";
import { applyTheme, currentTheme, toggleTheme } from "./ui/theme";
import { PREVIEW_BADGE, VERSION } from "./version";
import { hideMapTip as hideTip, mountTips, showAt } from "./ui/tips";
import { mountGuide } from "./ui/guide";
import { renderLegend } from "./ui/legend";
import { words } from "./ui/spot";
import { mountFullMap, trackReady, urlSwitches } from "./ui/fullmap";

const abs = (p: string) => new URL(p, document.baseURI).href;

/** The parts of summary.json the site reads (top zones per day, overall and per species). */
interface SummaryZone { where: string; lat: number; lon: number; score: number; spot?: number; why?: string; confidence?: "high" | "medium" | "low"; }
interface Summary { days: { date: string; top_zones: SummaryZone[];
  species?: Record<string, { in_season: boolean; top_zones: SummaryZone[] }> }[]; }

/** Is this file published? (The dev server answers missing files with the HTML page.) */
async function hasFile(path: string): Promise<boolean> {
  try {
    const r = await fetch(abs(path), { method: "HEAD" });
    return r.ok && (r.headers.get("content-type") ?? "").indexOf("html") < 0;
  } catch { return false; }
}
/** 250 m forest squares published? (If not, the map falls back to ~2 km zones.) */
const hasCells = () => hasFile(pmtiles("data/cells.pmtiles"));

async function getJSON<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(url, { cache: "no-cache" });
    return r.ok ? ((await r.json()) as T) : null;
  } catch { return null; }
}

function cyprusToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Nicosia" }).format(new Date());
}

/** Island-average daily rain for the replay timeline. */
function islandRain(rain: GeoJSON.FeatureCollection | null, n: number): number[] {
  const sum = new Array(n).fill(0);
  const feats = rain?.features ?? [];
  for (const f of feats) {
    const d = (f.properties as { d: number[] }).d;
    for (let i = 0; i < n; i++) sum[i] += d[i] ?? 0;
  }
  return sum.map((v) => (feats.length ? v / feats.length : 0));
}

// 3D view (kept next to its control; imports are hoisted).
import "./styles/map-3d.css";
import { HEIGHTS, setTerrainHeight, terrainHeight } from "./map/layers";

/** The "3D" map button, and (in 3D) the "mountain height" button under it. */
class TerrainControl implements maplibregl.IControl {
  private btn!: HTMLButtonElement;
  private heightBtn!: HTMLButtonElement;
  private map?: maplibregl.Map;
  on = false;
  constructor(private toggle: (on: boolean) => void) {}
  /** Back to flat 2D (used by Full map). */
  off() { if (this.on) { this.on = false; this.update(); this.toggle(false); } }
  onAdd(map: maplibregl.Map) {
    this.map = map;
    const div = document.createElement("div");
    div.className = "maplibregl-ctrl maplibregl-ctrl-group";
    this.btn = document.createElement("button");
    this.btn.type = "button";
    this.btn.className = "ctrl-3d";
    this.btn.addEventListener("click", () => { this.on = !this.on; this.update(); this.toggle(this.on); });
    this.heightBtn = document.createElement("button");
    this.heightBtn.type = "button";
    this.heightBtn.className = "ctrl-height";
    this.heightBtn.addEventListener("click", () => {
      const i = HEIGHTS.indexOf(terrainHeight() as (typeof HEIGHTS)[number]);
      setTerrainHeight(this.map!, HEIGHTS[(i + 1) % HEIGHTS.length]);
      this.update();
    });
    div.append(this.btn, this.heightBtn);
    this.update();
    return div;
  }
  update() {
    this.btn.textContent = this.on ? "2D" : "3D";
    this.btn.setAttribute("aria-pressed", String(this.on));
    this.btn.setAttribute("aria-label", this.on ? "Back to the flat 2D map" : "Show the map in 3D");
    this.btn.dataset.tip = this.on
      ? "Back to the flat map."
      : "Tilt the map to see the mountains in 3D. Heights are stretched to show the shape of the mountains. To turn or tilt: drag with the right mouse button, or with two fingers.";
    const h = terrainHeight();
    this.heightBtn.hidden = !this.on;
    this.heightBtn.innerHTML = `<svg viewBox="0 0 16 10" aria-hidden="true"><path d="M0 10 5.5 2l2.5 3.5L10.5 0 16 10z"/></svg><span>${h}×</span>`;
    this.heightBtn.setAttribute("aria-label", `Mountain height: ${h} times taller than real. Change height`);
    this.heightBtn.dataset.tip = `Mountain height: ${h}× taller than real. Heights are stretched to show the shape of the mountains. Tap to change (${HEIGHTS.join("×, ")}×).`;
  }
  onRemove() { this.btn.parentElement?.remove(); }
}

async function main() {
  // Web-address switches for Full map screenshots: ?full=1 &layer= &day= &theme= (ui/fullmap.ts).
  const sw = urlSwitches();
  applyTheme(sw.theme ?? currentTheme());
  if (PREVIEW_BADGE) {
    const sub = document.querySelector(".brand-sub");
    sub?.insertAdjacentHTML("afterend", ` <span class="ver-badge" data-tip="Test version ${VERSION}. Not the live site.">v${VERSION.split(".").slice(0, 2).join(".")} preview</span>`);
  }
  mountTips();
  mountSafetyToggle();
  const guide = mountGuide();
  mountEmergency([...document.querySelectorAll<HTMLElement>("[data-emergency]")]);

  maplibregl.setWorkerUrl(abs("vendor/maplibre-gl-worker.mjs"));
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  const [meta, priv, spots, rain, shade, summary] = await Promise.all([
    fetch(abs("data/meta.json"), { cache: "no-cache" }).then((r) => r.json() as Promise<Meta>),
    hasCells(),
    getJSON<Spots>(abs("data/spots.json")),
    getJSON<GeoJSON.FeatureCollection>(abs("data/rain.geojson")),
    hasFile(pmtiles("tiles/shade50.pmtiles")),
    getJSON<Summary>(abs("data/summary.json")),
  ]);

  if (meta.weather_run < cyprusToday()) {
    const d = document.getElementById("delayed")!;
    d.textContent = `Data delayed · last update ${meta.weather_run}`;
    d.dataset.tip = "Today's weather update has not arrived yet. The map shows the last good data. It usually updates at 6 am Cyprus time (7 am in summer).";
    d.hidden = false;
  }

  // 250 m square details (~8 MB) load only when a square is first tapped. 50 m hotspot zoom list.
  let cellInfo: CellInfo | null = null;
  let cellInfoLoading: Promise<void> | null = null;
  let cellMeta: { factors: string[]; inputs: string[]; days: number } | null = null;
  const ensureCellInfo = () => cellInfoLoading ??= (async () => {
    cellMeta = await getJSON<{ factors: string[]; inputs: string[]; days: number }>(abs("data/cells_info.json"));
    if (cellMeta) cellInfo = await CellInfo.load(abs("data/cells_info.bin"), cellMeta).catch(() => null);
  })();
  // v0.3: scores come from small files per species / general map (map/scores.ts).
  const store = new ScoreStore((f) => `${abs(f)}?v=${encodeURIComponent(meta.generated_utc)}`);
  const paintScores = () => { if (meta.engine && map.getSource("cells")) trackReady(map, store.paint(map, panel.scoreKey, panel.day)); };
  if (import.meta.env.DEV) (window as unknown as { store: unknown }).store = store;
  // Top-zone outlines (daily). The 50 m shade itself is the fixed file tiles/shade50.pmtiles.
  let hotZonesGeo: GeoJSON.FeatureCollection | undefined;
  if (priv) {
    const hz = await getJSON<{ zones: (HotZone & { ring: number[][] })[] }>(abs("data/hotspot_zones.json"));
    if (hz) {
      hotZonesGeo = { type: "FeatureCollection", features: hz.zones.map((z) => ({ type: "Feature",
        properties: { where: z.where, score: z.score }, geometry: { type: "Polygon", coordinates: [z.ring] } })) };
    }
  }

  // Map files get the data version in their address, so after each daily update the browser
  // fetches fresh pieces instead of mixing in old cached copies (which breaks PMTiles reads).
  const v = (p: string) => `${abs(p)}?v=${encodeURIComponent(meta.generated_utc)}`;
  const urls: LayerUrls = {
    terrain: v(pmtiles("tiles/terrain.pmtiles")), hexes: abs("data/hexes.geojson"),
    rain: abs("data/rain.geojson"), reserves: abs("data/reserves.geojson"),
    cells: priv ? v(pmtiles("data/cells.pmtiles")) : undefined,
    hotspots: priv && shade ? v(pmtiles("tiles/shade50.pmtiles")) : undefined,         // island-wide 50 m shade
    hotspotZones: hotZonesGeo,
  };
  const basemap = v(pmtiles("tiles/basemap.pmtiles"));
  let theme: Theme = sw.theme ?? currentTheme();

  const map = new maplibregl.Map({
    container: "map",
    style: baseStyle(theme, basemap),
    bounds: [[32.25, 34.55], [34.6, 35.7]],
    fitBoundsOptions: { padding: { top: 20, bottom: 20, left: 20, right: 20 } },
    maxBounds: [[29.0, 32.0], [37.8, 38.2]],
    maxPitch: 75,
    attributionControl: { compact: true },
    cooperativeGestures: false,
  });
  if (import.meta.env.DEV) {
    (window as unknown as { map: unknown }).map = map;
    map.on("error", (e) => console.error("[map]", e.error?.message ?? e));
  }
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
  const terrainCtl = new TerrainControl((on) => set3D(map, on, theme));
  map.addControl(terrainCtl, "top-right");
  map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true } }), "top-right");
  // Full map: the whole island for clean screenshots (shroomy-shared/FULL-MAP-SPEC.md).
  const full = mountFullMap({
    map,
    flat: () => terrainCtl.off(),
    fitNormal: () => fitCyprus(),
    quiet: () => { hideTip(); lastPick = null; applySelection(); panel.showSpot(null); },
  });
  // Our own tips on MapLibre's buttons (and no second, native browser tooltip).
  const ctlTips: Record<string, string> = {
    ".maplibregl-ctrl-zoom-in": "Zoom in. You can also scroll or pinch.",
    ".maplibregl-ctrl-zoom-out": "Zoom out.",
    ".maplibregl-ctrl-compass": "Turn the map back to north and flat. The needle shows where north is.",
    ".maplibregl-ctrl-geolocate": "Show where you are on the map (needs location permission). Your position stays on your phone.",
  };
  for (const [sel, tip] of Object.entries(ctlTips)) {
    const b = document.querySelector<HTMLElement>(sel);
    if (b) { b.removeAttribute("title"); b.dataset.tip = tip; }
  }
  // The location button shows crossed out when the browser gives no location: say why, in plain words.
  const geo = document.querySelector<HTMLButtonElement>(".maplibregl-ctrl-geolocate");
  if (geo) {
    const sayGeo = () => {
      const off = geo.disabled;
      geo.removeAttribute("title");
      geo.dataset.tip = off
        ? "Your location is off: this browser gives no location. Allow location for this site in your browser settings to see where you are."
        : ctlTips[".maplibregl-ctrl-geolocate"];
      geo.setAttribute("aria-label", off ? "Your location (off: no location permission)" : "Show your location");
      // Spec 4.10: say it in words next to the crossed-out button, not only in a tooltip.
      let lab = document.getElementById("geo-label");
      if (off && !lab) {
        lab = document.createElement("span");
        lab.id = "geo-label";
        lab.className = "geo-label";
        lab.setAttribute("aria-hidden", "true");
        lab.textContent = "Location off";
        geo.closest(".maplibregl-ctrl-group")?.append(lab);
      }
      if (lab) lab.hidden = !off;
    };
    sayGeo();
    new MutationObserver(sayGeo).observe(geo, { attributes: true, attributeFilter: ["disabled", "title"] });
  }

  const sheet = document.getElementById("sheet")!;
  const phone = matchMedia("(max-width: 899px)");

  // ------------------------------------------------------------ the tapped spot
  type Pick = { f: MapGeoJSONFeature; lngLat: maplibregl.LngLat };
  let lastPick: Pick | null = null;
  type Pick_Event = { point: maplibregl.PointLike & { x: number; y: number }; lngLat: maplibregl.LngLat };
  const PICK_ZOOM = 12;                       // a tap at island zoom zooms in to here, then opens the square
  const buildSpot = (p: Pick): SpotData => {
    const props = p.f.properties as Record<string, number>;
    if (p.f.layer.id === "hot-fill") return { kind: "hot", score: () => null, hot: props };
    if (p.f.layer.id === "cells-fill") {
      const sp = speciesByCode(panel.species);
      const i = Number(props.i);
      if (meta.engine) {
        // v0.3: everything from the score files. Details load on the first tap.
        const e = meta.engine;
        const key = panel.scoreKey;
        const sc = store.get(key), inf = store.info(key);
        const row = sc ? sc.row(i) : -1;
        const visible = e.codes.filter((c) => speciesByCode(c)?.tier === "key" || panel.showMore);
        const s = cellSpot(props, cellInfo, (d) => sc?.score(i, d) ?? null, p.lngLat, 0, {
          factors: (d) => (inf && row >= 0 ? inf.parts(row, d) : null),
          inputs: (d) => (inf && row >= 0 ? inf.inputs(row, d) : null),
          speciesBase: (spx, d) => (visible.includes(spx.code) ? store.get(spx.code)?.score(i, d) ?? null : null),
          bestName: (d) => {
            if (sp || !inf || row < 0) return null;
            const b = Math.round(inf.inputs(row, d)[e.general_inputs.indexOf("best")]);
            return speciesByCode(e.general[key]?.[b] ?? "")?.common ?? null;
          },
        });
        const zone = props.h === undefined ? undefined : spots?.spots[Number(props.h)];
        s.where = zone ? `${zone.where} · 250 m square` : "250 m square";
        const ready = !!cellInfo && inf !== undefined && visible.every((c) => store.get(c) !== undefined);
        s.note = ready ? undefined : "Loading the details for this square…";
        if (!ready) void Promise.all([ensureCellInfo(), store.loadInfo(key), ...visible.map((c) => store.load(c))]).then(() => {
          if (lastPick?.f.layer.id === "cells-fill") panel.showSpot(buildSpot(lastPick), false);
        });
        return s;
      }
      const score = (d: number) => {
        if (!sp) return props[`s${d}`] === null || props[`s${d}`] === undefined ? null : Number(props[`s${d}`]);
        if (!sp.trees.includes(Number(props.tree)) || !sp.bands.includes(Number(props.band))) return null;
        return panel.inSeason(d) ? Math.round(Number(props[`b${d}`]) + meta.season_share) : 0;
      };
      const s = cellSpot(props, cellInfo, score, p.lngLat, meta.season_share);
      const zone = props.h === undefined ? undefined : spots?.spots[Number(props.h)];
      s.where = zone ? `${zone.where} · 250 m forest square` : "250 m forest square";
      s.note = cellInfo ? undefined : "Loading the details for this square…";
      if (!cellInfo) void ensureCellInfo().then(() => {
        if (lastPick?.f.layer.id === "cells-fill") panel.showSpot(buildSpot(lastPick), false);
      });
      return s;
    }
    return hexSpot(props, spots?.spots[Number(props.h)], (d) => hexProp(d, panel.filter), meta.general_map_trees);
  };

  const panel: Panel = new Panel(sheet, meta, priv, islandRain(rain, 30), shade,
    (p) => {
      if (!map.getLayer("hex-fill")) return;               // overlays not added yet (tiles may still be loading)
      applyView(map, p.view);
      paintScores();
      drawLegend();
      if (lastPick && p.mode === "conditions") p.showSpot(buildSpot(lastPick), false);
    },
    (p) => { if (map.isStyleLoaded()) setReplayFrame(map, p.view); },
    (code) => openSpecies(code));
  if (sw.layer !== null) {
    const code = sw.layer === "general" || sw.layer === "" ? null : sw.layer;
    if (code === null || meta.engine?.codes.includes(code)) {
      panel.showMore = speciesByCode(code)?.tier === "more";       // the same menu every time (not the saved choice)
      panel.setSpecies(code);
    }
  }
  if (sw.day !== null && sw.day < meta.days.length) { panel.day = sw.day; panel.refresh(); }
  // Best zone per day (and per species) for the day buttons, from summary.json.
  panel.best = (day, code) => {
    const d = summary?.days[day];
    if (!code && meta.engine && panel.showMore) {            // general map with the "more" species: best of all
      const all = Object.values(d?.species ?? {}).map((x) => x.top_zones[0]).filter(Boolean);
      const z = all.sort((a, b) => b.score - a.score)[0];
      return z ? { score: z.score, where: z.where, confidence: z.confidence } : null;
    }
    const z = code ? (d?.species?.[code]?.in_season ? d.species[code].top_zones[0] : undefined) : d?.top_zones[0];
    return z ? { score: z.score, where: z.where, confidence: z.confidence } : null;
  };
  panel.refresh();

  // The colour key on the map (follows the layer, the species season and the zoom).
  const legendEl = document.getElementById("map-legend")!;
  function drawLegend() { renderLegend(legendEl, panel.view, map.getZoom(), shade); }
  drawLegend();
  map.on("zoom", drawLegend);

  // "Conditions for this mushroom now" on its card: best areas today + best day, from summary.json.
  const speciesNow = (code: string): SpeciesNow | null => {
    const days = summary?.days ?? [];
    const today = days[0]?.species?.[code];
    if (!today) return null;
    let bestDay: SpeciesNow["bestDay"] = null;
    days.forEach((d, k) => {
      const z = d.species?.[code]?.top_zones[0];
      if (z && (!bestDay || z.score > bestDay.score)) {
        bestDay = { label: k === 0 ? "today" : fmtDay(meta.days[k].date, { weekday: "long" }), score: z.score };
      }
    });
    const rs = meta.rain_since;
    const rainSince = rs && meta.engine?.species[code]?.autumn_rain_memory
      ? { from: fmtDay(rs.from, { day: "numeric", month: "long" }), mm: rs.mm } : null;
    return { areas: today.top_zones.slice(0, 3).map((z) => ({ where: z.where, score: z.score })), bestDay, rainSince };
  };
  const openSpecies = mountSpecies(() => panel.monthOf(panel.day), (code) => panel.setSpecies(code), speciesNow);

  // Keep map buttons above the bottom sheet on phones.
  new ResizeObserver(() => document.documentElement.style.setProperty("--sheet-h", `${sheet.offsetHeight + 8}px`))
    .observe(sheet);

  // Fit Cyprus into the part of the map NOT covered by the panel.
  const fitCyprus = () => {
    const pad = phone.matches
      ? { top: 4, right: 50, left: 4, bottom: sheet.offsetHeight + 4 }        // right: clear of the map buttons (Karpas tip)
      : { top: 24, right: 60, bottom: 24, left: sheet.offsetWidth + 40 };
    // Phones: Cyprus is wide and flat, so its width sets the zoom; use every pixel of it.
    map.fitBounds([[32.27, 34.56], [34.62, 35.7]], { padding: pad, duration: 0 });
  };
  map.once("load", () => {
    fitCyprus();
    if (sw.full) full.enter();
    document.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
  });

  // "You tapped here": a small ring marker, plus the zone outline.
  const pinEl = document.createElement("div");
  pinEl.className = "pick-pin";
  pinEl.setAttribute("aria-hidden", "true");
  const pin = new maplibregl.Marker({ element: pinEl });
  const applySelection = () => {
    const f = lastPick?.f;
    // Outline a ~2 km hexagon only when the map itself shows hexagons (fallback view); never over squares.
    const hexView = !!map.getLayer("hex-fill") && map.getLayoutProperty("hex-fill", "visibility") !== "none";
    setSelection(map, f?.layer.id === "hex-fill" && hexView ? (f.id as number) : null,
      f?.layer.id === "cells-fill" ? Number((f.properties as Record<string, number>).i) : null);
    if (lastPick) pin.setLngLat(lastPick.lngLat).addTo(map); else pin.remove();
  };

  const onStyle = () => {
    addOverlays(map, theme, urls, panel.view);
    store.reset();                                            // a new style = a new source without colours
    paintScores();
    if (terrainCtl.on) set3D(map, true, theme, false);
    applySelection();
  };
  map.once("load", onStyle);
  // v0.3: repaint the scores if the squares source was rebuilt (cheap no-op otherwise).
  map.on("sourcedata", (e) => { if (e.sourceId === "cells") paintScores(); });

  // Loading message: hide once the map has drawn its layers for the first time.
  const loading = document.getElementById("loading")!;
  const slow = window.setTimeout(() => {
    document.getElementById("loading-text")!.textContent = "Still loading… a slow connection can take a minute.";
  }, 12000);
  // Done = our zone data is in (or the map went idle). Works even in a background tab,
  // where the map draws no frames and "idle" can wait a long time.
  let loaded = false;
  const finishLoading = () => {
    if (loaded) return;
    loaded = true;
    window.clearTimeout(slow);
    loading.classList.add("done");
    window.setTimeout(() => (loading.hidden = true), 400);
    if (!full.isOn()) guide.openIfFirstVisit();
  };
  map.once("idle", finishLoading);
  map.on("sourcedata", (e) => {
    if (e.sourceId === "hexes" && map.getLayer("hex-fill") && map.isSourceLoaded("hexes")) finishLoading();
  });
  document.addEventListener("open-guide", () => guide.open());

  document.addEventListener("toggle-theme", () => {
    theme = toggleTheme();
    map.setStyle(baseStyle(theme, basemap), { diff: false });
    map.once("style.load", onStyle);
  });

  const pick = (e: Pick_Event) => {
    const layersToHit = ["hot-fill", "cells-fill", "hex-fill"].filter((id) => map.getLayer(id) &&
      map.getLayoutProperty(id, "visibility") !== "none");
    const f: MapGeoJSONFeature | undefined = map.queryRenderedFeatures(e.point, { layers: layersToHit })[0];
    // At island zoom the 250 m squares are too small to be in the map tiles, so a tap hits nothing.
    // Then zoom in on the tapped place and open the square there (phone note, audit round 2).
    const onIsland = e.lngLat.lng > 32.2 && e.lngLat.lng < 34.65 && e.lngLat.lat > 34.55 && e.lngLat.lat < 35.72;
    if (!f && onIsland && panel.mode === "conditions" && map.getZoom() < PICK_ZOOM - 0.5) {
      const pad = phone.matches ? { bottom: sheet.offsetHeight, top: 0, left: 0, right: 0 }
        : { left: sheet.offsetWidth + 32, top: 0, bottom: 0, right: 0 };
      map.easeTo({ center: e.lngLat, zoom: PICK_ZOOM, padding: pad, duration: 600 });
      map.once("idle", () => pick({ point: map.project(e.lngLat), lngLat: e.lngLat }));
      return;
    }
    lastPick = f ? { f, lngLat: e.lngLat } : null;
    applySelection();
    panel.showSpot(lastPick ? buildSpot(lastPick) : null);
    // Keep the tapped spot in view, above the panel on phones / beside it on desktop.
    if (f) {
      const pad = phone.matches ? { bottom: sheet.offsetHeight, top: 0, left: 0, right: 0 }
        : { left: sheet.offsetWidth + 32, top: 0, bottom: 0, right: 0 };
      map.easeTo({ center: e.lngLat, padding: pad, duration: 400 });
    }
  };
  map.on("click", (e) => pick(e));
  document.addEventListener("spot-closed", () => {
    lastPick = null;
    applySelection();
  });
  for (const id of ["hex-fill", "cells-fill", "hot-fill"]) {
    map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; hideTip(); });
  }

  // Hovering the map (mouse only): a small tip with the score, so you can scan before clicking.
  map.on("mousemove", (e) => {
    if (panel.mode !== "conditions") return;
    const ids = ["hot-fill", "cells-fill", "hex-fill"].filter((id) => map.getLayer(id) &&
      map.getLayoutProperty(id, "visibility") !== "none");
    const f = map.queryRenderedFeatures(e.point, { layers: ids })[0];
    if (!f) { hideTip(); return; }
    const r = map.getCanvas().getBoundingClientRect();
    const p = f.properties as Record<string, number>;
    let text: string;
    if (f.layer.id === "hot-fill") text = `Shade ${p.sh}/100 · ${p.el} m. Click for details.`;
    else {
      const sp = speciesByCode(panel.species);
      if (sp && !panel.inSeason(panel.day)) text = `Out of season for ${sp.latin} (${sp.season_text}). Click for details.`;
      else {
        const v = buildSpot({ f, lngLat: e.lngLat }).score(panel.day);
        text = v === null ? "Not scored here. Click for details." : `${v}/100 · ${words(v)}. Click for details.`;
      }
    }
    showAt(e.originalEvent.clientX || r.left + e.point.x, (e.originalEvent.clientY || r.top + e.point.y) - 6, text);
  });
  map.on("mouseout", () => hideTip());
  map.on("movestart", () => hideTip());
}

main().catch((e) => {
  console.error(e);
  const t = document.getElementById("loading-text");
  if (t) t.textContent = "The map could not load. Check your internet connection, then reload the page.";
  document.getElementById("loading")?.classList.add("failed");
});
