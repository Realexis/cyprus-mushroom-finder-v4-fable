"""The mushroom clock: a cycle state machine per square (v0.3 spec 3.2 step 4).

    Dormant -> Primed -> Triggered -> Window open -> (Spent -> Recovering) -> Primed

- Dormant:    soil temperature outside the species window (e.g. summer heat).
- Primed:     temperature is fine, waiting for a soaking rain.
- Triggered:  a soaking rain filled the bucket. Degree-days count up; warm days run the
              clock faster, cold days slower. Dry soil cancels the wait.
              Once the season has started (a window has opened since 1 September), a new
              soaking rain re-opens the window after `rewet_wait_days` instead [LOI19].
- Open:       the growing window. Ends early on dry soil or frost. After window_length_days
              it goes on as a "late window" (lower factor) while the soil stays wet,
              for species with recovery_days = 0 [LOI19: no rest]. Others go to Spent.
- Spent:      just after a full window. Rain does not restart the clock.
- Recovering: rest of recovery_days. Then Primed again.

All per-square arrays are updated together, one day at a time.
"""
import numpy as np

from .soiltemp import degree_days

DORMANT, PRIMED, TRIGGERED, OPEN, SPENT, RECOVERING = range(6)
STATE_NAMES = ["dormant", "primed", "triggered", "open", "spent", "recovering"]


def cycle_factor(state, prog, late, fcfg):
    """Score multiplier for each state. While triggered it rises with the wait's progress (0..1).
    A late window (open past its full length) gets fcfg["late_open"]."""
    table = np.array([fcfg["dormant"], fcfg["primed"], 0.0, fcfg["open"],
                      fcfg["spent"], fcfg["recovering"]])
    f = table[state]
    trig = fcfg["triggered_start"] + (fcfg["triggered_end"] - fcfg["triggered_start"]) * np.clip(prog, 0, 1)
    f = np.where(state == TRIGGERED, trig, f)
    return np.where((state == OPEN) & late, fcfg["late_open"], f)


class Cycle:
    """State of every square. Call step() once per day."""

    def __init__(self, n, temp_ok0, prof, ccfg, started0=None):
        self.state = np.where(temp_ok0, PRIMED, DORMANT).astype("int8")
        self.dd = np.zeros(n)                          # degree-days since the trigger
        self.days = np.zeros(n, "int16")               # days waiting (re-wet) / open / since the window ended
        self.trigger_t = np.full(n, -1, "int16")       # day index of the last trigger rain
        self.started = np.zeros(n, bool) if started0 is None else np.asarray(started0, bool).copy()
        self.quick = np.zeros(n, bool)                 # this wait is a re-wet (season already started)
        self.late = np.zeros(n, bool)                  # open past window_length_days
        self.p, self.c = prof, ccfg

    def progress(self):
        """Wait progress 0..1 (meaningful while Triggered)."""
        rw = max(self.c.get("rewet_wait_days", 2), 1)
        return np.where(self.quick, self.days / rw, self.dd / self.p["wait_dd"])

    def step(self, t, rain_win, fill, tsoil, temp_ok, frost, new_season=False):
        p, c, s0 = self.p, self.c, self.state.copy()
        if new_season:                                  # 1 September: the season memory starts again
            self.started[:] = False
        rest = np.where(temp_ok, PRIMED, DORMANT).astype("int8")   # where a cancelled cycle goes
        trig = (rain_win >= p["trigger_mm"]) & (fill >= c["trigger_min_fill"]) & temp_ok
        new = s0.copy()

        # Dormant / Primed: follow the temperature; a soaking rain starts the clock.
        m = (s0 == DORMANT) | (s0 == PRIMED)
        new[m] = rest[m]
        go = m & trig
        new[go] = TRIGGERED
        self.dd[go] = 0.0
        self.days[go] = 0
        self.quick[go] = self.started[go]

        # Triggered: count degree-days (first flush) or days (re-wet); dry soil cancels.
        m = (s0 == TRIGGERED)
        self.dd[m] += degree_days(tsoil[m], p["base_c"])
        self.days[m] += 1
        abort = m & (fill < c["abort_below_fill"])
        new[abort] = rest[abort]
        ready = np.where(self.quick, self.days >= c.get("rewet_wait_days", 2), self.dd >= p["wait_dd"])
        opens = m & ~abort & ready
        new[opens] = OPEN
        self.days[opens] = 0
        self.late[opens] = False
        self.started[opens] = True
        self.trigger_t[go | (m & trig)] = t                     # newest soaking rain

        # Open: ends early on dry soil or frost (not used up -> Primed). After its full length:
        # a late window while the soil stays wet (recovery_days = 0), else Spent.
        m = s0 == OPEN
        self.days[m] += 1
        early = m & ((fill < c["close_below_fill"]) | frost)
        new[early] = rest[early]
        self.late[early] = False
        full = m & ~early & (self.days >= p["window_days"])
        if p["recovery_days"] > 0:
            new[full] = SPENT
            self.days[full] = 0
        else:
            self.late[full] = True

        # Spent, then Recovering, counted in days since the window ended.
        m = (s0 == SPENT) | (s0 == RECOVERING)
        self.days[m] += 1
        new[(s0 == SPENT) & (self.days >= c["spent_days"])] = RECOVERING
        back = m & (self.days >= p["recovery_days"])
        new[back] = rest[back]
        self.days[back] = 0

        self.state = new
        return new


def run_cycle(rain_win, fill, tsoil, temp_ok, frost, prof, ccfg, new_season=None, started0=None):
    """Whole run. Inputs (squares, days); new_season: (days,) bool, True on 1 September.
    Returns dict of (squares, days) arrays."""
    n, nd = fill.shape
    cyc = Cycle(n, temp_ok[:, 0], prof, ccfg, started0)
    ns = np.zeros(nd, bool) if new_season is None else np.asarray(new_season, bool)
    out = {"state": np.empty((n, nd), "int8"), "dd": np.empty((n, nd), "float32"),
           "days": np.empty((n, nd), "int16"), "trigger_t": np.empty((n, nd), "int16"),
           "prog": np.empty((n, nd), "float32"), "late": np.empty((n, nd), bool),
           "started": np.empty((n, nd), bool)}
    for t in range(nd):
        out["state"][:, t] = cyc.step(t, rain_win[:, t], fill[:, t], tsoil[:, t], temp_ok[:, t], frost[:, t], ns[t])
        out["dd"][:, t] = cyc.dd
        out["days"][:, t] = cyc.days
        out["trigger_t"][:, t] = cyc.trigger_t
        out["prog"][:, t] = cyc.progress()
        out["late"][:, t] = cyc.late
        out["started"][:, t] = cyc.started
    out["factor"] = cycle_factor(out["state"], out["prog"], out["late"], ccfg["factor"]).astype("float32")
    return out
