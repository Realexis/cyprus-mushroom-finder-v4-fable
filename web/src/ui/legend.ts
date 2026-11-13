// The small colour key that always sits on the map. It follows what the map shows:
// growing-conditions scores, rain, or (when zoomed in) the 50 m shade squares.
import { RAIN1_STOPS, RAIN30_STOPS, RAIN7_STOPS, SCORE_STOPS, SHADE_STOPS, SOILPH_STOPS, SOILW_STOPS, type View } from "../map/layers";

/** Zoom from which the 50 m shade squares cover the forest (see the hot-fill layer). */
export const SHADE_ZOOM = 12;

function gradient(stops: [number, string][]) {
  const lo = stops[0][0], hi = stops[stops.length - 1][0];
  return `linear-gradient(90deg, ${stops.map(([v, c]) => `${c} ${((v - lo) / (hi - lo)) * 100}%`).join(", ")})`;
}

interface Key { title: string; stops: [number, string][]; left: string; right: string; note?: string; tip: string; }

function keyFor(v: View, zoom: number, hasShade: boolean): Key {
  if (v.mode === "soilw") return { title: "Soil holds water", stops: SOILW_STOPS, left: "Little", right: "A lot",
    note: "Estimate (SoilGrids)", tip: "How much water the top 30 cm of soil can hold. More = good conditions last longer after rain. A computer estimate with few Cyprus samples." };
  if (v.mode === "soilph") return { title: "Soil pH", stops: SOILPH_STOPS, left: "Acid", right: "Alkaline",
    note: "Estimate (SoilGrids)", tip: "Soil pH in the top 30 cm: acid (orange), neutral (pale), alkaline (purple). A computer estimate." };
  if (v.mode === "rain7") return { title: "Rain, last 7 days", stops: RAIN7_STOPS, left: "0 mm", right: "80+ mm",
    tip: "Total rain over the last 7 days. Pale = dry, dark blue = a lot of rain." };
  if (v.mode === "rain30") return { title: "Rain, last 30 days", stops: RAIN30_STOPS, left: "0 mm", right: "120+ mm",
    tip: "Total rain over the last 30 days. The score gives full points from 80 mm." };
  if (v.mode === "replay") return { title: "Rain that day", stops: RAIN1_STOPS.slice(1), left: "0.5 mm", right: "30+ mm",
    tip: "Rain on the day shown in the replay." };
  if (hasShade && v.priv && zoom >= SHADE_ZOOM) return { title: "Shade (50 m)", stops: SHADE_STOPS, left: "Sunny", right: "Deep shade",
    note: "Zoom out to see scores", tip: "Close up, the forest shows shade: cool north-east slopes, valley bottoms and little autumn sun. Shade keeps the ground moist." };
  const oos = v.filter.code && !v.filter.inSeason;
  return { title: "Growing conditions", stops: SCORE_STOPS, left: "Poor", right: "Very good",
    note: oos ? "Grey = out of season" : undefined,
    tip: "Colour of each forest square: how good the growing conditions are, from poor (dark green) to very good (orange-red). Not a sign that mushrooms are there." };
}

export function renderLegend(el: HTMLElement, v: View, zoom: number, hasShade: boolean) {
  const k = keyFor(v, zoom, hasShade);
  const html = `
    <div class="ml-title">${k.title}</div>
    <div class="ml-bar" style="background:${gradient(k.stops)}" aria-hidden="true"></div>
    <div class="ml-scale"><span>${k.left}</span><span aria-hidden="true">→</span><span>${k.right}</span></div>
    ${k.note ? `<div class="ml-note">${k.note}</div>` : ""}`;
  if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
  el.dataset.tip = k.tip;
  el.setAttribute("aria-label", `Colour key: ${k.title}, from ${k.left} to ${k.right}.${k.note ? ` ${k.note}.` : ""}`);
}
