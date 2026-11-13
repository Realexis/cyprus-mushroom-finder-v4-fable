"""The daily run (GitHub Actions at 04:00 UTC, or by hand).

1. Fetch weather: 3 past days + 8 forecast days (cheap). If the history has a gap,
   fetch the full 31 past days once instead.
2. Merge into the rolling history and assemble today's 31+8 day run, plus the engine's
   season run (from 1 September, as far as the history goes: audit step 4).
3. Score today + 7 days, export the PUBLIC site data + summary.json.

If the weather source is down, this exits with an error and the site keeps
yesterday's data — the site then shows "Data delayed" by itself.

Run:  uv run python -m shroomy.daily [--public] [--full]
"""
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config
from .export import web
from .weather import history
from .weather.fetch import fetch_main


def main():
    cfg = config.load("weather")["open_meteo"]
    today = datetime.now(ZoneInfo(cfg["timezone"])).date()
    past, fc = cfg["past_days"], cfg["forecast_days"]
    recent = 3                                   # past days fetched every day
    full = "--full" in sys.argv or not history.complete_for(today, past, skip_recent=recent)
    print(f"Daily run for {today} · {'FULL 31-day' if full else 'incremental 3-day'} weather fetch")

    fetched = fetch_main(today, past_days=past if full else recent, out_name="fetch")
    history.merge(fetched)
    run = config.PROCESSED / "weather" / f"run_{today.isoformat()}.npz"
    history.assemble(today, past, fc, run)
    season_run = config.PROCESSED / "weather" / f"season_{today.isoformat()}.npz"
    _, season_days = history.assemble_season(today, past, fc, season_run)
    print(f"Engine memory: {season_days} past days (season starts {history.season_start(today)})")
    web.build(run, private="--public" not in sys.argv, engine_run=season_run)

    status = {"ok": True, "day": today.isoformat(), "full_fetch": full, "engine_past_days": season_days}
    (config.PROCESSED / "daily_status.json").write_text(json.dumps(status))
    print("Done:", status)


if __name__ == "__main__":
    main()
