# Species profiles (v0.3)

One file per species. The engine (`pipeline/shroomy/engine/`) runs every profile on every
250 m square. **All species numbers live here, never in the engine code.**

- Every number is a **starting guess from research**. Each profile says so in a comment.
- Files starting with `_` are templates and are skipped.
- Shared engine settings (bucket, cycle factors) are in `config/engine.yaml`.
- The format is checked by `shroomy.engine.profile.check()`: a missing field stops the run.

## Fields (spec 3.4)

| Field | What it means |
|---|---|
| `code`, `english_name`, `latin_name` | Names. `local_name: {name, confirmed}`: mark "to confirm". |
| `group` | pine_partner, oak_partner, litter_recycler, field_recycler, fennel_root, burn, underground |
| `tier`, `rare`, `confidence` | key or more; true/false; low or medium |
| `host_trees` | tree name: weight 0-1 (calabrian_pine, black_pine, golden_oak, other_broadleaf, kermes_oak) |
| `land_cover` | optional, land-cover share: weight (grass_frac, clc_pasture, clc_sclerophyll, ...) |
| `min_tree_cover_pct` | optional, else `config/soil.yaml` (30 %) |
| `altitude_range` | [low, high] metres, soft edges |
| `trigger_mm` | soaking rain over 3 days that starts the clock |
| `wait_degree_days` | `{total, base_c}`: warmth needed after the trigger |
| `soil_temp_window` | `{min, best, max}` in C; `best` can be [low, high] |
| `window_length_days`, `recovery_days` | how long a window lasts; rest after a full window |
| `season_prior` | month: 0-1. 0 becomes 0.5, 1 stays 1 (soft prior) |
| `extra_cues` | e.g. `needs_burn: true`. Unknown cues are kept but do nothing yet |
| `soil_pref` | `{ph, texture, rock, weight}`. ph: acid/neutral/alkaline/any/unknown. weight 0.8-1.0 |
| `lookalikes` | 2-3 lookalikes specific to this species |
| `sources` | where each number came from |
| `water_fit` | optional `{zero_at_fill, full_at_fill}`, else `config/engine.yaml` |
