// Bottom sheet (mobile) / side panel (desktop): days, layer switch, species filter,
// rain replay, legend, hotspot zoom list and the spot panel.
import { RAIN1_STOPS, RAIN30_STOPS, RAIN7_STOPS, SCORE_STOPS, SHADE_STOPS, SOILPH_STOPS, SOILW_STOPS, isSoil, type Filter, type Mode, type View } from "../map/layers";
import { SPECIES, speciesByCode } from "./species";
import { esc, fmtDay, scoreColour, spotHTML, words, type SpotData } from "./spot";

export interface DayInfo { offset: number; date: string; confidence: "high" | "medium" | "low"; }
export interface Meta {
  weather_run: string; generated_utc: string; model: string; days: DayInfo[]; credits: unknown[];
  rain_days: string[];
  clock: { opens: number; closes: number; soak_mm: number };
  weights: Record<string, number>; season_share: number; general_map_trees: number[];
  /** v0.3 species engine: present when the map shows the multiplied score. */
  engine?: { parts: string[]; inputs: string[]; general_inputs: string[]; codes: string[]; states: string[];
    /** Rain dependence limits for sure / likely / unsure (config/engine.yaml). */
    confidence: { sure_below: number; likely_below: number };
    /** Species codes behind each general map ("key", "all"), in the order of the "best" input. */
    general: Record<string, string[]>;
    species: Record<string, { english_name: string; latin_name: string; season_text: string; window_days: number }> };
}
export interface HotZone { hex: string; where: string; lat: number; lon: number; score: number; date: string; }

/** Forecast confidence in plain words (it is about the weather forecast, not about mushrooms). */
const CONF_WORD = { high: "sure", medium: "likely", low: "unsure" };
/** The best ~2 km zone of a day (from summary.json), for the general map or a species. */
export interface Best { score: number; where: string; confidence?: DayInfo["confidence"]; }
const CONF_TIP = {
  high: "Forecast for the next 2 days: usually reliable.",
  medium: "Forecast 3-4 days ahead: it may still change.",
  low: "Forecast 5 or more days ahead: only a rough guide. Check again closer to the day.",
};
/** v0.3 (spec 3.7): confidence = how much the best zone's score needs rain that has not fallen yet. */
const CONF_TIP_V3 = {
  high: "the best zone's score rests on rain that already fell, so it holds even if no more rain comes.",
  medium: "part of the best zone's score needs rain that is only forecast.",
  low: "most of the best zone's score needs rain that is only forecast. Check again closer to the day.",
};
const REPLAY_DAYS = 30;
/** Top row of the zone panel: always a clear way back (stays visible while the panel scrolls). */
const SPOT_BAR = `<div class="spot-bar">
  <button type="button" class="spot-back" data-spot-back data-tip="Close this panel and go back to the days.">
    <span aria-hidden="true">←</span> Back to days</button>
  <button type="button" class="spot-x" data-spot-close aria-label="Close this panel" data-tip="Close this panel.">✕</button></div>`;

function gradient(stops: [number, string][]) {
  const max = stops[stops.length - 1][0];
  return `linear-gradient(90deg, ${stops.map(([v, c]) => `${c} ${(v / max) * 100}%`).join(", ")})`;
}

const MORE_KEY = "shroomy-show-more";
function readMore(): boolean { try { return localStorage.getItem(MORE_KEY) === "1"; } catch { return false; } }
function saveMore(on: boolean) { try { localStorage.setItem(MORE_KEY, on ? "1" : "0"); } catch { /* private window */ } }

export class Panel {
  day = 0;
  /** v0.3: show the "more" species too (and use them in the general map). */
  showMore = readMore();
  mode: Mode = "conditions";
  priv = false;
  species: string | null = null;
  replayIndex = REPLAY_DAYS - 1;
  playing = false;
  private timer = 0;
  private spot: SpotData | null = null;
  /** Phone panel size: "min" (just a bar), "peek" (days, or the top of a zone), "full" (everything). */
  sheet: "min" | "peek" | "full" = matchMedia("(max-width: 899px)").matches ? "peek" : "full";
  private setSheet(s: "min" | "peek" | "full") { this.sheet = s; this.render(); }
  /** Best zone per day (set by main.ts from summary.json). */
  best: (day: number, species: string | null) => Best | null = () => null;
  refresh() { this.render(); }

  /** `fine` = the 250 m forest squares are published (the normal case). Without them: ~2 km zones. */
  constructor(private el: HTMLElement, private meta: Meta, fine: boolean,
              private islandRain: number[], private hasHot: boolean,
              private onChange: (p: Panel) => void, private onFrame: (p: Panel) => void,
              private openSpecies: (code?: string) => void) {
    this.priv = fine;
    // Escape closes the zone panel (unless a dialog is open: it closes itself first).
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.spot && !document.querySelector("dialog[open]")) this.closeSpot(true);
    });
    this.render();
  }

  /** Month of a day offset (1-12), for species season windows. */
  monthOf(day: number) { return Number(this.meta.days[day].date.slice(5, 7)); }

  /** Is this species scored by the v0.3 engine (soft season: never greyed out)? */
  isEngine = (code: string | null) => !!code && !!this.meta.engine?.codes.includes(code);

  /** In the species' usual months (species.yaml). */
  usualSeason = (day: number) => {
    const sp = speciesByCode(this.species);
    return !sp || sp.months.includes(this.monthOf(day));
  };

  /** Which score file colours the map: the species, or the general map of the species shown. */
  get scoreKey(): string { return this.species ?? (this.showMore ? "all" : "key"); }

  /** Scored on this day? Engine species always are (soft season); older species only in season. */
  inSeason = (day: number) => this.isEngine(this.species) || this.usualSeason(day);

  get filter(): Filter {
    const sp = speciesByCode(this.species);
    return { code: sp?.code ?? null, trees: sp?.trees ?? [], bands: sp?.bands ?? [],
      inSeason: this.inSeason(this.day), seasonShare: this.meta.season_share, engine: !!this.meta.engine };
  }

  get view(): View {
    return { day: this.day, mode: this.mode, priv: this.priv, filter: this.filter, replayIndex: this.replayIndex };
  }

  setSpecies(code: string | null) {
    this.species = code;
    if (speciesByCode(code)?.tier === "more" && !this.showMore) { this.showMore = true; saveMore(true); }
    if (this.mode !== "conditions") { this.stop(); this.mode = "conditions"; }
    this.render(); this.onChange(this);
  }

  /** Close the zone panel; `toDays` also brings the day buttons back into view and focus. */
  closeSpot(toDays = false) {
    this.showSpot(null);
    document.dispatchEvent(new Event("spot-closed"));
    if (toDays) {
      this.el.scrollTo({ top: 0 });
      this.el.querySelector<HTMLButtonElement>('.day[aria-pressed="true"]')?.focus({ preventScroll: true });
    }
  }

  showSpot(s: SpotData | null, scroll = true) {
    if (s && this.sheet === "min") {                     // tapped the map with the panel hidden: show the short panel
      this.spot = s; this.sheet = "peek"; this.render();
      return;
    }
    this.spot = s;
    this.renderSpot();
    if (s && scroll) this.el.querySelector("#spot")?.scrollIntoView({ block: "nearest" });
  }

  // ------------------------------------------------------------ rain replay
  private play() {
    if (this.replayIndex >= REPLAY_DAYS - 1) this.replayIndex = 0;
    this.playing = true;
    this.timer = window.setInterval(() => {
      if (this.replayIndex >= REPLAY_DAYS - 1) { this.stop(); return; }
      this.replayIndex++; this.updateReplay(); this.onFrame(this);
    }, 550);
    this.updateReplay();
  }

  private stop() {
    window.clearInterval(this.timer); this.playing = false;
    if (this.el.querySelector("#replay")) this.updateReplay();
  }

  private updateReplay() {
    const i = this.replayIndex;
    const d = this.meta.rain_days[i];
    const btn = this.el.querySelector<HTMLButtonElement>("#play");
    if (btn) {
      btn.innerHTML = this.playing ? "❚❚ Pause" : "▶ Play";
      btn.setAttribute("aria-label", this.playing ? "Pause the rain replay" : "Play the rain replay");
      btn.dataset.tip = this.playing ? "Pause on this day." : "Play the last 30 days of rain, one day at a time.";
    }
    const date = this.el.querySelector("#replay-date");
    if (date) date.innerHTML = `<b>${fmtDay(d, { weekday: "short", day: "numeric", month: "short" })}</b>
      ${i === REPLAY_DAYS - 1 ? "· today" : `· ${REPLAY_DAYS - 1 - i} day${REPLAY_DAYS - 1 - i === 1 ? "" : "s"} ago`}
      <span class="muted">· island average ${this.islandRain[i].toFixed(1)} mm</span>`;
    const sl = this.el.querySelector<HTMLInputElement>("#replay-slider");
    if (sl) { sl.value = String(i); sl.setAttribute("aria-valuetext", fmtDay(d, { day: "numeric", month: "long" })); }
    this.el.querySelectorAll<HTMLElement>(".tl i").forEach((b, k) => b.classList.toggle("now", k === i));
  }

  private replayHTML() {
    const max = Math.max(1, ...this.islandRain.slice(0, REPLAY_DAYS));
    const bars = this.islandRain.slice(0, REPLAY_DAYS).map((v, k) =>
      `<i style="height:${Math.max(2, (v / max) * 40)}px"></i>`).join("");
    return `<div class="replay" id="replay">
      <div class="replay-row"><button id="play" class="primary-btn" type="button"></button>
        <span id="replay-date" aria-live="polite"></span></div>
      <div class="tl" aria-hidden="true" data-tip="Each bar is one day. Taller bar = more rain over the island. Tap a bar to jump to that day.">${bars}</div>
      <input id="replay-slider" type="range" data-tip="Drag to choose a day of the last 30 days." min="0" max="${REPLAY_DAYS - 1}" step="1" value="${this.replayIndex}"
        aria-label="Day of the rain replay" />
      <div class="legend-scale"><span>${fmtDay(this.meta.rain_days[0], { day: "numeric", month: "short" })}</span><span>today</span></div>
      <p class="muted small">Daily rain for each ~3 km weather square, last 30 days.</p>
    </div>`;
  }

  // ------------------------------------------------------------ render
  private render() {
    const days = this.meta.days.map((d) => {
      const label = d.offset === 0 ? "Today" : fmtDay(d.date, { weekday: "short" });
      const num = fmtDay(d.date, { day: "numeric", month: "short" });
      const b = this.best(d.offset, this.species);
      // v0.3: the best zone's own confidence (does its score need forecast rain?); else by days ahead.
      const conf = b?.confidence ?? d.confidence;
      const word = CONF_WORD[conf];
      const long = fmtDay(d.date, { weekday: "long", day: "numeric", month: "long" });
      const oos = !!this.species && !this.inSeason(d.offset);
      const scoreTip = b ? `Best zone: ${words(b.score).toLowerCase()} (${b.score}/100), ${b.where}.` : oos ? "Out of season for this species." : "No score.";
      return `<button class="day" data-day="${d.offset}" aria-pressed="${d.offset === this.day}"
          aria-label="${label} ${num}. ${b ? `Best zone: ${words(b.score).toLowerCase()} (${b.score} out of 100)` : oos ? "Out of season" : "No score"}. Forecast ${word}."
          data-tip="${long}. ${scoreTip} Forecast ${word}: ${(this.meta.engine && b?.confidence ? CONF_TIP_V3 : CONF_TIP)[conf]}">
        <span class="day-top"><b>${label}</b><span class="day-date">${num}</span></span>
        <span class="day-score">${b ? `${words(b.score)}<span class="day-bar" aria-hidden="true"><i style="width:${Math.max(6, b.score)}%;background:${scoreColour(b.score)}"></i></span>` : "–"}</span>
        <span class="day-conf"><i class="dot ${conf}"></i>Forecast: ${word}</span></button>`;
    }).join("");
    const cur = this.meta.days[this.day];
    const sp = speciesByCode(this.species);
    const rainNote = this.mode === "rain7" || this.mode === "rain30"
      ? `<p class="conf-line">Rain shown is the <b>${this.mode === "rain7" ? "last 7" : "last 30"} days</b>, up to today.</p>` : "";
    // In-season species first; out-of-season ones after, in a group that says why they are grey.
    const month = this.monthOf(this.day);
    const opt = (s: (typeof SPECIES)[number], off: boolean) =>
      `<option value="${s.code}" ${s.code === this.species ? "selected" : ""}>${esc(s.common)} · ${esc(s.latin)}${off ? ` · ${esc(s.season_text)}` : ""}${s.rare ? " · rare" : ""}</option>`;
    // v0.3: only species with an engine profile are scored; the rest follow in the next step.
    const eng = !!this.meta.engine;
    const scored = SPECIES.filter((s) => !eng || (this.isEngine(s.code) && (s.tier === "key" || this.showMore)));
    const later = SPECIES.filter((s) => eng && !this.isEngine(s.code));
    const nMore = SPECIES.filter((s) => eng && this.isEngine(s.code) && s.tier === "more").length;
    const inSeasonList = scored.filter((s) => s.months.includes(month));
    const offList = scored.filter((s) => !s.months.includes(month));
    const monthName = fmtDay(cur.date, { month: "long" });
    const options = [`<option value="" ${this.species ? "" : "selected"}>All forest (general map)</option>`,
      inSeasonList.length ? `<optgroup label="In season in ${monthName}: coloured by score">${inSeasonList.map((s) => opt(s, false)).join("")}</optgroup>` : "",
      offList.length ? `<optgroup label="${eng ? `Outside their usual season: lower scores` : `Out of season in ${monthName}: grey, no score`}">${offList.map((s) => opt(s, true)).join("")}</optgroup>` : "",
      later.length ? `<optgroup label="Coming soon to the new model">${later.map((s) => `<option value="${s.code}" disabled>${esc(s.common)} · ${esc(s.latin)}</option>`).join("")}</optgroup>` : "",
    ].join("");
    const warn = sp?.warn ? `<p class="filter-line warn-line"><b>${esc(sp.warn)}</b></p>` : "";
    const seasonMsg = warn + (sp && this.isEngine(sp.code) ? (this.usualSeason(this.day)
      ? `<p class="filter-line">Good conditions for <i>${esc(sp.latin)}</i> habitat · <span class="tag">in season ${esc(sp.season_text)}</span></p>`
      : `<p class="filter-line warn-line"><b>Outside its usual season.</b> <i>${esc(sp.latin)}</i> usually fruits in
          <b>${esc(sp.season_text)}</b>. Its scores are lowered, not set to zero.</p>`)
      : sp ? (this.inSeason(this.day)
      ? `<p class="filter-line">Good conditions for <i>${esc(sp.latin)}</i> habitat · <span class="tag">in season ${esc(sp.season_text)}</span></p>`
      : `<p class="filter-line warn-line"><b>Why is the map grey?</b> <i>${esc(sp.latin)}</i> (${esc(sp.common)}) fruits in
          <b>${esc(sp.season_text)}</b>, and this day is in ${fmtDay(cur.date, { month: "long" })}. Grey shows where its habitat is
          (its trees and altitude), with no score. Its season starts again in
          <b>${new Date(2000, sp.months[0] - 1, 1).toLocaleDateString("en-GB", { month: "long" })}</b>. For now, pick an in-season species.</p>`) : "");

    this.el.innerHTML = `
      <div class="sheet-top">
        ${this.sheet === "min" ? `<span class="sheet-top-label">Days</span>` : `<button type="button" class="sheet-chip" id="sheet-size" aria-expanded="${this.sheet === "full"}"
          data-tip="${this.sheet === "full" ? "Make the panel smaller." : "Show everything: details, species, rain and settings."}">${this.sheet === "full" ? "▾ Less" : "▴ More"}</button>`}
        <button class="grip-btn" id="grip" type="button" aria-label="${this.sheet === "full" ? "Show less" : "Show more"}"><div class="grip"></div></button>
        <button type="button" class="sheet-chip" id="sheet-hide" aria-expanded="${this.sheet !== "min"}"
          data-tip="${this.sheet === "min" ? "Show the panel again." : "Hide the panel to see more map."}">${this.sheet === "min" ? "▴ Show panel" : "▾ Hide"}</button>
      </div>
      <div class="spot" id="spot" hidden></div>
      <div class="days-block">
      <h2 id="days-h">Day</h2>
      <div class="days" role="group" aria-labelledby="days-h">${days}</div>
      <p class="conf-line">${fmtDay(cur.date, { weekday: "long", day: "numeric", month: "long" })}
        ${(() => { const b = this.best(this.day, this.species); return b ? `· best zone <b>${b.score}</b>, ${esc(b.where)}` : ""; })()}
        · Forecast: <b>${CONF_WORD[cur.confidence]}</b></p>
      </div>
      <div class="sheet-more">
      <h2 id="sp-h"><label for="species">Conditions for</label></h2>
      <div class="sp-row">
        <select id="species" aria-describedby="sp-help" data-tip="Pick a mushroom to colour the map for its habitat: its trees, its altitude and its season. Out of season = grey, no score. The map never says the mushroom is there.">${options}</select>
        <button id="cards-btn" type="button" class="icon-btn" aria-label="Open species cards" data-tip="Photos, season, trees and the deadly lookalikes for each mushroom.">Species cards</button>
      </div>
      ${nMore ? `<button type="button" class="chip more-toggle" id="more-btn" aria-pressed="${this.showMore}"
        data-tip="${this.showMore ? "Hide the extra species again." : `Add ${nMore} more species: boletes, wood blewit, field and scrub mushrooms. Some are rare, some are easy to mix up with deadly ones.`}">${this.showMore ? "✓ Showing more species" : "Show more species"} (${nMore})</button>` : ""}
      <p id="sp-help" class="muted small">${eng ? "Each species has its own trees, water, warmth and season." : "A species changes only the trees, altitude and season that count."}</p>
      ${sp ? "" : (() => {
        const on = scored.filter((x) => x.months.includes(this.monthOf(this.day)));
        const off = scored.filter((x) => !x.months.includes(this.monthOf(this.day)));
        return `<div class="filter-line">
          <p data-tip="Species whose season includes this day's month. Tap one to colour the map for its habitat.">
          <b>In season on this day:</b> ${on.length ? on.map((x) => `<button type="button" class="chip" data-pick-species="${x.code}">${esc(x.common)}${x.rare ? ` <span class="tag">rare</span>` : ""}</button>`).join(" ") : "none of our target species"}</p>
          ${off.length ? `<details class="oos"><summary>Show out-of-season species (${off.length})</summary>
            <ul>${off.map((x) => `<li>${esc(x.common)} · ${esc(x.season_text)}</li>`).join("")}</ul>
            <p>${eng ? "Picked anyway, its scores are lower." : "Picked anyway, its habitat shows <b>grey</b> with no score."}</p></details>` : ""}
          ${later.length ? `<p class="muted small">Coming soon to the new model: ${later.map((x) => esc(x.common)).join(", ")}.</p>` : ""}</div>`;
      })()}
      ${seasonMsg}
      <h2 id="layer-h">Show</h2>
      <div class="seg" role="group" aria-labelledby="layer-h">
        <button data-mode="conditions" aria-pressed="${this.mode === "conditions"}"
          data-tip="Colour the forest by its growing-conditions score, 0 to 100. Tap a zone to see why.">Conditions</button>
        <button data-mode="rain7" aria-pressed="${this.mode === "rain7"}"
          data-tip="All the rain of the last 7 days, in millimetres.">Rain 7 days</button>
        <button data-mode="rain30" aria-pressed="${this.mode === "rain30"}"
          data-tip="All the rain of the last 30 days. The score gives full points from 80 mm.">Rain 30 days</button>
        <button data-mode="replay" aria-pressed="${this.mode === "replay"}"
          data-tip="Watch the last 30 days of rain move over the island, day by day.">Rain replay</button>
        <button data-mode="soilw" aria-pressed="${this.mode === "soilw"}"
          data-tip="How much water the top 30 cm of soil can hold. More water held = good conditions last longer after rain. An estimate.">Soil water</button>
        <button data-mode="soilph" aria-pressed="${this.mode === "soilph"}"
          data-tip="Soil pH: acid (orange), neutral (pale) or alkaline (purple). An estimate.">Soil pH</button>
      </div>
      ${rainNote}
      ${this.mode === "replay" ? this.replayHTML() : ""}
      ${this.legend()}
      <p class="no-rakes panel-rakes" data-tip="Cyprus law: rakes and tools are banned in the forest (up to 1 year in prison, up to €5,000 fine, or both). No fires in or within 2 km of forests."><b>No rakes.</b> Pick by hand or knife. Put the leaf litter back.</p>
      <div class="links"><a href="about.html" data-tip="Where the data comes from, how the score works, and the picking law.">About the data</a>
        <button id="guide-btn" type="button" data-tip="Show the three-step guide again.">How to use</button>
        <button id="theme-btn" type="button" data-tip="Switch between light and dark colours. Dark is easier on the eyes at night.">Light / dark</button></div>
      </div>`;

    this.el.querySelectorAll<HTMLButtonElement>(".day").forEach((b) =>
      b.addEventListener("click", () => { this.day = Number(b.dataset.day); this.render(); this.onChange(this); }));
    this.el.querySelectorAll<HTMLButtonElement>(".seg button").forEach((b) =>
      b.addEventListener("click", () => {
        this.stop();
        this.mode = b.dataset.mode as Mode;
        if (this.mode === "replay") this.replayIndex = 0;
        this.render(); this.onChange(this);
        if (this.mode === "replay") this.play();
      }));
    this.el.querySelector<HTMLSelectElement>("#species")?.addEventListener("change", (e) =>
      this.setSpecies((e.target as HTMLSelectElement).value || null));
    this.el.querySelector("#cards-btn")?.addEventListener("click", () => this.openSpecies(this.species ?? undefined));
    this.el.querySelector("#more-btn")?.addEventListener("click", () => {
      this.showMore = !this.showMore;
      saveMore(this.showMore);
      if (!this.showMore && speciesByCode(this.species)?.tier === "more") this.species = null;
      this.render(); this.onChange(this);
    });
    this.el.querySelectorAll<HTMLButtonElement>(".filter-line [data-pick-species]").forEach((b) =>
      b.addEventListener("click", () => this.setSpecies(b.dataset.pickSpecies!)));
    this.el.querySelector("#play")?.addEventListener("click", () => (this.playing ? this.stop() : this.play()));
    this.el.querySelector<HTMLInputElement>("#replay-slider")?.addEventListener("input", (e) => {
      this.stop(); this.replayIndex = Number((e.target as HTMLInputElement).value);
      this.updateReplay(); this.onFrame(this);
    });
    this.el.querySelector<HTMLElement>(".tl")?.addEventListener("click", (e) => {   // tap a day on the timeline
      const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
      this.stop();
      this.replayIndex = Math.max(0, Math.min(REPLAY_DAYS - 1, Math.floor(((e.clientX - r.left) / r.width) * REPLAY_DAYS)));
      this.updateReplay(); this.onFrame(this);
    });
    // Phone panel size controls
    this.el.dataset.sheet = this.sheet;
    this.el.querySelector("#grip")?.addEventListener("click", () => this.setSheet(this.sheet === "full" ? "peek" : "full"));
    this.el.querySelector("#sheet-size")?.addEventListener("click", () => this.setSheet(this.sheet === "full" ? "peek" : "full"));
    this.el.querySelector("#sheet-hide")?.addEventListener("click", () => this.setSheet(this.sheet === "min" ? "peek" : "min"));
    this.el.querySelector("#theme-btn")?.addEventListener("click", () => document.dispatchEvent(new Event("toggle-theme")));
    this.el.querySelector("#guide-btn")?.addEventListener("click", () => document.dispatchEvent(new Event("open-guide")));
    if (this.mode === "replay") this.updateReplay();
    this.renderSpot();
  }

  private legend() {
    if (isSoil(this.mode)) {
      const ph = this.mode === "soilph", st = ph ? SOILPH_STOPS : SOILW_STOPS;
      const lo = st[0][0], hi = st[st.length - 1][0];
      const bar = `linear-gradient(90deg, ${st.map(([v, c]) => `${c} ${((v - lo) / (hi - lo)) * 100}%`).join(", ")})`;
      return `<div class="legend" aria-label="${ph ? "Soil pH colours" : "Soil water colours"}">
        <div class="legend-bar" style="background:${bar}"></div>
        <div class="legend-scale">${ph ? "<span>acid (5)</span><span>neutral (7)</span><span>alkaline (8+)</span>"
          : "<span>holds little (15 mm)</span><span>holds a lot (40+ mm)</span>"}</div>
        <div class="legend-row muted">${ph ? "Soil pH, top 30 cm." : "Water the top 30 cm can hold for plants and fungi."}
          An estimate from SoilGrids (few Cyprus samples).</div></div>`;
    }
    if (this.mode === "conditions") {
      const sp = speciesByCode(this.species);
      return `<div class="legend" aria-label="Score colours from 0 to 100">
        <div class="legend-bar" style="background:${gradient(SCORE_STOPS)}" data-tip="Score colours. Dark green = poor growing conditions. Orange-red = very good. It is about conditions, never about a mushroom being there."></div>
        <div class="legend-scale"><span>0 · poor</span><span>50</span><span>100 · very good</span></div>
        <div class="legend-row" data-tip="Nature reserves are closed to picking. They always score 0."><span class="swatch closed"></span> Nature reserve: <b>CLOSED</b>, score 0</div>
        ${sp ? `<div class="legend-row" data-tip="Grey = this mushroom's habitat, but the month is outside its season, so there is no score."><span class="swatch oos"></span> Out of season (habitat only)</div>` : ""}
        <div class="legend-row" data-tip="Each coloured square is 250 m of forest. Its score uses the weather for its area (about 9 km wide), corrected for its height, plus its own shade, trees and altitude.">${this.priv ? "Each square = 250 m of forest" : "Each hexagon ≈ 2 km of forest"}</div>
        ${sp ? "" : `<div class="legend-row muted">"Other broadleaf" forest is not scored here (no partner tree). It counts for morels.</div>`}
        ${this.priv && this.hasHot ? `<div class="legend-zoom" data-tip="Zoom in anywhere and the forest turns into 50 m squares showing shade: cool north-east slopes, valley bottoms and little autumn sun. Shade keeps the ground moist. Terrain only, no finer weather. Tap a square for details.">
          <div class="legend-row"><span><b>Zoom in</b> anywhere for 50 m shade</span></div>
          <div class="legend-bar" style="background:${gradient(SHADE_STOPS)}"></div>
          <div class="legend-scale"><span>sunny</span><span>deep shade</span></div></div>` : ""}
      </div>`;
    }
    const stops = this.mode === "replay" ? RAIN1_STOPS : this.mode === "rain7" ? RAIN7_STOPS : RAIN30_STOPS;
    const max = stops[stops.length - 1][0];
    return `<div class="legend" aria-label="Rain colours in millimetres">
      <div class="legend-bar" style="background:${gradient(stops)}" data-tip="Rain colours. Pale = dry. Dark blue = a lot of rain."></div>
      <div class="legend-scale"><span>0 mm</span><span>${max / 2} mm</span><span>${max}+ mm${this.mode === "replay" ? " a day" : ""}</span></div></div>`;
  }

  private renderSpot() {
    const el = this.el.querySelector<HTMLElement>("#spot");
    if (!el) return;
    const s = this.spot;
    if (!s || this.mode !== "conditions") { el.hidden = true; return; }
    const sp = speciesByCode(this.species);
    el.innerHTML = SPOT_BAR + spotHTML(s, { meta: this.meta, day: this.day,
      species: sp ? { code: sp.code, latin: sp.latin, season_text: sp.season_text } : null, inSeason: this.inSeason,
      monthOf: (d) => this.monthOf(d), all: SPECIES });
    el.querySelectorAll<HTMLButtonElement>("[data-pick-species]").forEach((b) =>
      b.addEventListener("click", () => this.setSpecies(b.dataset.pickSpecies || null)));
    el.querySelectorAll<HTMLButtonElement>("[data-open-card]").forEach((b) =>
      b.addEventListener("click", () => this.openSpecies(b.dataset.openCard!)));
    el.querySelector("#spot-close")?.addEventListener("click", () => this.closeSpot(true));
    el.querySelector("#spot-more")?.addEventListener("click", () => this.setSheet(this.sheet === "full" ? "peek" : "full"));
    const more = el.querySelector<HTMLButtonElement>("#spot-more");
    if (more) { more.textContent = this.sheet === "full" ? "▴ Fewer details" : "▾ More details"; more.setAttribute("aria-expanded", String(this.sheet === "full")); }
    el.querySelector("[data-spot-close]")?.addEventListener("click", () => this.closeSpot(true));
    el.querySelector("[data-spot-back]")?.addEventListener("click", () => this.closeSpot(true));
    // Phones: swipe down (from the top of the panel) to close it.
    if (!el.dataset.swipe) {
      el.dataset.swipe = "1";
      let y0: number | null = null;
      el.addEventListener("touchstart", (e) => { y0 = this.el.scrollTop <= 0 ? e.touches[0].clientY : null; }, { passive: true });
      el.addEventListener("touchmove", (e) => {
        if (y0 !== null && e.touches[0].clientY - y0 > 80) { y0 = null; this.closeSpot(true); }
      }, { passive: true });
    }
    el.hidden = false;
  }
}
