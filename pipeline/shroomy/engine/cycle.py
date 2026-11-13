"""The mushroom clock: a cycle state machine per square (v0.3 spec 3.2 step 4).

    Dormant -> Primed -> Triggered -> Window open -> Spent -> Recovering -> Primed

- Dormant:    soil temperature outside the species window (e.g. summer heat).
- Primed:     temperature is fine, waiting for a soaking rain.
- Triggered:  a soaking rain filled the bucket. Degree-days count up; warm days run the
              clock faster, cold days slower. Dry soil cancels the wait.
- Open:       the growing window. Lasts window_length_days, or ends early on dry soil or frost.
- Spent:      just after a full window. Rain does not restart the clock.
- Recovering: rest of recovery_days. Then Primed again.

All per-square arrays are updated together, one day at a time.
"""
import numpy as np

from .soiltemp import degree_days

DORMANT, PRIMED, TRIGGERED, OPEN, SPENT, RECOVERING = range(6)
STATE_NAMES = ["dormant", "primed", "triggered", "open", "spent", "recovering"]


def cycle_factor(state, dd, wait_dd, fcfg):
    """Score multiplier for each state. While triggered it rises with degree-day progress."""
    table = np.array([fcfg["dormant"], fcfg["primed"], 0.0, fcfg["open"],
                      fcfg["spent"], fcfg["recovering"]])
    f = table[state]
    prog = np.clip(dd / wait_dd, 0, 1)
    trig = fcfg["triggered_start"] + (fcfg["triggered_end"] - fcfg["triggered_start"]) * prog
    return np.where(state == TRIGGERED, trig, f)


class Cycle:
    """State of every square. Call step() once per day."""

    def __init__(self, n, temp_ok0, prof, ccfg):
        self.state = np.where(temp_ok0, PRIMED, DORMANT).astype("int8")
        self.dd = np.zeros(n)                          # degree-days since the trigger
        self.days = np.zeros(n, "int16")               # days open / days since the window ended
        self.trigger_t = np.full(n, -1, "int16")       # day index of the last trigger rain
        self.p, self.c = prof, ccfg

    def step(self, t, rain_win, fill, tsoil, temp_ok, frost):
        p, c, s0 = self.p, self.c, self.state.copy()
        rest = np.where(temp_ok, PRIMED, DORMANT).astype("int8")   # where a cancelled cycle goes
        trig = (rain_win >= p["trigger_mm"]) & (fill >= c["trigger_min_fill"]) & temp_ok
        new = s0.copy()

        # Dormant / Primed: follow the temperature; a soaking rain starts the clock.
        m = (s0 == DORMANT) | (s0 == PRIMED)
        new[m] = rest[m]
        go = m & trig
        new[go] = TRIGGERED
        self.dd[go] = 0.0

        # Triggered: count degree-days; dry soil cancels; enough degree-days opens the window.
        m = s0 == TRIGGERED
        self.dd[m] += degree_days(tsoil[m], p["base_c"])
        abort = m & (fill < c["abort_below_fill"])
        new[abort] = rest[abort]
        opens = m & ~abort & (self.dd >= p["wait_dd"])
        new[opens] = OPEN
        self.days[opens] = 0
        self.trigger_t[go | (m & trig)] = t                     # newest soaking rain

        # Open: ends early on dry soil or frost (not used up -> Primed), or after its full length.
        m = s0 == OPEN
        self.days[m] += 1
        early = m & ((fill < c["close_below_fill"]) | frost)
        new[early] = rest[early]
        full = m & ~early & (self.days >= p["window_days"])
        new[full] = SPENT
        self.days[full] = 0

        # Spent, then Recovering, counted in days since the window ended.
        m = (s0 == SPENT) | (s0 == RECOVERING)
        self.days[m] += 1
        new[(s0 == SPENT) & (self.days >= c["spent_days"])] = RECOVERING
        back = m & (self.days >= p["recovery_days"])
        new[back] = rest[back]
        self.days[back] = 0

        self.state = new
        return new


def run_cycle(rain_win, fill, tsoil, temp_ok, frost, prof, ccfg):
    """Whole run. Inputs (squares, days). Returns dict of (squares, days) arrays."""
    n, nd = fill.shape
    cyc = Cycle(n, temp_ok[:, 0], prof, ccfg)
    out = {"state": np.empty((n, nd), "int8"), "dd": np.empty((n, nd), "float32"),
           "days": np.empty((n, nd), "int16"), "trigger_t": np.empty((n, nd), "int16")}
    for t in range(nd):
        out["state"][:, t] = cyc.step(t, rain_win[:, t], fill[:, t], tsoil[:, t], temp_ok[:, t], frost[:, t])
        out["dd"][:, t] = cyc.dd
        out["days"][:, t] = cyc.days
        out["trigger_t"][:, t] = cyc.trigger_t
    out["factor"] = cycle_factor(out["state"], out["dd"], prof["wait_dd"], ccfg["factor"]).astype("float32")
    return out
