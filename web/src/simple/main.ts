// PROTOTYPE: an extremely simple version of the map ("answer first").
// One screen: the 3 best areas for the chosen day, a big map, and one "More" button.
// Growing conditions only. Public ~2 km hexagons only (never the private 250 m data).
import "@fontsource/atkinson-hyperlegible/400.css";
import "@fontsource/atkinson-hyperlegible/700.css";
import "maplibre-gl/dist/maplibre-gl.css";
import "../styles/tokens.css";
import "./simple.css";

import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { addOverlays, applyView, setSelection, type LayerUrls, type View } from "../map/layers";
import { baseStyle, type Theme } from "../map/style";
import type { Meta } from "../ui/controls";
import { mountEmergency } from "../ui/safety";
import { clockSentence, cyprusDate, esc, fmtDay, scoreColour, words, type Spots } from "./text";
import { applyTheme, currentTheme, toggleTheme } from "../ui/theme";
import { mountMore } from "./more";

interface TopZone { rank: number; where: string; lat: number; lon: number; score: number; }
interface Summary { days: { date: string; confidence: "high" | "medium" | "low"; top_zones: TopZone[] }[]; }
type HexFC = GeoJSON.FeatureCollection<GeoJSON.Polygon, Record<string, number>>;

const abs = (p: string) => new URL(p, document.baseURI).href;
const getJSON = <T>(p: string) => fetch(abs(p), { cache: "no-cache" }).then((r) => {
  if (!r.ok) throw new Error(`${p}: ${r.status}`);
  return r.json() as Promise<T>;
});
const phone = matchMedia("(max-width: 899px)");

/** "today", "tomorrow" or "on Saturday 14 Nov". */
export function dayWords(iso: string): string {
  if (iso === cyprusDate()) return "today";
  if (iso === cyprusDate(1)) return "tomorrow";
  return `on ${fmtDay(iso, { weekday: "long", day: "numeric", month: "short" })}`;
}

/** Dark text on the warm colours, light text on the dark greens. */
const badge = (v: number, cls = "s-badge") =>
  `<span class="${cls}" style="background:${scoreColour(v)};color:${v >= 50 ? "#1b1405" : "#ffffff"}">${v}</span>`;

function inRing(x: number, y: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

async function main() {
  let theme: Theme = currentTheme();
  applyTheme(theme);
  mountEmergency([...document.querySelectorAll<HTMLElement>("[data-emergency]")]);

  maplibregl.setWorkerUrl(abs("vendor/maplibre-gl-worker.mjs"));
  maplibregl.addProtocol("pmtiles", new Protocol().tile);

  const [meta, summary, spots, hexes] = await Promise.all([
    getJSON<Meta>("data/meta.json"), getJSON<Summary>("data/summary.json"),
    getJSON<Spots>("data/spots.json"), getJSON<HexFC>("data/hexes.geojson"),
  ]);

  // Start on the real date in Cyprus if the data has it (the data may be a day old).
  let day = Math.max(0, meta.days.findIndex((d) => d.date === cyprusDate()));
  type Sel = { kind: "hex"; id: number; top?: number } | { kind: "reserve"; name: string } | null;
  let sel: Sel = null;

  const answer = document.getElementById("answer")!;
  const zone = document.getElementById("zone")!;
  const urls: LayerUrls = {
    terrain: abs("tiles/terrain.pmtiles"), hexes: abs("data/hexes.geojson"),
    rain: abs("data/rain.geojson"), reserves: abs("data/reserves.geojson"),
  };
  const basemap = abs("tiles/basemap.pmtiles");
  const view = (): View => ({ day, mode: "conditions", priv: false, replayIndex: 0,
    filter: { code: null, trees: [], bands: [], inSeason: true, seasonShare: meta.season_share, engine: false } });

  const map = new maplibregl.Map({
    container: "map",
    style: baseStyle(theme, basemap),
    bounds: [[32.27, 34.56], [34.6, 35.7]],
    maxBounds: [[29.0, 32.0], [37.8, 38.2]],
    attributionControl: { compact: true },
    dragRotate: false, pitchWithRotate: false,
  });
  map.touchZoomRotate.disableRotation();
  if (import.meta.env.DEV) (window as unknown as { map: unknown }).map = map;
  const geo = new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true } });
  map.addControl(geo, "top-right");          // hidden by CSS; "More" → "Show where I am" uses it

  /** Map space not covered by our cards. */
  const pad = (): maplibregl.PaddingOptions => {
    if (!phone.matches) return { top: 24, right: 24, bottom: 24, left: answer.offsetWidth + 40 };
    return { top: 16, right: 16, left: 16, bottom: zone.hidden ? 16 : zone.offsetHeight + 24 };
  };
  const fitCyprus = () => map.fitBounds([[32.27, 34.56], [34.6, 35.7]], { padding: pad(), duration: 0 });

  // ---------------------------------------------------------------- the answer card
  const top3 = () => summary.days[day]?.top_zones.slice(0, 3) ?? [];
  const hexAt = (lon: number, lat: number) => hexes.features.findIndex((f) => inRing(lon, lat, f.geometry.coordinates[0]));

  const renderAnswer = () => {
    const d = meta.days[day];
    const late = meta.weather_run < cyprusDate();
    const conf = d.confidence === "high" ? "" : d.confidence === "medium"
      ? "Forecast. It may still change." : "Forecast. Only a rough guide.";
    const rows = top3().map((z, i) => `<li><button type="button" class="s-row${sel?.kind === "hex" && sel.top === i ? " on" : ""}"
        data-top="${i}" aria-label="${i + 1}: ${esc(z.where)}, score ${z.score} out of 100">
        <span class="s-rank" aria-hidden="true">${i + 1}</span><span class="s-name">${esc(z.where)}</span>${badge(z.score)}</button></li>`).join("");
    answer.innerHTML = `
      <h1 class="s-title">Best growing conditions <span class="s-when">${esc(dayWords(d.date))}</span></h1>
      <p class="s-sub">Score out of 100. Higher is better.${conf ? ` <b>${conf}</b>` : ""}</p>
      ${late ? `<p class="s-late">Data delayed. Last update ${esc(fmtDay(meta.weather_run, { day: "numeric", month: "long" }))}.</p>` : ""}
      <ol class="s-list">${rows}</ol>`;
    answer.querySelectorAll<HTMLButtonElement>("[data-top]").forEach((b) => b.addEventListener("click", () => {
      const i = Number(b.dataset.top), z = top3()[i];
      const id = hexAt(z.lon, z.lat);
      select(id >= 0 ? { kind: "hex", id, top: i } : null);
      flyTo([z.lon, z.lat]);
    }));
  };

  // Numbered pins for the 3 best areas.
  const pins = [0, 1, 2].map((i) => {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "s-pin";
    el.textContent = String(i + 1);
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      (answer.querySelector(`[data-top="${i}"]`) as HTMLButtonElement | null)?.click();
    });
    return new maplibregl.Marker({ element: el });
  });
  const placePins = () => top3().forEach((z, i) => {
    pins[i].setLngLat([z.lon, z.lat]).addTo(map);
    pins[i].getElement().setAttribute("aria-label", `Area ${i + 1}: ${z.where}`);
  });

  // ---------------------------------------------------------------- the zone card
  const renderZone = () => {
    if (!sel) { zone.hidden = true; zone.innerHTML = ""; return; }
    let body: string;
    if (sel.kind === "reserve") {
      body = `<p class="s-where">${esc(sel.name)}</p>
        <p class="s-zhead"><b>Nature reserve: CLOSED</b></p>
        <p class="s-say">Closed areas get no score and are never listed.</p>`;
    } else {
      const p = hexes.features[sel.id].properties;
      const v = p[`s${day}`];
      const info = spots.spots[p.h];
      const clk = clockSentence(Number(p[`p${day}`]), meta.clock);
      body = `<p class="s-where">${esc(info?.where ?? "Forest zone")}</p>
        <div class="s-zrow"><p class="s-zhead"><b>${words(v)}</b> growing conditions</p>${badge(v, "s-badge big")}</div>
        <p class="s-say">${esc(clk)}</p>
        <p class="s-small">Average for a forest zone of about 2 km, ${esc(dayWords(meta.days[day].date))}.</p>`;
    }
    zone.innerHTML = `<button type="button" class="s-close" aria-label="Close">✕</button>${body}`;
    zone.hidden = false;
    zone.querySelector(".s-close")!.addEventListener("click", () => select(null));
  };

  const select = (s: Sel) => {
    sel = s;
    setSelection(map, s?.kind === "hex" ? s.id : null, null);
    renderZone();
    renderAnswer();
  };
  const flyTo = (c: [number, number]) =>
    map.flyTo({ center: c, zoom: Math.max(map.getZoom(), 10.2), padding: pad(), duration: 1200 });

  map.on("click", (e) => {
    const fs = map.queryRenderedFeatures(e.point, { layers: ["reserve-fill", "hex-fill"] });
    const r = fs.find((f) => f.layer.id === "reserve-fill");
    const h = fs.find((f) => f.layer.id === "hex-fill");
    if (r) select({ kind: "reserve", name: String(r.properties.name ?? "Nature reserve") });
    else if (h) {
      const top = top3().findIndex((z) => hexAt(z.lon, z.lat) === h.id);
      select({ kind: "hex", id: h.id as number, top: top >= 0 ? top : undefined });
    } else { select(null); return; }
    map.easeTo({ center: e.lngLat, padding: pad(), duration: 400 });
  });
  for (const id of ["hex-fill", "reserve-fill"]) {
    map.on("mouseenter", id, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", id, () => (map.getCanvas().style.cursor = ""));
  }

  // ---------------------------------------------------------------- "More"
  const more = mountMore(document.getElementById("more-btn")!, meta, () => day, {
    day: (i) => {
      day = i;
      if (map.isStyleLoaded()) applyView(map, view());
      renderAnswer(); renderZone(); placePins();
    },
    locate: () => geo.trigger(),
    theme: () => {
      theme = toggleTheme();
      map.setStyle(baseStyle(theme, basemap), { diff: false });
      map.once("style.load", onStyle);
    },
  });
  void more;

  // ---------------------------------------------------------------- start
  const onStyle = () => {
    addOverlays(map, theme, urls, view());
    setSelection(map, sel?.kind === "hex" ? sel.id : null, null);
  };
  renderAnswer();
  map.once("load", () => {
    fitCyprus();
    onStyle();
    placePins();
    document.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
  });
  const loading = document.getElementById("loading")!;
  const done = () => loading.remove();
  // Done = the map drew once, or our zones are in (a background tab draws no frames, so "idle" can wait).
  map.once("idle", done);
  map.on("sourcedata", (e) => { if (e.sourceId === "hexes" && e.isSourceLoaded) done(); });
  map.once("load", () => window.setTimeout(done, 1500));
  phone.addEventListener("change", fitCyprus);
}

main().catch((e) => {
  console.error(e);
  const l = document.getElementById("loading");
  if (l) l.textContent = "The map could not load. Check your internet connection, then reload the page.";
});
