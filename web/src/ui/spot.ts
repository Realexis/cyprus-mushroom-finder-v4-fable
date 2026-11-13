// The spot panel: everything about one tapped 250 m forest square, ~2 km zone (fallback)
// or 50 m hotspot square. Growing conditions only.
import { SCORE_STOPS } from "../map/layers";
import type { DayInfo, Meta } from "./controls";
import "../styles/maps-link.css";

export interface SpotInfo {
  where: string; alt: [number, number]; trees: Record<string, number>;
  f: number[][]; in: number[][];                       // [day][factor] x100, [day][input]
  /** at = road access point outside nature reserves: [lat, lon, km from the zone middle]. */
  road: { track_km: number; road_km: number; road: string; at?: [number, number, number] } | null;
}
export interface Spots { factors: string[]; inputs: string[]; spots: SpotInfo[]; }

export const TREES: Record<number, string> = {
  1: "Calabrian pine (likely)", 2: "Troodos black pine (likely)", 3: "Golden oak (likely)",
  4: "Other broadleaf", 5: "Tripylos cedar zone (closed)",
};
const BANDS: Record<number, string> = { 1: "low", 2: "mid", 3: "high (above 1,200 m)" };
const FACTOR_LABEL: Record<string, string> = {
  rain_total: "Rain, last 30 days", rain_pulse: "Soaking rain 7–20 days ago",
  temperature: "Temperature, last 7 days", soil_moisture: "Soil moisture",
  season_altitude: "Season for the altitude", shade: "Shade",
};
// Plain-language help for each factor (same numbers as config/scoring.yaml and the About page).
const FACTOR_TIP: Record<string, string> = {
  rain_total: "All rain in the last 30 days. No points below 20 mm, full points from 80 mm.",
  rain_pulse: "The biggest 3-day rain between 7 and 20 days ago. No points below 10 mm, full points from 25 mm.",
  temperature: "Average temperature of the last 7 days, corrected for height. Best 8-18 °C. No points at 3 °C or 24 °C. Frost days take points off.",
  soil_moisture: "How wet the top soil is now, compared with this place's normal. Wetter than most days = more points.",
  season_altitude: "Is it the right month for this height? High Troodos starts in September, middle heights in October, low hills in November.",
  shade: "North and east-facing slopes, valley bottoms and little autumn sun keep the ground moist longer.",
};

// v0.3 engine: the five parts that multiply into the score.
const PART_LABEL: Record<string, string> = {
  habitat: "Habitat", water: "Water in the ground", temperature: "Soil warmth",
  cycle: "Mushroom clock", prior: "Season",
};
const PART_TIP: Record<string, string> = {
  habitat: "Partner trees, tree cover, altitude and soil for this species. It does not change from day to day.",
  water: "Each square has a water bucket. Rain fills it. Sun and wind empty it, faster on sunny slopes.",
  temperature: "Is the soil in this species' comfortable range? Frost stops most species.",
  cycle: "After a soaking rain the clock starts. Warm soil runs it faster, cold soil slower. Then a window opens.",
  prior: "The usual months for this species. Just before and after them the score is lower. Outside that, it is zero.",
};
const STATE_TEXT = [
  "Soil too warm or too cold: the clock is paused.",
  "Waiting for a soaking rain.",
  "Soaking rain fell. The clock is running.",
  "Window open.",
  "A window just ended. It needs rest and a new soaking rain.",
  "Resting after a window. It needs a new soaking rain later.",
];

/** The v0.3 mushroom clock in plain words, from the state and days-left inputs. */
export function engineClock(inp: number[] | null, names: string[]): { text: string; open: boolean } | null {
  if (!inp) return null;
  const st = Math.round(inp[names.indexOf("state")]), left = Math.round(inp[names.indexOf("left_days")]);
  if (!(st >= 0 && st <= 5)) return null;
  const pl = (k: number) => `${k} day${k === 1 ? "" : "s"}`;
  if (st === 3 && left > 0) return { text: `Window open, about ${pl(left)} more.`, open: true };
  if (st === 2 && left > 0) return { text: `Soaking rain fell. Window opens in about ${pl(left)}.`, open: false };
  return { text: STATE_TEXT[st], open: st === 3 };
}

/** v0.3 forecast confidence (spec 3.7): how much of a score needs rain that has not fallen yet. */
type Conf = "high" | "medium" | "low";
export const CONF_LABEL: Record<Conf, string> = { high: "sure", medium: "likely", low: "unsure" };
const CONF_WHY: Record<Conf, string> = {
  high: "this rests on rain that already fell",
  medium: "partly needs rain that is only forecast",
  low: "mostly needs rain that is only forecast",
};
const CONF_HELP: Record<Conf, string> = {
  high: "Sure: the score holds even if no more rain falls. Rain that already fell drives it.",
  medium: "Likely: part of the score needs forecast rain. Forecasts can change.",
  low: "Unsure: most of the score needs rain that has not fallen yet. Check again closer to the day.",
};
const SHORT_WORD = (v: number) => (v >= 80 ? "V.good" : v >= 65 ? "Good" : v >= 45 ? "Fair" : "Poor");

/** Confidence of this spot on a day, from its "rain_dep_pct" number (v0.3); null if not known. */
function confWord(s: SpotData, ctx: SpotContext, day: number): Conf | null {
  const e = ctx.meta.engine, inp = s.inputs?.(day);
  if (!e || !inp) return null;
  const i = e.inputs.indexOf("rain_dep_pct");
  if (i < 0 || !Number.isFinite(inp[i])) return null;
  const dep = inp[i] / 100;
  return dep < e.confidence.sure_below ? "high" : dep < e.confidence.likely_below ? "medium" : "low";
}

export const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

export const fmtDay = (iso: string, opts: Intl.DateTimeFormatOptions) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { ...opts, timeZone: "Asia/Nicosia" });

export function scoreColour(v: number) {
  let c = SCORE_STOPS[0][1];
  for (const [s, col] of SCORE_STOPS) if (v >= s) c = col;
  return c;
}

export function words(v: number) {
  if (v >= 80) return "Very good";
  if (v >= 65) return "Good";
  if (v >= 45) return "Fair";
  return "Poor";
}

/** The mushroom clock in plain words (same rules as pipeline/shroomy/score/clock.py). */
export function clockSentence(daysSince: number, c: Meta["clock"]): { text: string; open: boolean } {
  if (daysSince < 0) return { text: `No soaking rain (${c.soak_mm} mm+) in the last month. Fruiting window closed.`, open: false };
  if (daysSince < c.opens) {
    const k = c.opens - daysSince;
    return { text: `Soaking rain ${daysSince} days ago. Window opens in ${k} day${k === 1 ? "" : "s"}.`, open: false };
  }
  if (daysSince <= c.closes) {
    const k = c.closes - daysSince;
    return { text: `Soaking rain ${daysSince} days ago. Window OPEN, about ${k} more day${k === 1 ? "" : "s"}.`, open: true };
  }
  return { text: `Last soaking rain was ${daysSince} days ago. Fruiting window has closed.`, open: false };
}

/** What the panel needs to know about the current filter, per day. */
export interface SpotContext {
  meta: Meta; day: number;
  species: { code: string; latin: string; season_text: string } | null;
  inSeason: (day: number) => boolean;
  monthOf: (day: number) => number;
  all: SpeciesLite[];
}
export interface SpeciesLite { code: string; latin: string; common: string; months: number[]; season_text: string;
  trees: number[]; bands: number[]; photos: { url: string }[]; }

/** A tapped spot, already turned into numbers per day. */
export interface SpotData {
  kind: "hex" | "cell" | "hot";
  score: (day: number) => number | null;       // null = not habitat for this filter
  clock?: (day: number) => number;
  factors?: (day: number) => number[] | null;  // 0..1, in meta factor order
  inputs?: (day: number) => number[] | null;
  where?: string; trees?: string; altitude?: string; road?: string; note?: string; soil?: string;
  hot?: Record<string, number>;
  /** Pin for "Drive there" / "Share location". road = nearest road point outside nature reserves
   *  (2 km zones); centre = the middle of a 250 m square (none for squares in or by a reserve). */
  access?: { lat: number; lon: number; km?: number; from?: string; kind: "road" | "centre" };
  /** v0.3 general map: the species that gives the best score on a day (shown in "Why this score"). */
  bestName?: (day: number) => string | null;
  /** Habitat score for a species on a day, ignoring its season. null = no habitat here. */
  speciesBase?: (sp: SpeciesLite, day: number) => number | null;
}

/** Every target species, ranked by habitat conditions at this spot on this day. */
function speciesHere(s: SpotData, ctx: SpotContext): string {
  if (!s.speciesBase) return "";
  const m = ctx.monthOf(ctx.day);
  const e = ctx.meta.engine;
  const all = e ? ctx.all.filter((sp) => e.codes.includes(sp.code)) : ctx.all;
  // v0.3: every scored species is ranked (outside its usual season it just scores lower).
  const rows = all.map((sp) => ({ sp, v: s.speciesBase!(sp, ctx.day), on: !!e || sp.months.includes(m) }));
  const good = rows.filter((r) => r.v !== null && r.on).sort((a, b) => (b.v ?? 0) - (a.v ?? 0));
  const off = rows.filter((r) => r.v !== null && !r.on);
  const none = rows.filter((r) => r.v === null);
  const item = (r: (typeof rows)[number]) => `<li><button type="button" class="sp-here" data-pick-species="${r.sp.code}"
      data-tip="Colour the whole map for ${esc(r.sp.latin)} habitat.">
      ${r.sp.photos[0] ? `<img src="${esc(r.sp.photos[0].url)}" alt="" loading="lazy" referrerpolicy="no-referrer" />` : ""}
      <span class="sp-here-name">${e ? `${esc(r.sp.common)}<br><span class="muted"><i>${esc(r.sp.latin)}</i></span>` : `<i>${esc(r.sp.latin)}</i><br><span class="muted">${esc(r.sp.common)}</span>`}</span>
      <span class="sp-here-score" style="background:${scoreColour(r.v!)}"${e ? ` data-tip="${r.v} out of 100"` : ""}>${e ? SHORT_WORD(r.v!) : r.v}</span></button>
      <button type="button" class="link-btn" data-open-card="${r.sp.code}" data-tip="Open the species card: deadly lookalikes first.">Card</button></li>`;
  const names = (list: typeof rows, withSeason: boolean) =>
    list.map((r) => `<i>${esc(r.sp.latin)}</i>${withSeason ? ` (${esc(r.sp.season_text)})` : ""}`).join(", ");
  return `<h3 class="spot-h" data-tip="Each species needs its own trees, altitude and season. This ranks them by how well this spot's conditions suit their habitat. It is not a sighting.">Species habitat here</h3>
    ${good.length ? `<ul class="sp-here-list">${good.map(item).join("")}</ul>`
      : `<p class="muted small">No target species is in season with habitat here on this day.</p>`}
    ${off.length ? `<details class="oos"><summary>Show out-of-season species (${off.length})</summary>
      <p class="muted small">${names(off, true)}.</p></details>` : ""}
    ${none.length ? `<p class="muted small"><b>No habitat here:</b> ${names(none, false)}.</p>` : ""}
    <p class="muted small">${e ? "A better word means" : "A high number means"} good conditions for that species' habitat, not that it is there.</p>`;
}

function factorText(name: string, inp: number[] | null, f: number, ctx: SpotContext, d: DayInfo): string {
  if (name === "season_altitude") {
    if (ctx.species) return ctx.inSeason(d.offset) ? `In season (${ctx.species.season_text})` : `Out of season (${ctx.species.season_text})`;
    return fmtDay(d.date, { month: "long" });
  }
  if (name === "shade") return `${Math.round(f * 100)}/100`;
  if (!inp) return "";
  const [r30, pulse, t7, soil, frost] = inp;
  switch (name) {
    case "rain_total": return `${Math.round(r30)} mm`;
    case "rain_pulse": return `${Math.round(pulse)} mm in 3 days`;
    case "temperature": return `${t7.toFixed(1)} °C average${frost >= 1 ? ` · frost on ${Math.round(frost)} day${frost >= 2 ? "s" : ""}` : ""}`;
    case "soil_moisture": return `wetter than ${Math.round(soil)}% of last season`;
  }
  return "";
}

function engineBars(s: SpotData, ctx: SpotContext): string {
  const e = ctx.meta.engine!;
  const fac = s.factors?.(ctx.day);
  if (!fac) return "";
  const inp = s.inputs?.(ctx.day) ?? null;
  const at = (n: string) => (inp ? inp[e.inputs.indexOf(n)] : NaN);
  const clk = engineClock(inp, e.inputs);
  const val: Record<string, string> = {
    water: Number.isFinite(at("fill_pct")) ? `${Math.round(at("fill_pct"))}% full · ${Math.round(at("rain_3d_mm"))} mm rain in 3 days` : "",
    temperature: Number.isFinite(at("soil_temp_c")) ? `about ${Math.round(at("soil_temp_c"))} °C in the soil` : "",
    cycle: clk?.text ?? "",
    prior: ctx.species ? (ctx.species.season_text ? `usual season ${ctx.species.season_text}` : "") : "",
  };
  const rows = e.parts.map((n, i) => {
    const pct = Math.round(Math.max(0, Math.min(1, fac[i])) * 100);
    return `<li class="why-row" data-tip="${esc(PART_TIP[n])}">
      <div class="why-top"><span>${PART_LABEL[n]}</span><span class="muted">${pct}/100</span></div>
      <div class="why-bar" role="img" aria-label="${PART_LABEL[n]}: ${pct} out of 100"><i style="width:${pct}%;background:${scoreColour(pct)}"></i></div>
      ${val[n] ? `<div class="why-val">${esc(val[n])}</div>` : ""}</li>`;
  }).join("");
  return `<details class="why" open><summary data-tip="The five parts multiply. One short bar pulls the whole score down. Tap to hide or show."><b>Why this score</b></summary>
    <p class="muted small">${ctx.species ? "" : (() => { const b = s.bestName?.(ctx.day); return b ? `For the species that does best here: <b>${esc(b)}</b>. ` : "For the species that does best here. "; })()}The parts multiply: one short bar pulls the score down.</p><ul>${rows}</ul></details>`;
}

function whyBars(s: SpotData, ctx: SpotContext): string {
  if (ctx.meta.engine) return engineBars(s, ctx);
  const fac = s.factors?.(ctx.day);
  if (!fac) return "";
  const names = Object.keys(ctx.meta.weights);
  const inp = s.inputs?.(ctx.day) ?? null;
  const d = ctx.meta.days[ctx.day];
  const rows = names.map((n, i) => {
    let f = fac[i];
    if (n === "season_altitude" && ctx.species) f = ctx.inSeason(ctx.day) ? 1 : 0;
    const pct = Math.round(Math.max(0, Math.min(1, f)) * 100);
    const tip = n === "season_altitude" && ctx.species
      ? `Is it ${ctx.species.latin} season? Its season is ${ctx.species.season_text}. In season = full points.`
      : FACTOR_TIP[n];
    return `<li class="why-row" data-tip="${esc(tip)} This counts for ${Math.round(ctx.meta.weights[n] * 100)}% of the score.">
      <div class="why-top"><span>${FACTOR_LABEL[n]}</span><span class="muted">counts ${Math.round(ctx.meta.weights[n] * 100)}%</span></div>
      <div class="why-bar" role="img" aria-label="${FACTOR_LABEL[n]}: ${pct} out of 100"><i style="width:${pct}%;background:${scoreColour(pct)}"></i></div>
      <div class="why-val">${esc(factorText(n, inp, f, ctx, d))}</div></li>`;
  }).join("");
  return `<details class="why" open><summary data-tip="The six things that make the score. A long bar = that thing is good right now. Tap to hide or show."><b>Why this score</b></summary><ul>${rows}</ul></details>`;
}

function forecast(s: SpotData, ctx: SpotContext): string {
  const bars = ctx.meta.days.map((d) => {
    const off = !!ctx.species && !ctx.inSeason(d.offset);         // out of season: no score
    const v = off ? null : s.score(d.offset);
    const label = d.offset === 0 ? "Today" : fmtDay(d.date, { weekday: "short" });
    const h = v === null ? 0 : Math.max(4, v * 0.56);
    const cf = (ctx.meta.engine && v !== null ? confWord(s, ctx, d.offset) : null) ?? d.confidence;
    const tipText = `${fmtDay(d.date, { weekday: "long", day: "numeric", month: "long" })}: ${off ? "out of season" : v === null ? "no score" : `${words(v).toLowerCase()} (${v}/100)`}. Forecast ${CONF_LABEL[cf]}.`;
    return `<div class="fc-day${d.offset === ctx.day ? " sel" : ""}" data-tip="${tipText}">
      <span class="fc-num">${v === null ? "–" : ctx.meta.engine ? SHORT_WORD(v) : v}</span>
      <i style="height:${h}px;background:${v === null ? "transparent" : scoreColour(v)}"></i>
      <span class="fc-lab">${label}</span><span class="dot ${cf}" aria-hidden="true"></span></div>`;
  }).join("");
  return `<h3 class="spot-h" data-tip="The score for today and the next 7 days. Later days use the weather forecast, so they are less certain.">Next 8 days</h3><div class="fc" aria-label="Score for the next 8 days">${bars}</div>
    <p class="muted small">${ctx.meta.engine ? "Dots: how sure (full = sure: rain already fell, half = likely, empty = unsure: needs forecast rain)."
      : "Dots: forecast confidence (full = high, half = medium, empty = low)."}</p>`;
}

// ---------------------------------------------------------------- Google Maps links
// Free Google Maps URLs (no API key, no cost). They open the Google Maps app on phones.
const ll = (lat: number, lon: number) => `${lat.toFixed(5)},${lon.toFixed(5)}`;
export const mapsDirectionsUrl = (lat: number, lon: number) =>
  `https://www.google.com/maps/dir/?api=1&destination=${ll(lat, lon)}&travelmode=driving`;
export const mapsPinUrl = (lat: number, lon: number) =>
  `https://www.google.com/maps/search/?api=1&query=${ll(lat, lon)}`;

function mapsLinks(s: SpotData): string {
  const a = s.access;
  if (!a) return "";
  const centre = a.kind === "centre";
  const dist = a.km === undefined ? "" : a.km < 0.1 ? ", right by it" : `, about ${a.km} km in a straight line from ${a.from}`;
  const what = centre ? "the middle of this 250 m square" : "the nearest road point by this spot";
  const text = `${centre ? "250 m square" : "Road access point"}${!centre && s.where ? ` · ${s.where.split(" · ")[0]}` : ""} (Cyprus Mushroom Finder, growing conditions only)`;
  const note = centre
    ? `Directions go to the middle of this 250 m square. It may be away from roads and tracks.`
    : `Directions go to the nearest road${dist}, never into a mapped nature reserve.`;
  return `<div class="maps-link">
    <div class="maps-btns">
      <a class="maps-btn primary" href="${mapsDirectionsUrl(a.lat, a.lon)}" target="_blank" rel="noopener"
        data-tip="Opens Google Maps with driving directions to ${what}. Free, no sign-in. Forest tracks may be rough.">
        <span class="maps-main"><span aria-hidden="true">🚗</span> Drive there</span>
        <span class="maps-warn"><span aria-hidden="true">⚠</span> tracks may be rough</span></a>
      <button type="button" class="maps-btn" data-share-url="${mapsPinUrl(a.lat, a.lon)}" data-share-text="${esc(text)}"
        data-tip="Send a Google Maps pin of ${what} to a friend. On a computer it copies the link."><span aria-hidden="true">📍</span> <span class="maps-btn-label">Share location</span></button>
    </div>
    <p class="muted small maps-note">${note}</p>
  </div>`;
}

async function shareLink(btn: HTMLElement) {
  const url = btn.dataset.shareUrl!;
  const label = btn.querySelector<HTMLElement>(".maps-btn-label");
  const say = (t: string) => {
    if (!label) return;
    label.textContent = t;
    window.setTimeout(() => (label.textContent = "Share location"), 2500);
  };
  // Phones: the system share sheet (WhatsApp, Messages…). Computers: copy the link.
  if (navigator.share && matchMedia("(pointer: coarse)").matches) {
    try { await navigator.share({ title: "Location", text: btn.dataset.shareText ?? "", url }); return; }
    catch (e) { if ((e as DOMException).name === "AbortError") return; }
  }
  try { await navigator.clipboard.writeText(url); say("Link copied ✓"); return; }
  catch { /* clipboard blocked: show the link so it can be copied by hand */ }
  const box = btn.closest(".maps-link");
  let input = box?.querySelector<HTMLInputElement>(".maps-copy");
  if (box && !input) {
    input = document.createElement("input");
    input.className = "maps-copy";
    input.readOnly = true;
    input.setAttribute("aria-label", "Google Maps link");
    box.querySelector(".maps-btns")?.after(input);
  }
  if (!input) return;
  input.value = url;
  input.focus();
  input.select();
  say(document.execCommand?.("copy") ? "Link copied ✓" : "Copy the link below");
}

document.addEventListener("click", (e) => {
  const b = (e.target as Element | null)?.closest?.<HTMLElement>("[data-share-url]");
  if (!b) return;
  e.preventDefault();
  void shareLink(b);
});

export function spotHTML(s: SpotData, ctx: SpotContext): string {
  if (s.kind === "hot" && s.hot) return hotHTML(s);
  const v = s.score(ctx.day);
  const sp = ctx.species;
  let head: string;
  if (v === null) {
    head = sp ? `<b>No <i>${esc(sp.latin)}</i> habitat here</b>` : `<b>Not scored on the general map</b>`;
  } else if (sp && !ctx.inSeason(ctx.day)) {
    head = `<b>Out of season for <i>${esc(sp.latin)}</i></b><span class="muted"> (${esc(sp.season_text)})</span>`;
  } else {
    // v0.3: the word sits in the coloured badge next to it, so the title does not repeat it.
    head = ctx.meta.engine
      ? (sp ? `<b>Conditions for <i>${esc(sp.latin)}</i> habitat</b>` : `<b>Growing conditions</b>`)
      : (sp ? `<b>${words(v)} conditions for <i>${esc(sp.latin)}</i> habitat</b>` : `<b>${words(v)} growing conditions</b>`);
  }
  const showScore = v !== null && !(sp && !ctx.inSeason(ctx.day));
  const e = ctx.meta.engine;
  const clk = e ? engineClock(s.inputs?.(ctx.day) ?? null, e.inputs)
    : s.clock ? clockSentence(s.clock(ctx.day), ctx.meta.clock) : null;
  const clkTip = e ? "After a soaking rain (about 20 mm in 3 days) the clock starts. Warm soil runs it faster, cold soil slower. Then a window opens for about 10 days."
    : `Counts the days since the last soaking rain (${ctx.meta.clock.soak_mm} mm or more). The fruiting window opens about ${ctx.meta.clock.opens} days after it and closes about ${ctx.meta.clock.closes} days after it.`;
  const facts = [
    s.trees ? `<li data-tip="The likely trees, worked out from satellite forest maps, height and rock type. Not a tree survey."><span aria-hidden="true">🌲</span> <b>Trees:</b> ${s.trees}</li>` : "",
    s.altitude ? `<li data-tip="Height above sea level. Higher forest is cooler and its season starts earlier."><span aria-hidden="true">⛰</span> <b>Altitude:</b> ${s.altitude}</li>` : "",
    s.soil ? `<li data-tip="From SoilGrids (a computer estimate, few Cyprus samples). 'Holds water' compares this square with other Cyprus forest squares."><span aria-hidden="true">🟫</span> <b>Soil:</b> ${s.soil}</li>` : "",
    s.road ? `<li data-tip="Straight-line distance to the nearest forest track and drivable road, from OpenStreetMap. Not a driving route."><span aria-hidden="true">🚙</span> <b>Nearest:</b> ${s.road}</li>` : "",
  ].join("");
  const e0 = ctx.meta.engine;
  // v0.3 (spec 3.7): words, not numbers. The number stays in the tooltip for the curious.
  const badge = !showScore ? "" : e0
    ? `<span class="spot-word" style="--c:${scoreColour(v!)}" data-tip="Score ${v} out of 100. It describes growing conditions, not mushrooms.">${words(v!)}</span>`
    : `<span class="spot-score" data-tip="0 to 100: how good the growing conditions are here. It does not mean a mushroom is there.">${v}<small>/100</small></span>`;
  const conf = e0 && showScore ? confWord(s, ctx, ctx.day) : null;
  return `
    <div class="spot-head"><span>${head}</span>${badge}</div>
    ${e0 && clk ? `<p class="clock top ${clk.open ? "open" : ""}" data-tip="${esc(clkTip)}"><span aria-hidden="true">⏱</span> ${clk.text}</p>` : ""}
    ${conf ? `<p class="muted small conf-note" data-tip="${esc(CONF_HELP[conf])}">Forecast: <b>${CONF_LABEL[conf]}</b> · ${CONF_WHY[conf]}</p>` : ""}
    ${s.where ? `<p class="muted">${esc(s.where)}</p>` : ""}
    ${s.note ? `<p class="muted small">${s.note}</p>` : ""}
    ${mapsLinks(s)}
    <button type="button" class="spot-more-btn" id="spot-more" data-tip="Show or hide the rest: mushroom clock, why this score, the 8 days, species and trees."></button>
    <div class="spot-rest">
    ${clk && !e0 ? `<p class="clock ${clk.open ? "open" : ""}" data-tip="${esc(clkTip)}"><span aria-hidden="true">⏱</span> <b>Mushroom clock:</b> ${clk.text}</p>` : ""}
    ${showScore ? whyBars(s, ctx) : ""}
    ${forecast(s, ctx)}
    ${ctx.species ? (s.speciesBase ? `<p><button type="button" class="link-btn" data-pick-species=""
        data-tip="Go back to the general map and list every species' habitat for this spot.">Compare all species here</button></p>` : "")
      : speciesHere(s, ctx)}
    ${facts ? `<ul class="facts">${facts}</ul>` : ""}
    <p class="no-rakes" data-tip="Cyprus law: rakes and tools are banned in the forest (up to 1 year in prison, up to €5,000 fine, or both). No fires in or within 2 km of forests."><b>No rakes.</b> Pick by hand or knife. Put the leaf litter back.</p>
    <p class="muted small">Growing conditions only. <button class="link-btn" id="spot-close" type="button" data-tip="Close this panel.">Close</button></p>
    </div>`;
}

function hotHTML(s: SpotData): string {
  const h = s.hot!;
  const part = (label: string, v: number, tip: string) => `<li class="why-row" data-tip="${tip}"><div class="why-top"><span>${label}</span><span class="muted">${v}/100</span></div>
    <div class="why-bar"><i style="width:${v}%;background:#2f6f78"></i></div></li>`;
  return `
    <div class="spot-head"><span><b>50 m terrain square</b></span>
      <span class="spot-score" data-tip="Shade score 0 to 100: the average of the three parts below. Shade keeps the ground moist.">${h.sh}<small>/100 shade</small></span></div>
    <p class="muted">${h.con ? "Conifer forest" : "Broadleaf forest"} · ${h.el} m</p>
    <ul class="why-list">
      ${part("Faces north-east (cooler)", h.fa, "Slopes facing north or east get less sun, so they stay cooler and wetter.")}${part("Valley bottom", h.va, "Valley bottoms collect water and stay damp longer than ridges.")}${part("Little autumn sun", h.ls, "How much autumn sun this square misses, including shadows from nearby ridges.")}
    </ul>
    <p class="muted small">Terrain only. Rain and temperature are the same for the whole zone
      (the weather model is about 9 km). <button class="link-btn" id="spot-close" type="button" data-tip="Close this panel.">Close</button></p>`;
}

// ---------------------------------------------------------------- builders
export function hexSpot(props: Record<string, number>, info: SpotInfo | undefined, prop: (d: number) => string,
                        generalTrees: number[]): SpotData {
  const trees = info ? Object.entries(info.trees).sort((a, b) => b[1] - a[1]).map(([k, share]) => {
    const n = Number(k);
    const off = !generalTrees.includes(n) ? " <span class=\"muted\">(not counted on the general map)</span>" : "";
    return `${TREES[n]} ${Math.round(share * 100)}%${off}`;
  }).join(" · ") : undefined;
  const road = info?.road ? `forest track ≈ ${info.road.track_km} km · road ≈ ${info.road.road_km} km${info.road.road ? ` (${esc(info.road.road)})` : ""}
    <span class="muted">from the middle of this zone</span>` : undefined;
  return {
    kind: "hex",
    // Out of season the hexagon stores 0, but the habitat is still there (shown as "out of season").
    speciesBase: (sp, d) => (props[`${sp.code}${d}`] === undefined ? null : Number(props[`${sp.code}${d}`])),
    score: (d) => (props[prop(d)] === undefined ? null : Number(props[prop(d)])),
    clock: (d) => Number(props[`p${d}`]),
    factors: (d) => (info ? info.f[d].map((x) => x / 100) : null),
    inputs: (d) => (info ? info.in[d] : null),
    where: info ? `${info.where} · zone of about 2 km` : "Zone of about 2 km",
    trees, road,
    access: info?.road?.at ? { lat: info.road.at[0], lon: info.road.at[1], km: info.road.at[2], from: "the middle of this zone", kind: "road" } : undefined,
    altitude: info ? `${info.alt[0].toLocaleString("en-GB")}–${info.alt[1].toLocaleString("en-GB")} m` : undefined,
    note: "Averages over the forest in this ~2 km zone.",
  };
}

/** Private 250 m cell details (cells_info.bin from the pipeline). */
export class CellInfo {
  private constructor(private a: Int16Array, private nf: number, private ni: number, private days: number,
                      private ra: Float32Array | null, private tail = 2) {}
  static async load(url: string, meta: { factors: string[]; inputs: string[]; days: number }): Promise<CellInfo> {
    const buf = await fetch(url).then((r) => r.arrayBuffer());
    // Drive-there pins (cells_road.bin, next to cells_info.bin): each square's centre. Optional.
    const ra = await fetch(url.replace("cells_info.bin", "cells_road.bin"))
      .then((r) => (r.ok ? r.arrayBuffer() : null)).catch(() => null);
    return new CellInfo(new Int16Array(buf), meta.factors.length, meta.inputs.length, meta.days,
      ra ? new Float32Array(ra) : null);
  }
  /** The square's centre for "Drive there", or null (in or by a nature reserve). */
  access(i: number): { lat: number; lon: number } | null {
    if (!this.ra || 2 * i + 1 >= this.ra.length) return null;
    const lat = this.ra[2 * i], lon = this.ra[2 * i + 1];
    return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
  }
  private get stride() { return this.days * (this.nf + this.ni) + this.tail; }
  factors(i: number, d: number): number[] | null {
    const o = i * this.stride + d * (this.nf + this.ni);
    const f = [...this.a.subarray(o, o + this.nf)];
    return f.some((x) => x < 0) ? null : f.map((x) => x / 100);
  }
  inputs(i: number, d: number): number[] {
    const o = i * this.stride + d * (this.nf + this.ni) + this.nf;
    return [...this.a.subarray(o, o + this.ni)].map((x) => x / 10);
  }
  road(i: number): [number, number] {
    const o = (i + 1) * this.stride - 2;
    return [this.a[o], this.a[o + 1]];
  }
}

export function cellSpot(props: Record<string, number>, info: CellInfo | null, score: (d: number) => number | null,
                         lngLat: { lng: number; lat: number }, seasonShare: number,
                         eng?: Pick<SpotData, "factors" | "inputs" | "speciesBase" | "bestName">): SpotData {
  const i = Number(props.i);
  const m = (x: number) => (x < 0 ? "–" : x < 1000 ? `${Math.round(x / 10) * 10} m` : `${(x / 1000).toFixed(1)} km`);
  const rd = info?.road(i);
  const acc = info?.access(i);
  return {
    kind: "cell", score,
    speciesBase: (sp, d) => (sp.trees.includes(Number(props.tree)) && sp.bands.includes(Number(props.band)) && !props.closed
      ? Math.round(Number(props[`b${d}`]) + seasonShare) : null),
    clock: (d) => Number(props[`p${d}`]),
    factors: (d) => info?.factors(i, d) ?? null,
    inputs: (d) => info?.inputs(i, d) ?? null,
    ...eng,                                       // v0.3: parts, numbers and species scores from the score files
    where: `250 m square · ${lngLat.lat.toFixed(4)}, ${lngLat.lng.toFixed(4)}`,
    trees: TREES[Number(props.tree)] ?? "Forest",
    soil: props.awc === undefined ? undefined
      : `holds water ${["", "poorly", "average", "well"][Number(props.hold)] ?? "–"} · pH ${(Number(props.ph) / 10).toFixed(1)}${props.su ? " · <span class=\"muted\">uncertain estimate</span>" : " · <span class=\"muted\">estimate</span>"}${props.tc !== undefined ? ` · tree cover ${props.tc}%` : ""}`,
    altitude: `${Number(props.elev).toLocaleString("en-GB")} m · ${BANDS[Number(props.band)] ?? ""} band`,
    road: rd ? `forest track ${m(rd[0])} · road ${m(rd[1])}` : undefined,
    access: acc ? { ...acc, kind: "centre" } : undefined,
    note: undefined,
  };
}
