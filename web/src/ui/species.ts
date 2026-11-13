// Species guide: a simple list of mushrooms, and one scrolling page per mushroom.
// Order on every mushroom page (v0.3 spec 4.3; user decision 2026-11-13 "new order, never empty"):
// photo -> names -> conditions for this species now -> where and when -> what to look for ->
// "Don't confuse with": this species' own lookalikes where sourced, then ALL deadly / toxic ones (folded).
// The Amanita warning signs show on every page. Cards do not lead with warnings.
// Facts: species.json (project brief) plus field notes below, each backed by a listed source.
// Photos: iNaturalist; every photo opens a larger view with its author and licence.
// Nothing here ever says a mushroom can be eaten.
import "../styles/species.css";
import data from "../generated/species.json";
import { SAFETY_LINE, WARN_ICON } from "./safety";
import { esc } from "./spot";

export interface Photo { url: string; licence: string; attribution: string; page: string; taxon?: string; }
export interface Species {
  code: string; latin: string; common: string; local: string; local_confirmed: boolean;
  trees: number[]; trees_text: string; bands: number[]; altitude_text: string; months: number[];
  notes: string[]; season_text: string; photos: Photo[];
  /** v0.3: "key" shows by default, "more" behind "Show more species"; rare gets a tag; warn = a fixed warning. */
  tier: "key" | "more"; rare: boolean; warn: string;
  /** Latin names of this species' own lookalikes (from its v0.3 profile; may be empty). */
  look: string[]; inat_pages: { name: string; url: string }[];
  records: { gbif_total: number; inat_research: number; months: Record<string, number>; links: { label: string; url: string }[] };
}
export interface Lookalike { latin: string; common: string; severity: "deadly" | "toxic"; note: string; photos: Photo[];
  inat_pages?: { name: string; url: string }[]; }

export const SPECIES = data.species as unknown as Species[];
export const LOOKALIKES = data.lookalikes as Lookalike[];
export const speciesByCode = (c: string | null) => SPECIES.find((s) => s.code === c) ?? null;

const MONTH_LETTER = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_LONG = ["January", "February", "March", "April", "May", "June", "July", "August",
  "September", "October", "November", "December"];

/** A 12-month ring: filled months = season window. A dot marks the current month. (Kept for other screens.) */
export function seasonRing(months: number[], current: number, size = 96): string {
  const c = size / 2, r = size * 0.36, w = size * 0.13;
  const arc = (m: number) => {
    const a0 = ((m - 1) / 12) * 2 * Math.PI - Math.PI / 2 + 0.03;
    const a1 = (m / 12) * 2 * Math.PI - Math.PI / 2 - 0.03;
    const p = (a: number) => `${(c + r * Math.cos(a)).toFixed(2)} ${(c + r * Math.sin(a)).toFixed(2)}`;
    return `<path d="M ${p(a0)} A ${r} ${r} 0 0 1 ${p(a1)}" stroke-width="${w}" fill="none"
      class="${months.includes(m) ? "ring-on" : "ring-off"}"/>`;
  };
  const lab = (m: number) => {
    const a = ((m - 0.5) / 12) * 2 * Math.PI - Math.PI / 2;
    const rr = r + w * 1.25;
    return `<text x="${(c + rr * Math.cos(a)).toFixed(1)}" y="${(c + rr * Math.sin(a)).toFixed(1)}"
      class="${m === current ? "ring-now" : ""}">${MONTH_LETTER[m - 1]}</text>`;
  };
  const am = ((current - 0.5) / 12) * 2 * Math.PI - Math.PI / 2;
  return `<svg data-tip="The year as a ring, starting with January at the top. Filled months = the season. The dot and bold letter = the month you are looking at." class="ring" width="${size + 28}" height="${size + 28}" viewBox="-14 -14 ${size + 28} ${size + 28}" role="img"
    aria-label="Season: ${months.map((m) => MONTH_LETTER[m - 1]).length} months, marked on a year ring">
    ${Array.from({ length: 12 }, (_, i) => arc(i + 1)).join("")}
    ${Array.from({ length: 12 }, (_, i) => lab(i + 1)).join("")}
    <circle cx="${(c + r * Math.cos(am)).toFixed(1)}" cy="${(c + r * Math.sin(am)).toFixed(1)}" r="${w * 0.32}" class="ring-dot"/>
  </svg>`;
}

// ------------------------------------------------------------------ field notes (researched 2026-11-12)
// Every line comes from one of the SOURCES below. Not yet checked by the Cyprus Mycological Association.
const SOURCES: Record<string, { label: string; url: string }> = {
  forests: { label: "Cyprus Department of Forests: Funga / Mushrooms", url: "https://www.moa.gov.cy/moa/fd/fd.nsf/fd67_en/fd67_en?OpenDocument=" },
  kykpee: { label: "KYKPEE: Μανιτάρια της Κύπρου (2015)", url: "https://kykpee.org/mushrooms-of-cyprus/" },
  pedoulas: { label: "Pedoulas: Οδηγός για τα μανιτάρια της Κύπρου", url: "https://www.pedoulas.org.cy/index.php/el/articles/nature-gr/mushrooms-gr" },
  dialogos: { label: "Dialogos: Μανιτάρια, ένας θησαυρός της κυπριακής φύσης (2017)", url: "https://dialogos.com.cy/manitaria-enas-thisavros-tis-kipriakis-fisis/" },
  w_lde: { label: "Wikipedia: Lactarius deliciosus", url: "https://en.wikipedia.org/wiki/Lactarius_deliciosus" },
  w_lsa: { label: "Wikipedia: Lactarius sanguifluus", url: "https://en.wikipedia.org/wiki/Lactarius_sanguifluus" },
  w_rde: { label: "Wikipedia: Russula delica", url: "https://en.wikipedia.org/wiki/Russula_delica" },
  w_tca: { label: "Wikipedia: Tricholoma caligatum", url: "https://en.wikipedia.org/wiki/Tricholoma_caligatum" },
  w_slu: { label: "Wikipedia: Suillus luteus", url: "https://en.wikipedia.org/wiki/Suillus_luteus" },
  w_arb: { label: "Wikipedia: Morchella arbutiphila (described from Cyprus)", url: "https://en.wikipedia.org/wiki/Morchella_arbutiphila" },
  w_dis: { label: "Wikipedia: Morchella disparilis (described from Cyprus)", url: "https://en.wikipedia.org/wiki/Morchella_disparilis" },
  w_false: { label: "Wikipedia: False morel", url: "https://en.wikipedia.org/wiki/False_morel" },
  w_dcap: { label: "Wikipedia: Death cap (Amanita phalloides)", url: "https://en.wikipedia.org/wiki/Amanita_phalloides" },
  fn_lde: { label: "First Nature: Lactarius deliciosus", url: "https://www.first-nature.com/fungi/lactarius-deliciosus.php" },
  fn_tor: { label: "First Nature: Lactarius torminosus", url: "https://www.first-nature.com/fungi/lactarius-torminosus.php" },
  fn_chr: { label: "First Nature: Lactarius chrysorrheus", url: "https://www.first-nature.com/fungi/lactarius-chrysorrheus.php" },
  fn_col: { label: "First Nature: Suillus collinitus", url: "https://www.first-nature.com/fungi/suillus-collinitus.php" },
  exub: { label: "Miller lab (2017): first report of Morchella exuberans in eastern North America, citing Loizides et al. 2016 for burned Calabrian pine in Cyprus",
    url: "https://miller-mycology-lab.inhs.illinois.edu/files/2020/04/First-report-of-the-post-fire-morel-Morchella-exuberans-in-eastern-North-America-Mycologia-2017.pdf" },
  ncbi: { label: "NCBI StatPearls: Gyromitra toxicity", url: "https://www.ncbi.nlm.nih.gov/books/NBK470580/" },
};

interface Field {
  look: [string, string][];   // [part, what to look for]
  where: string[];
  danger: string[];           // "leave it alone if…" signs
  check: string[];            // things still to confirm (behind the info button)
  src: string[];
}
const AMANITA_SIGNS = "a skirt-like ring on the stem, white gills, and a cup (sac) at the base. The cup can be hidden in the soil: clear the soil to check. These are signs of deadly Amanitas.";

const FIELD: Record<string, Field> = {
  lde: {
    look: [
      ["Cap", "Carrot-orange, often with darker orange rings. The edge is rolled in when young; funnel-shaped when old."],
      ["Gills", "Orange and crowded, running a little down the stem."],
      ["Stem", "Short, orange and hollow, often with small darker orange pits."],
      ["Milk", "Cut it: orange, carrot-coloured milk comes out."],
      ["Bruises", "Gills and flesh turn green where touched or bruised."],
    ],
    where: [
      "Mainly under pines: Calabrian pine and Troodos black pine.",
      "Also with golden oak, kermes oak, strawberry tree, mastic and terebinth.",
      "Under pine needles and fallen golden-oak leaves.",
      "Damp, sheltered slopes and valleys, rather than windy, sunny ones.",
    ],
    danger: [
      "White milk, or milk that turns yellow. The yellowdrop milk cap's milk turns sulphur yellow in seconds.",
      "A pinker cap with a woolly, shaggy edge: the woolly milk cap (μαλλίτσης). It is poisonous and grows in Cyprus.",
    ],
    check: ["The woolly milk cap (Lactarius torminosus) is not yet in our list of 10 lookalikes."],
    src: ["w_lde", "fn_lde", "forests", "dialogos", "kykpee", "fn_tor", "fn_chr"],
  },
  lsa: {
    look: [
      ["Cap", "4–7.5 cm, orange to pinkish-buff, sticky, sinking in the middle. Grey-green patches where bruised."],
      ["Gills", "Pale wine-red."],
      ["Stem", "Short, pale pinkish-buff."],
      ["Milk", "Blood-red to purple straight away (not orange first), slowly turning greenish."],
    ],
    where: [
      "Under pines; in Europe often on chalky soil.",
      "In southern Europe it fruits from September to November, and into December in the far south.",
    ],
    danger: [
      "White milk, or milk that turns yellow: a different milk cap.",
      "A pinker cap with a woolly, shaggy edge: the woolly milk cap, which is poisonous.",
    ],
    check: ["Local name: Wikipedia spells it γαιματάς (\"the bloody one\")."],
    src: ["w_lsa", "fn_chr", "fn_tor", "kykpee"],
  },
  rde: {
    look: [
      ["Cap", "White, often with ochre-brown stains. Funnel-shaped and rough, often with soil and leaves stuck on it. Can be half buried."],
      ["Gills", "White to cream, close together, running down the stem."],
      ["Stem", "Short, thick and firm. White."],
      ["Flesh", "White. Does not change colour when cut."],
      ["Smell", "Fruity when young; can smell fishy when old."],
    ],
    where: [
      "Pine, broadleaf and mixed woods. Common in the eastern Mediterranean.",
      "In Cyprus: pine forests and shrubland in autumn, earlier than the red pine mushroom.",
      "Often comes up in warm spells.",
    ],
    danger: [`A white mushroom with ${AMANITA_SIGNS}`],
    check: [],
    src: ["w_rde", "kykpee", "w_dcap"],
  },
  tca: {
    look: [
      ["Cap", "Pale, covered in chestnut to dark-brown scales. The edge is rolled in, with cottony bits."],
      ["Gills", "Whitish to cream, crowded. Brown spots with age."],
      ["Stem", "A cottony ring. Below it, dark brown bands of scales, like a boot."],
      ["Smell", "Strong and spicy, like nutmeg or allspice."],
    ],
    where: [
      "Calabrian pine and Troodos black pine forests.",
      "Elsewhere in the Mediterranean also with evergreen oaks, strawberry trees and terebinth.",
      "Autumn and winter, on the coast and in the mountains.",
    ],
    danger: [`${cap1(AMANITA_SIGNS)}`],
    check: ["Local name: also called μαραθεύτικο in one Cyprus source."],
    src: ["w_tca", "kykpee", "pedoulas", "dialogos", "w_dcap"],
  },
  mor: {
    look: [
      ["Cap", "A honeycomb of pits and ridges. Cyprus morels are often cone-shaped, olive-brown to grey."],
      ["Inside", "Cut it in half from top to bottom: true morels are always hollow inside."],
    ],
    where: [
      "Spring. Recently burned areas, forests, meadows and uncultivated land.",
      "Burned Calabrian pine forest, in the years after a fire.",
      "With strawberry trees on the Troodos rocks; lower down also with cypress and hawthorn.",
    ],
    danger: [
      "Brain-like wrinkles instead of pits, or a cotton-filled or chambered inside: a false morel. False morels stay poisonous even after cooking.",
    ],
    check: [
      "Cyprus has several morel species, two of them first described from Cyprus in 2016 (Morchella arbutiphila and M. disparilis). The names M. esculenta / elata may need updating.",
      "False morels (Gyromitra) are not in our list of 10 lookalikes. We found no Cyprus record of them.",
    ],
    src: ["kykpee", "exub", "w_arb", "w_dis", "w_false", "ncbi", "pedoulas"],
  },
  slu: {
    look: [
      ["Cap", "Brown, slimy and shiny. The skin peels off."],
      ["Underneath", "A sponge of small pores, not gills. Yellow, then olive."],
      ["Stem", "Pale yellow, with a ring: white on top, dark brown to violet underneath. Small dots above the ring."],
    ],
    where: [
      "Under pines, including planted pines, on poor soil.",
      "Often in groups, after rain.",
    ],
    danger: ["Gills instead of pores: it is not this mushroom."],
    check: [
      "The Cyprus Department of Forests lists Suillus collinitus (no ring, pink stem base) and S. granulatus, but not S. luteus. Which Suillus is \"lartias\" is still to confirm.",
    ],
    src: ["w_slu", "forests", "fn_col"],
  },
};
function cap1(s: string) { return s.charAt(0).toUpperCase() + s.slice(1); }

// ------------------------------------------------------------------ small helpers
const ICONS: Record<string, string> = {
  info: `<circle cx="12" cy="12" r="9.5"/><path d="M12 11v6"/><circle cx="12" cy="7.6" r="0.6" fill="currentColor"/>`,
  close: `<path d="M6 6l12 12M18 6 6 18"/>`,
  back: `<path d="M15 5 8 12l7 7"/>`,
  next: `<path d="m9 5 7 7-7 7"/>`,
  map: `<path d="m3 6 6-2 6 2 6-2v14l-6 2-6-2-6 2Z"/><path d="M9 4v14M15 6v14"/>`,
  shroom: `<path d="M3 12a9 7 0 0 1 18 0Z"/><path d="M9.5 12v6a2.5 2.5 0 0 0 5 0v-6"/>`,
  warn: `<path d="M12 3 2 20h20Z"/><path d="M12 10v4"/><circle cx="12" cy="17" r="0.6" fill="currentColor"/>`,
  check: `<path d="m5 12.5 4.5 4.5L19 7.5"/>`,
  look: `<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>`,
  tree: `<path d="M12 2 5.5 11H9l-4.5 7h15L15 11h3.5Z"/><path d="M12 18v4"/>`,
  cal: `<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>`,
};
const icon = (n: string, size = 22) => `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
  stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]}</svg>`;

const inSeason = (sp: Species, m: number) => sp.months.includes(m);
const monthName = (m: number) => MONTH_LONG[m - 1];
function monthsUntil(sp: Species, m: number): number {
  for (let k = 1; k <= 12; k++) if (sp.months.includes(((m - 1 + k) % 12) + 1)) return k;
  return 0;
}
const LOOK_ORDER = [...LOOKALIKES.filter((l) => l.severity === "deadly"), ...LOOKALIKES.filter((l) => l.severity === "toxic")];
const nDeadly = LOOKALIKES.filter((l) => l.severity === "deadly").length;
const sevText = (l: Lookalike) => (l.severity === "deadly" ? "Deadly" : "Toxic");

type Shot = { p: Photo; name: string; sev?: Lookalike["severity"]; note?: string };

/** The year as 12 boxes: the season filled, this month marked. */
function monthBar(sp: Species, now: number): string {
  return `<div class="sc-months" role="img" aria-label="Season ${esc(sp.season_text)}. This month is ${monthName(now)}.">
    ${MONTH_LETTER.map((l, i) => `<span class="${inSeason(sp, i + 1) ? "on" : ""}${i + 1 === now ? " now" : ""}">${l}</span>`).join("")}
  </div>`;
}

// ------------------------------------------------------------------ the dialog
type View = { kind: "list" } | { kind: "looks" } | { kind: "sp"; code: string };

/** "Conditions for this species now", from summary.json (set by main.ts). */
export interface SpeciesNow { areas: { where: string; score: number }[]; bestDay: { label: string; score: number } | null;
  /** Rain since 1 September, for species whose crop depends on autumn rain (a fact, not a score). */
  rainSince?: { from: string; mm: number } | null; }

/** Mounts the species guide. Returns open(code?) — no code = the list of all species. */
export function mountSpecies(month: () => number, onShow: (code: string) => void,
                             conditions: (code: string) => SpeciesNow | null = () => null): (code?: string) => void {
  const dlg = document.createElement("dialog");
  dlg.className = "species-dlg sc";
  dlg.setAttribute("aria-label", "Mushroom guide");
  document.body.append(dlg);

  let view: View = { kind: "list" };
  let now = month();
  let layerOpener: HTMLElement | null = null;
  const sets: Record<string, Shot[]> = {};
  LOOK_ORDER.forEach((l, i) => { sets[`lk${i}`] = l.photos.map((p) => ({ p, name: l.latin, sev: l.severity, note: l.note })); });
  SPECIES.forEach((s) => { sets[`sp-${s.code}`] = s.photos.map((p) => ({ p, name: p.taxon ?? s.latin })); });

  // ---------------------------------------------------------------- pieces
  const lookRows = (only?: string[]) => `<ul class="sc-lk">${LOOK_ORDER.map((l, i) => only && !only.includes(l.latin) ? "" : `
    <li><button type="button" class="sc-lk-row ${l.severity}" data-act="view" data-set="lk${i}" data-i="0"
        aria-label="${esc(l.latin)}, ${sevText(l).toLowerCase()}. Open the photo, with its credit."
        data-tip="Tap to see the photo larger, with its author and licence.">
      ${l.photos[0] ? `<img src="${esc(l.photos[0].url)}" alt="" loading="lazy" referrerpolicy="no-referrer" />` : `<span class="sc-noimg"></span>`}
      <span class="sc-lk-text">
        <span class="sc-sev ${l.severity}">${WARN_ICON}${sevText(l)}</span>
        <b><i>${esc(l.latin)}</i></b>${l.common ? `<span class="sc-soft">${esc(l.common)}</span>` : ""}
        ${l.note ? `<span class="sc-lk-note">${esc(l.note)}</span>` : ""}
      </span>
    </button></li>`).join("")}</ul>`;

  const row = (s: Species) => {
    const on = inSeason(s, now);
    // Common name first (and the local name once confirmed), Latin smaller (spec 4.2). No tooltip (4.6).
    return `<li><button type="button" class="sc-row${on ? " on" : ""}" data-act="open" data-code="${s.code}">
      ${s.photos[0] ? `<img src="${esc(s.photos[0].url)}" alt="" loading="lazy" referrerpolicy="no-referrer" />`
        : `<span class="sc-ph-none" aria-hidden="true">${icon("shroom", 36)}</span>`}
      <span class="sc-row-text">
        <b>${esc(cap1(s.common))}${s.local_confirmed && s.local ? ` <span class="sc-soft">· ${esc(s.local)}</span>` : ""}${s.rare ? ` <span class="sc-tag">rare</span>` : ""}</b>
        <span class="sc-soft sc-latin"><i>${esc(s.latin)}</i></span>
        ${on ? `<span class="sc-chip on">${icon("check", 16)}In season</span>` : `<span class="sc-chip">${esc(s.season_text)}</span>`}
      </span>
      ${icon("next")}
    </button></li>`;
  };

  const listHTML = () => {
    const key = SPECIES.filter((s) => s.tier !== "more"), more = SPECIES.filter((s) => s.tier === "more");
    const on = key.filter((s) => inSeason(s, now)), off = key.filter((s) => !inSeason(s, now));
    return `
      ${on.length ? `<h3 class="sc-h sc-h-first">In season in ${monthName(now)}</h3><ul class="sc-list">${on.map(row).join("")}</ul>` : ""}
      ${off.length ? `<h3 class="sc-h">Not in season in ${monthName(now)}</h3><ul class="sc-list off">${off.map(row).join("")}</ul>` : ""}
      ${more.length ? `<h3 class="sc-h">More species</h3><ul class="sc-list">${more.map(row).join("")}</ul>` : ""}
      <h3 class="sc-h">Lookalikes</h3>
      <button type="button" class="sc-row sc-looks-row" data-act="looks">
        <span class="sc-ph-none warn" aria-hidden="true">${icon("warn", 36)}</span>
        <span class="sc-row-text"><b>Deadly and toxic lookalikes</b><span class="sc-soft">All ${LOOKALIKES.length}, with photos</span></span>
        ${icon("next")}
      </button>`;
  };

  const looksHTML = () => `
    <section class="sc-danger">
      <h3 class="sc-h danger">${WARN_ICON}Deadly and toxic lookalikes</h3>
      <p>These grow in the same forests and can look like the mushrooms on this map. <b>Some can kill.</b></p>
      <p class="sc-sign"><b>Leave it alone if you see</b> ${AMANITA_SIGNS}</p>
      ${lookRows()}
    </section>`;

  const nowHTML = (sp: Species) => {
    const c = conditions(sp.code);
    const word = (v: number) => (v >= 80 ? "Very good" : v >= 65 ? "Good" : v >= 45 ? "Fair" : "Poor");
    const body = !c || !c.areas.length
      ? `<p class="sc-soft">No scores for this mushroom today.</p>`
      : `<ul class="sc-now-list">${c.areas.map((a) => `<li><b>${word(a.score)}</b> · ${esc(a.where)}</li>`).join("")}</ul>
         ${c.bestDay ? `<p>Best day this week: <b>${esc(c.bestDay.label)}</b> (${word(c.bestDay.score).toLowerCase()}).</p>` : ""}
         <p class="sc-soft">Growing conditions for its habitat. It does not mean the mushroom is there.</p>`;
    const rain = c?.rainSince
      ? `<p>Rain since ${esc(c.rainSince.from)}: <b>${c.rainSince.mm} mm</b> (island average).
          Its crop depends on autumn rain. How much it needs in Cyprus is not known.</p>` : "";
    return `<section class="sc-sec sc-now">
        <h3 class="sc-h">${icon("map")}Conditions for this mushroom now</h3>
        ${body}${rain}
        <button type="button" class="primary-btn sc-map" data-act="show" data-code="${sp.code}"
          data-tip="Close this and colour the map for this mushroom.">${icon("map")}Show it on the map</button>
      </section>`;
  };

  /** "Don't confuse with": own lookalikes where sourced, then all of them folded. Never empty. */
  const confuseHTML = (sp: Species, f: Field | undefined) => {
    const own = LOOK_ORDER.filter((l) => sp.look.includes(l.latin)).map((l) => l.latin);
    return `<section class="sc-sec sc-confuse" aria-labelledby="sc-danger-h">
        <h3 class="sc-h warn" id="sc-danger-h" tabindex="-1">${WARN_ICON}Don't confuse with</h3>
        ${sp.warn ? `<p class="sc-sign"><b>${esc(sp.warn)}</b></p>` : ""}
        ${own.length ? lookRows(own)
          : `<p class="sc-soft">Which lookalikes matter most for this mushroom is not confirmed yet. All of them are below.</p>`}
        <p class="sc-sign-h"><b>Leave it alone if you see:</b></p>
        <ul class="sc-signs">${[...(f?.danger ?? []), ...(f?.danger.some((d) => d.includes("cup (sac)")) ? [] : [cap1(AMANITA_SIGNS)])]
          .map((d) => `<li>${esc(d)}</li>`).join("")}</ul>
        <details class="sc-fold sc-all-looks">
          <summary>All ${LOOKALIKES.length} deadly and toxic lookalikes (${nDeadly} can kill)</summary>
          ${lookRows()}
        </details>
      </section>`;
  };

  const speciesHTML = (sp: Species) => {
    const f = FIELD[sp.code];
    const shots = sets[`sp-${sp.code}`];
    const onNow = inSeason(sp, now);
    const k = monthsUntil(sp, now), nextM = ((now - 1 + k) % 12) + 1;
    return `
      <section class="sc-me">
        <div class="sc-car-wrap">
          ${shots.length ? `<ul class="sc-car" tabindex="0" aria-label="Photos of ${esc(sp.common)}. Swipe for more.">
            ${shots.map((s, i) => `<li><button type="button" class="sc-photo" data-act="view" data-set="sp-${sp.code}" data-i="${i}"
                aria-label="Photo ${i + 1} of ${shots.length}: ${esc(s.name)}. Open larger, with the photo credit.">
              <img src="${esc(s.p.url)}" alt="" loading="${i ? "lazy" : "eager"}" referrerpolicy="no-referrer" />
              <span class="sc-cc" aria-hidden="true">©</span></button></li>`).join("")}
          </ul>` : `<div class="sc-ph-empty">${icon("shroom", 56)}<span>No photo with an open licence yet.</span></div>`}
          ${shots.length > 1 ? `<div class="sc-dots" aria-hidden="true">${shots.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</div>` : ""}
        </div>
        <h3 class="sc-name">${esc(cap1(sp.common))}${sp.rare ? ` <span class="sc-tag">rare</span>` : ""}</h3>
        <p class="sc-sub"><i>${esc(sp.latin)}</i>${sp.local ? ` · local name <b>${esc(sp.local)}</b>${sp.local_confirmed ? "" : `<span class="sc-q" tabindex="0"
          data-tip="Spelling still to confirm with the Cyprus Mycological Association.">?</span>`}` : ""}</p>
      </section>

      ${nowHTML(sp)}

      <section class="sc-sec">
        <h3 class="sc-h">${icon("tree")}Where to look</h3>
        ${f ? `<p class="sc-unchecked">${icon("info", 18)}<span>From public sources, <b>not checked by an expert</b>. Never use it to decide what to eat.</span></p>` : ""}
        <ul class="sc-where">${(f?.where ?? []).map((w) => `<li>${esc(w)}</li>`).join("")}
          <li><b>On our map:</b> ${esc(sp.trees_text)}. ${esc(sp.altitude_text)}.</li></ul>
      </section>

      <section class="sc-sec">
        <h3 class="sc-h">${icon("cal")}When</h3>
        ${monthBar(sp, now)}
        <p class="sc-when ${onNow ? "on" : ""}">${onNow
          ? `${icon("check")}<span><b>In season now</b> (${esc(sp.season_text)}).</span>`
          : `<span><b>Not in season in ${monthName(now)}.</b> Season ${esc(sp.season_text)}: starts in ${monthName(nextM)}.</span>`}</p>
      </section>

      ${f ? `<section class="sc-sec">
        <h3 class="sc-h">${icon("look")}What to look for</h3>
        <p class="sc-unchecked">${icon("info", 18)}<span>From public sources, <b>not checked by an expert</b>. Never use it to decide what to eat.</span></p>
        <dl class="sc-look">${f.look.map(([k, t]) => `<div><dt>${esc(k)}</dt><dd>${esc(t)}</dd></div>`).join("")}</dl>
      </section>` : ""}

      ${confuseHTML(sp, f)}

      <button type="button" class="sc-more" data-act="info">${icon("info", 20)}Sources, photo credits and notes</button>`;
  };

  // ---------------------------------------------------------------- whole screen
  const headHTML = () => {
    const back = `<button type="button" class="sc-round" data-act="list" aria-label="Back to all mushrooms" data-tip="Back to all mushrooms.">${icon("back")}</button>`;
    if (view.kind === "sp") {
      const sp = speciesByCode(view.code)!;
      return `${back}<h2 class="sc-title">${esc(cap1(sp.common))}<span><i>${esc(sp.latin)}</i></span></h2>`;
    }
    if (view.kind === "looks") return `${back}<h2 class="sc-title">Lookalikes<span>Deadly and toxic</span></h2>`;
    return `<h2 class="sc-title">Mushrooms<span>Tap one to learn it</span></h2>`;
  };

  const render = (focus = ".sc-head .sc-round") => {
    const sp = view.kind === "sp" ? speciesByCode(view.code)! : null;
    dlg.innerHTML = `
      <div class="sc-main">
        <header class="sc-head">
          ${headHTML()}
          <button type="button" class="sc-round" data-act="info" aria-label="Sources and credits"
            data-tip="Sources, photo credits, public records in Cyprus and notes.">${icon("info")}</button>
          <button type="button" class="sc-round" data-act="close" aria-label="Close" data-tip="Close and go back to the map.">${icon("close")}</button>
        </header>
        <div class="sc-safety">${WARN_ICON}<span>${SAFETY_LINE}</span></div>
        <div class="sc-body"><div class="sc-page">
          ${sp ? speciesHTML(sp) : view.kind === "looks" ? looksHTML() : listHTML()}
        </div></div>
      </div>
      <div class="sc-layer" hidden></div>`;
    const car = dlg.querySelector<HTMLElement>(".sc-car");
    if (car) {
      const dots = [...dlg.querySelectorAll<HTMLElement>(".sc-dots i")];
      car.addEventListener("scroll", () => {
        const i = Math.round(car.scrollLeft / car.clientWidth);
        dots.forEach((d, j) => d.classList.toggle("on", i === j));
      }, { passive: true });
    }
    dlg.querySelector<HTMLElement>(focus)?.focus({ preventScroll: true });
  };

  // ---------------------------------------------------------------- layers: photo viewer and sources
  const layer = () => dlg.querySelector<HTMLElement>(".sc-layer");
  const openLayer = (html: string, label: string) => {
    const l = layer()!;
    layerOpener = document.activeElement as HTMLElement | null;
    l.innerHTML = html;
    l.setAttribute("role", "dialog");
    l.setAttribute("aria-modal", "true");
    l.setAttribute("aria-label", label);
    l.hidden = false;
    dlg.querySelector<HTMLElement>(".sc-main")!.inert = true;
    l.querySelector<HTMLElement>("[data-act='layer-close']")?.focus();
  };
  const closeLayer = () => {
    const l = layer();
    if (!l || l.hidden) return false;
    l.hidden = true; l.innerHTML = "";
    dlg.querySelector<HTMLElement>(".sc-main")!.inert = false;
    layerOpener?.focus({ preventScroll: true });
    return true;
  };

  let viewerSet = "", viewerI = 0;
  const viewerHTML = () => {
    const shots = sets[viewerSet], s = shots[viewerI];
    return `<div class="sc-viewer">
      <header class="sc-layer-head">
        <h2>${s.sev ? `<span class="sc-sev ${s.sev}">${WARN_ICON}${s.sev === "deadly" ? "Deadly" : "Toxic"}</span> ` : ""}<i>${esc(s.name)}</i>
          ${shots.length > 1 ? `<span class="sc-soft">Photo ${viewerI + 1} of ${shots.length}</span>` : ""}</h2>
        <button type="button" class="sc-round" data-act="layer-close" aria-label="Close the photo">${icon("close")}</button>
      </header>
      <div class="sc-viewer-ph">
        <img src="${esc(s.p.url.replace("/medium.", "/large."))}" alt="Photo of ${esc(s.name)}" referrerpolicy="no-referrer"
          onerror="this.onerror=null;this.src='${esc(s.p.url)}'" />
        ${shots.length > 1 ? `
          <button type="button" class="sc-round sc-prev" data-act="vstep" data-d="-1" aria-label="Previous photo">${icon("back")}</button>
          <button type="button" class="sc-round sc-next" data-act="vstep" data-d="1" aria-label="Next photo">${icon("next")}</button>` : ""}
      </div>
      ${s.note ? `<p class="sc-viewer-note">${esc(s.note)}</p>` : ""}
      <p class="sc-credit"><span>Photo: ${esc(s.p.attribution)}</span>
        <a href="${esc(s.p.page)}" target="_blank" rel="noopener">Open on iNaturalist ↗</a></p>
    </div>`;
  };

  const creditList = (shots: Shot[]) => `<ul class="sc-credits">${shots.map((s) => `<li>
      <img src="${esc(s.p.url)}" alt="" loading="lazy" referrerpolicy="no-referrer" />
      <span><i>${esc(s.name)}</i><br><a href="${esc(s.p.page)}" target="_blank" rel="noopener">${esc(s.p.attribution)}</a></span></li>`).join("")}</ul>`;
  const lookCredits = () => `<details class="sc-fold"><summary>Photo credits for the lookalikes</summary>
      ${creditList(LOOK_ORDER.flatMap((_, i) => sets[`lk${i}`]))}</details>`;

  const recordsHTML = (sp: Species) => {
    const r = sp.records;
    const max = Math.max(1, ...Object.values(r.months));
    const bars = MONTH_SHORT.map((m, i) => {
      const n = r.months[String(i + 1)] ?? 0;
      return `<div class="rec-m${sp.months.includes(i + 1) ? " in" : ""}" data-tip="${m}: ${n} public record${n === 1 ? "" : "s"} in Cyprus.">
        <i style="height:${n ? Math.max(6, (n / max) * 44) : 2}px"></i><span>${m[0]}</span></div>`;
    }).join("");
    return `<h3>Public records in Cyprus</h3>
      <p><b>${r.gbif_total}</b> ${r.gbif_total === 1 ? "record" : "records"} on GBIF, and <b>${r.inat_research}</b>
        expert-checked ${r.inat_research === 1 ? "sighting" : "sightings"} on iNaturalist.</p>
      ${r.gbif_total ? `<div class="rec-chart" aria-label="Public records in Cyprus by month">${bars}</div>` : ""}
      <p class="sc-soft">Cyprus mushrooms are recorded very little, so these numbers are too small to show a season
        or to say where the species grows. You can help by adding your own sightings to iNaturalist.</p>`;
  };

  const infoHTML = () => {
    const head = `<header class="sc-layer-head"><h2>Sources, credits and notes</h2>
      <button type="button" class="sc-round" data-act="layer-close" aria-label="Close">${icon("close")}</button></header>`;
    const foot = `<p class="sc-soft">Links open other websites in a new tab. ${esc(SAFETY_LINE)}</p>`;
    if (view.kind === "sp") {
      const sp = speciesByCode(view.code)!;
      const f = FIELD[sp.code];
      const confirm = [
        !sp.local_confirmed ? `The local name ${sp.local}.` : "",
        "Which lookalikes matter most for this mushroom. Until then, the full list is on every page.",
        "The field notes on this page (researched November 2026).",
        ...(f?.check ?? []),
      ].filter(Boolean);
      return `${head}<div class="sc-info">
        <h3>Still to confirm with the Cyprus Mycological Association</h3>
        <ul class="sc-links">${confirm.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
        <h3>Where the field notes come from</h3>
        <ul class="sc-links">${(f?.src ?? []).map((k) => `<li><a href="${esc(SOURCES[k].url)}" target="_blank" rel="noopener">${esc(SOURCES[k].label)} ↗</a></li>`).join("")}</ul>
        <p class="sc-soft">Season, trees and altitude on the map come from the project brief.</p>
        <h3>How the map uses it</h3>
        <p>Its own habitat (${esc(sp.trees_text)}), water in the ground, soil warmth, mushroom clock and season
          (${esc(sp.season_text)}). These multiply into one score. See "About the data" for the method.</p>
        ${sp.notes.length ? `<ul class="sc-links">${sp.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}
        ${recordsHTML(sp)}
        <h3>Photos</h3>
        <p class="sc-soft">From iNaturalist. Each photo keeps its author and licence.</p>
        ${creditList(sets[`sp-${sp.code}`])}
        ${lookCredits()}
        <h3>Learn more</h3>
        <ul class="sc-links">${sp.records.links.map((l) => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)} ↗</a></li>`).join("")}</ul>
        ${foot}</div>`;
    }
    return `${head}<div class="sc-info">
      <h3>Where this comes from</h3>
      <p>Seasons, trees and altitudes on the map come from the project brief. The field notes on each mushroom page
        come from the sources listed on that page. Photos come from iNaturalist; tap any photo to see its author and licence.</p>
      <h3>Still to confirm with the Cyprus Mycological Association</h3>
      <p>The local names (except kokkinomanitaro), the field notes, and which lookalikes matter most for each mushroom.
        Until then, all ${LOOKALIKES.length} lookalikes are one tap away on every mushroom page.</p>
      <h3>Collecting in Cyprus</h3>
      <ul class="sc-links"><li>Allowed in state forests, but not in nature reserves.</li>
        <li>No rakes or tools that dig. Do not damage the fungus in the ground.</li>
        <li>Leave young mushrooms.</li></ul>
      <p class="sc-soft"><a href="${esc(SOURCES.forests.url)}" target="_blank" rel="noopener">${esc(SOURCES.forests.label)} ↗</a></p>
      ${lookCredits()}
      <p><a href="./about.html">Every photo credit, on the About page</a></p>
      ${foot}</div>`;
  };

  // ---------------------------------------------------------------- actions
  const go = (v: View) => { view = v; render(); dlg.querySelector(".sc-body")?.scrollTo(0, 0); };

  dlg.addEventListener("click", (e) => {
    if (e.target === dlg) { dlg.close(); return; }
    const b = (e.target as Element).closest<HTMLElement>("[data-act]");
    if (!b) return;
    const d = b.dataset;
    switch (d.act) {
      case "close": dlg.close(); break;
      case "jump": e.preventDefault(); dlg.querySelector("#sc-danger-h")?.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); break;
      case "list": go({ kind: "list" }); break;
      case "looks": go({ kind: "looks" }); break;
      case "open": go({ kind: "sp", code: d.code! }); break;
      case "view": viewerSet = d.set!; viewerI = Number(d.i); openLayer(viewerHTML(), "Photo and credit"); break;
      case "vstep": {
        const n = sets[viewerSet].length;
        viewerI = (viewerI + Number(d.d) + n) % n;
        layer()!.innerHTML = viewerHTML();
        layer()!.querySelector<HTMLElement>(`[data-act="vstep"][data-d="${d.d}"]`)?.focus();
        break;
      }
      case "info": openLayer(infoHTML(), "Sources, credits and notes"); break;
      case "layer-close": closeLayer(); break;
      case "show": onShow(d.code!); dlg.close(); break;
    }
  });
  dlg.addEventListener("keydown", (e) => {
    const l = layer();
    if (l && !l.hidden && l.querySelector(".sc-viewer") && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
      l.querySelector<HTMLElement>(`[data-act="vstep"][data-d="${e.key === "ArrowRight" ? 1 : -1}"]`)?.click();
    }
  });
  dlg.addEventListener("cancel", (e) => { if (closeLayer()) e.preventDefault(); });

  return (code?: string) => {
    now = month();
    closeLayer();
    go(code && speciesByCode(code) ? { kind: "sp", code } : { kind: "list" });
    if (!dlg.open) dlg.showModal();
    dlg.querySelector<HTMLElement>(".sc-head .sc-round")?.focus({ preventScroll: true });
  };
}
