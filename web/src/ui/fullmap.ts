// Full map mode (shroomy-shared/FULL-MAP-SPEC.md, 13 Nov 2026): the whole island, north up, flat 2D,
// for clean screenshots. Built the same way in every version, so screenshots line up.
//
// Keeps: the map (same day, layer, "Conditions for"), one slim safety line, a small colour key,
// the map credits, and an "Exit full map" button (Esc exits too). Hides everything else.
// Web-address switches: ?full=1 &layer=<id> &day=<0-7> &theme=light|dark  (ids: data/views.json).
// When the map has finished drawing: document.documentElement.dataset.mapReady = "1" ("0" while it redraws).
import type { Map as MlMap } from "maplibre-gl";
import "../styles/full-map.css";

let pending = 0;                                   // async map work still running (see trackReady)

export const FULL_BOUNDS: [[number, number], [number, number]] = [[32.25, 34.55], [34.60, 35.70]];
export const SAFETY_TEXT = "Conditions only. Never eat a wild mushroom based on this map, an app or an AI.";
const EXPAND = `<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 8V3h5M12 3h5v5M17 12v5h-5M8 17H3v-5"
  fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

export interface FullMapHooks {
  map: MlMap;
  /** Turn the 3D view off (full map is always flat 2D). */
  flat: () => void;
  /** Fit the island the normal way again after leaving full map. */
  fitNormal: () => void;
  /** Close tooltips, the tapped-spot panel etc. */
  quiet: () => void;
}

/** The "Full map" map button (a MapLibre control) + the full-map overlay. Returns enter/exit. */
export function mountFullMap(h: FullMapHooks): { enter: () => void; exit: () => void; isOn: () => boolean } {
  const root = document.documentElement;
  const { map } = h;
  let on = false;

  // Slim safety line, small "Exit full map" button: only visible in full map mode.
  const line = document.createElement("div");
  line.className = "fm-safety";
  line.setAttribute("role", "note");
  line.textContent = SAFETY_TEXT;
  const exitBtn = document.createElement("button");
  exitBtn.type = "button";
  exitBtn.className = "fm-exit";
  exitBtn.textContent = "Exit full map";
  exitBtn.setAttribute("aria-label", "Exit full map (Esc)");
  exitBtn.addEventListener("click", () => exit());
  document.body.append(line, exitBtn);

  const frame = () => {
    root.style.setProperty("--fm-line", `${line.offsetHeight}px`);
    map.resize();
    map.jumpTo({ bearing: 0, pitch: 0 });
    map.fitBounds(FULL_BOUNDS, { padding: 24, duration: 0, bearing: 0, pitch: 0 });
  };

  const enter = () => {
    if (on) return;
    on = true;
    h.quiet();
    h.flat();
    root.classList.add("full-map");
    root.dataset.mapReady = "0";
    map.dragRotate.disable();                      // north up: no turning or tilting while in full map
    map.touchZoomRotate.disableRotation();
    map.touchPitch.disable();
    requestAnimationFrame(frame);
    exitBtn.focus({ preventScroll: true });
  };
  const exit = () => {
    if (!on) return;
    on = false;
    root.classList.remove("full-map");
    map.dragRotate.enable();
    map.touchZoomRotate.enableRotation();
    map.touchPitch.enable();
    requestAnimationFrame(() => { map.resize(); h.fitNormal(); });
    btn.focus({ preventScroll: true });
  };
  document.addEventListener("keydown", (e) => { if (on && e.key === "Escape") exit(); });
  window.addEventListener("resize", () => { if (on) requestAnimationFrame(frame); });

  // The map button: expand icon + the words "Full map".
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "fm-open";
  btn.innerHTML = `${EXPAND}<span>Full map</span>`;
  btn.setAttribute("aria-label", "Full map: the whole island, for a clean screenshot");
  btn.dataset.tip = "Show the whole island on its own, north up, for a clean screenshot. Esc or \"Exit full map\" brings the panel back.";
  btn.addEventListener("click", () => enter());
  map.addControl({
    onAdd: () => {
      const div = document.createElement("div");
      div.className = "maplibregl-ctrl maplibregl-ctrl-group fm-ctrl";
      div.append(btn);
      return div;
    },
    onRemove: () => btn.parentElement?.remove(),
  }, "top-right");

  // Ready flag for screenshot tools: "1" when the map has finished drawing after the last change.
  const busy = () => { root.dataset.mapReady = "0"; };
  map.on("movestart", busy);
  map.on("dataloading", busy);
  map.on("idle", () => { if (pending === 0) root.dataset.mapReady = "1"; });

  return { enter, exit, isOn: () => on };
}

/** Wrap async map work (e.g. painting score files) so mapReady stays "0" until it is drawn. */
export function trackReady(map: MlMap, work: Promise<unknown>): void {
  const root = document.documentElement;
  pending++;
  root.dataset.mapReady = "0";
  void work.finally(() => { pending--; map.triggerRepaint(); });
}

/** The web-address switches. */
export function urlSwitches(): { full: boolean; layer: string | null; day: number | null; theme: "light" | "dark" | null } {
  const q = new URLSearchParams(location.search);
  const d = q.get("day");
  const day = d !== null && /^[0-7]$/.test(d) ? Number(d) : null;
  const t = q.get("theme");
  return { full: q.get("full") === "1", layer: q.get("layer"), day, theme: t === "light" || t === "dark" ? t : null };
}
