"""Turns per-frame recognitions into stable gestures.

A gesture counts after it was seen for hold_ms with the hands staying still
and ends after release_ms without it, so brief dropouts do not end it.
"""


class Tracker:
    def __init__(self, cfg):
        r = cfg["recognition"]
        self.hold = r["hold_ms"] / 1000
        self.release = r["release_ms"] / 1000
        self.still = r["still_threshold"]
        self.seen = {}      # gesture -> {"since", "last", "points"}
        self.stable = set()

    def update(self, t, present):
        """present: {gesture: (x, y) centre of its hands}. Returns the stable gestures."""
        for gid, center in present.items():
            entry = self.seen.setdefault(gid, {"since": t, "points": []})
            entry["last"] = t
            entry["points"].append((t, center))
            entry["points"] = [(pt, c) for pt, c in entry["points"] if t - pt <= self.hold + 0.1]
        for gid in list(self.seen):
            entry = self.seen[gid]
            if t - entry["last"] > self.release:
                del self.seen[gid]
                self.stable.discard(gid)
            elif gid not in self.stable and t - entry["since"] >= self.hold:
                if self._moved(entry) <= self.still:
                    self.stable.add(gid)
                else:
                    entry["since"] = t   # moving: start counting again
        return set(self.stable)

    @staticmethod
    def _moved(entry):
        xs = [c[0] for _, c in entry["points"]]
        ys = [c[1] for _, c in entry["points"]]
        return max(max(xs) - min(xs), max(ys) - min(ys)) if xs else 0.0
