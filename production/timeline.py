"""Compute the episode timeline from measured VO durations.

A beat occupies pre + vo + post seconds (or a fixed dur for silent MG beats).
Returns a list of dicts with absolute start/dur and the episode total.
"""

import json
import pathlib
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from episode01_beats import BEATS


def compute(durations_path="assets/vo/durations.json"):
    durs = json.loads(pathlib.Path(durations_path).read_text())
    t = 0.0
    rows = []
    for b in BEATS:
        if b["vo"]:
            vo = durs[b["id"]]
            dur = b["pre"] + vo + b["post"]
            vo_start = t + b["pre"]
        else:
            vo = 0.0
            dur = b["dur"]
            vo_start = None
        rows.append({**b, "start": t, "dur": dur, "vo_dur": vo,
                     "vo_start": vo_start})
        t += dur
    return rows, t


def sections(rows):
    """First-start / last-end per section, in script order."""
    out = {}
    for r in rows:
        s = r["section"]
        if s not in out:
            out[s] = [r["start"], r["start"] + r["dur"]]
        out[s][1] = r["start"] + r["dur"]
    return out


if __name__ == "__main__":
    rows, total = compute()
    for r in rows:
        print(f"{r['start']:7.2f}  {r['id']:8s} {r['section']:7s} "
              f"dur={r['dur']:6.2f} vo={r['vo_dur']:6.2f} shot={r['shot']}")
    print(f"TOTAL {total/60:.2f} min")
