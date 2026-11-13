// v0.3 scores: one small file per species (and per general map) colours the 250 m squares
// through MapLibre feature-state, so the map tiles never carry 14 species x 8 days of numbers.
// Layouts: pipeline/shroomy/export/web_v03.py.
import type { Map as MlMap } from "maplibre-gl";

/** General score files: no species with habitat here is in season that day (export/web_v03.py). */
export const NO_SPECIES_IN_SEASON = 255;

/** sp_<key>.bin: which squares have a score, and the score per day (0-100; 255 = none in season). */
export class Scores {
  private constructor(readonly idx: Uint32Array, readonly sc: Uint8Array, readonly days: number) {}
  static async load(url: string): Promise<Scores> {
    const buf = await fetch(url).then((r) => { if (!r.ok) throw new Error(url); return r.arrayBuffer(); });
    const [n, days] = new Uint32Array(buf, 0, 2);
    return new Scores(new Uint32Array(buf, 8, n), new Uint8Array(buf, 8 + 4 * n, n * days), days);
  }
  /** Row of square i, or -1 (no habitat for this key). Binary search: idx is sorted. */
  row(i: number): number {
    let lo = 0, hi = this.idx.length - 1;
    while (lo <= hi) {
      const m = (lo + hi) >> 1, v = this.idx[m];
      if (v === i) return m;
      if (v < i) lo = m + 1; else hi = m - 1;
    }
    return -1;
  }
  /** Score 0-100, or null: no habitat, or no species in season here that day (general maps: 255). */
  score(i: number, day: number): number | null {
    const r = this.row(i);
    if (r < 0) return null;
    const v = this.sc[r * this.days + day];
    return v === NO_SPECIES_IN_SEASON ? null : v;
  }
}

/** sp_<key>_info.bin: the parts (0..1) and plain numbers behind each score. Same rows as Scores. */
export class ScoreInfo {
  private constructor(private p: Uint8Array, private inp: Int16Array, private days: number,
                      readonly np: number, readonly ni: number) {}
  static async load(url: string): Promise<ScoreInfo> {
    const buf = await fetch(url).then((r) => { if (!r.ok) throw new Error(url); return r.arrayBuffer(); });
    const [n, days, np, ni] = new Uint32Array(buf, 0, 4);
    const pBytes = n * days * np;
    const iStart = 16 + pBytes + (pBytes % 2);
    return new ScoreInfo(new Uint8Array(buf, 16, pBytes), new Int16Array(buf, iStart, n * days * ni), days, np, ni);
  }
  parts(row: number, d: number): number[] {
    const o = (row * this.days + d) * this.np;
    return [...this.p.subarray(o, o + this.np)].map((x) => x / 100);
  }
  inputs(row: number, d: number): number[] {
    const o = (row * this.days + d) * this.ni;
    return [...this.inp.subarray(o, o + this.ni)].map((x) => x / 10);
  }
}

/** Loads score files once and paints the current one onto the "cells" squares. */
export class ScoreStore {
  private scores = new Map<string, Promise<Scores | null>>();
  private ready = new Map<string, Scores | null>();
  private infos = new Map<string, Promise<ScoreInfo | null>>();
  private infoReady = new Map<string, ScoreInfo | null>();
  private painted: { key: string; day: number } | null = null;
  private wanted: { key: string; day: number } | null = null;
  private src: unknown = null;                    // the "cells" source we painted (a new style = a new one)

  constructor(private url: (file: string) => string) {}

  load(key: string): Promise<Scores | null> {
    let p = this.scores.get(key);
    if (!p) {
      p = Scores.load(this.url(`data/sp_${key}.bin`)).catch(() => null);
      p.then((s) => this.ready.set(key, s));
      this.scores.set(key, p);
    }
    return p;
  }
  /** Already loaded (else undefined: call load first). */
  get(key: string): Scores | null | undefined { return this.ready.get(key); }

  loadInfo(key: string): Promise<ScoreInfo | null> {
    let p = this.infos.get(key);
    if (!p) {
      p = ScoreInfo.load(this.url(`data/sp_${key}_info.bin`)).catch(() => null);
      p.then((s) => this.infoReady.set(key, s));
      this.infos.set(key, p);
    }
    return p;
  }
  info(key: string): ScoreInfo | null | undefined { return this.infoReady.get(key); }

  /** Forget what is painted (after the map style, and so the source, was rebuilt). */
  reset() { this.painted = null; this.wanted = null; }

  /** Colour the squares for `key` on `day` (feature-state "v"; squares without a score stay clear). */
  async paint(map: MlMap, key: string, day: number) {
    const want = { key, day };
    this.wanted = want;
    const s = await this.load(key);
    const cur = map.getSource("cells");
    if (this.wanted !== want || !s || !cur) return;                        // a newer request won
    if (cur !== this.src) { this.painted = null; this.src = cur; }        // rebuilt source: paint it all again
    if (this.painted?.key === key && this.painted.day === day) return;
    const src = { source: "cells", sourceLayer: "cells" };
    // Clear the squares of the previous file by setting them empty. (removeFeatureState would be
    // applied AFTER the new values in the same frame and wipe them.)
    const prev = this.painted && this.painted.key !== key ? this.ready.get(this.painted.key) : null;
    if (prev) for (let r = 0; r < prev.idx.length; r++) map.setFeatureState({ ...src, id: prev.idx[r] }, { v: null });
    for (let r = 0; r < s.idx.length; r++) {
      const v = s.sc[r * s.days + day];
      map.setFeatureState({ ...src, id: s.idx[r] }, { v: v === NO_SPECIES_IN_SEASON ? null : v });   // clear: none in season
    }
    this.painted = { key, day };
  }
}
