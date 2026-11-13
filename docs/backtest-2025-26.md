# Backtest: the 2025-26 season (v0.3, step 9)

Run on 2026-11-13 with `uv run python -m shroomy.backtest`.
Numbers: `data/processed/backtest/backtest_2025-26.json` (not in git).

## What we ran

- **Season:** 1 Sep 2025 to 28 Feb 2026 (181 days).
- **Weather:** Open-Meteo historical forecasts, ECMWF IFS model, on **156 points** (one per 9 km of land,
  the model's own grid). About 2,000 free calls.
- **Gap:** the archive has no daily min / max temperature for **29 days** in September 2025.
  We estimated them from the daily mean and each point's usual range. Rain and mean temperature are complete.
- **Squares:** every 4th 250 m square with habitat for at least one species (about 27,000).
- **Species:** all 14 profiles, exactly as on the v0.3 branch.

## The weather: late and cold, as the press said

| Month | Island rain | Mean temp | Bucket fill (median) | Days with 10 mm+ |
|---|---|---|---|---|
| Sep 2025 | 2 mm | 25.6 °C | 3 % | 0 |
| Oct 2025 | 8 mm | 20.9 °C | 1 % | 0 |
| Nov 2025 | 17 mm | 18.9 °C | 3 % | 0 |
| Dec 2025 | 118 mm | 13.2 °C | 64 % | 4 |
| Jan 2026 | 81 mm | 11.0 °C | 76 % | 2 |
| Feb 2026 | 70 mm | 13.0 °C | 68 % | 1 |

- **First soaking rain** (island mean 20 mm in 3 days): **7 December 2025**.
- September to November: almost no rain (27 mm in 3 months).

## What the model said

Share of habitat squares with a **window open**, and the 90th-percentile score, by month:

| Species | Sep-Nov | Dec | Jan | Feb |
|---|---|---|---|---|
| Red pine mushroom | 0 % (score 0-1) | 25 % (71) | 2 % (30) | 33 % (48) |
| Bloody milk cap | 0 % | 0 % (12) | 1 % (10) | 19 % (31) |
| White brittlegill | 0 % | 25 % (31) | 2 % (12) | 29 % (31) |
| Matsutake | 0 % | 22 % (59) | 2 % (32) | 34 % (48) |
| Slippery Jack | 0 % | 25 % (71) | 2 % (30) | 33 % (48) |
| Morels | 0 % | 25 % (28) | 10 % (18) | 26 % (56) |
| Fennel king oyster | 0 % | 32 % (30) | 3 % (15) | 32 % (25) |
| Wood blewit | 0 % | 30 % (68) | 5 % (39) | 39 % (63) |
| Shaggy ink cap | 0 % | 32 % (60) | 3 % (31) | 32 % (51) |
| Desert truffle | 0 % | 46 % (37) | 14 % (20) | 8 % (20) |

### The good news

- **No false "great" autumn.** With almost no rain from September to November, every species stays
  at **zero**. The old v1 score said 86-90 every day. This was fault 1 in the spec, and it is fixed.
- **The season starts with the first soaking rain** (7 Dec), then windows open in mid-to-late December.
  That fits "rain came late and cold".
- **Scores spread out** over days and places (90th percentile from 0 to 71), instead of bunching at the top.

### What looks wrong (to calibrate)

1. **Out-of-season species still open windows.** Bloody milk cap (Sep-Oct) opens in February.
   Morels (Mar-Apr) and desert truffle (spring) open in December. The soft season factor only halves
   the score, and the soil temperature windows are wide. **Fix to try:** a lower season floor for
   strongly seasonal species, or narrower soil temperature windows (S12, S13).
2. **A long January gap.** After the December windows, most squares sit in "recovering" for 21 days,
   even though 81 mm of rain fell in January. **Fix to try:** shorter recovery, or let a big new
   rain end recovery early (E10, profile recovery_days).
3. **Many species behave the same.** Red pine mushroom, slippery Jack and chanterelle give the same
   numbers, because their profiles copy the same group defaults. They need their own data (S13).

## Dated public records (iNaturalist + GBIF, Cyprus, Sep 2025 - Feb 2026)

Only **2 records** for all 14 species in the whole season. Both are **shaggy ink cap**:

| Date | Model at the nearest square | Best within 5 km | Match? |
|---|---|---|---|
| 11 Jan 2026 | score 0, recovering | 14 | **Miss** |
| 19 Feb 2026 | score 20, recovering | 20 | **Miss** |

- Both finds fall in the **"recovering"** gap of problem 2 above. They point the same way:
  recovery after a window is probably too long for this field species.
- **Two records cannot calibrate anything.** Cyprus mushrooms are recorded very little.
  Our own trip log (spec 3.8) will matter much more.

## Next steps (not done here)

- Try the three fixes above, re-run this backtest, and compare.
- Add the 2024-25 season (about 2,000 more free calls) for a second year.
- Fetch Open-Meteo soil temperature instead of the air-temperature estimate (P2).
