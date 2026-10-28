"""Recognises the user's own gestures by comparing with their recordings.

samples.json: {"g…": {"hands": {"Left": [[…], …], "Right": [[…], …]}}}
A gesture recorded with one hand only matches that hand; one recorded with
both hands needs both. MediaPipe's left/right labels may be swapped by the
mirror image; what matters is that they are consistent.

A hand (or pair) belongs to the gesture with the nearest recording, if that
is close enough and clearly closer than any other gesture for the same hands.
Two-hand gestures win over one-hand gestures on the same hands.
"""

import numpy as np

from . import features

MIN_SAMPLES = 10
ACCEPT = 0.6      # max. distance to the nearest recording (feature units)
MARGIN = 0.75     # nearest gesture must be this much closer than the second


class Templates:
    def __init__(self, samples):
        self.components = {}
        for gid, value in samples.items():
            if not features.current(value) or value.get("kind") == "swipe":
                continue
            hands = {label: np.asarray(v, dtype=np.float32) for label, v in value.get("hands", {}).items()
                     if len(v) >= MIN_SAMPLES}
            if hands:
                self.components[gid] = hands

    @staticmethod
    def _distance(recorded, vec):
        return float(np.linalg.norm(recorded - vec, axis=1).min())

    def match(self, hands):
        """hands: {label: feature vector} -> {gesture: [labels]} recognised now."""
        groups = {}
        for gid, comps in self.components.items():
            if not all(label in hands for label in comps):
                continue
            d = max(self._distance(x, hands[label]) for label, x in comps.items())
            if d <= ACCEPT:
                groups.setdefault(frozenset(comps), []).append((d, gid))
        found = []
        for labels, items in groups.items():
            items.sort()
            if len(items) > 1 and items[0][0] > MARGIN * items[1][0]:
                continue   # two gestures fit about equally: ambiguous
            found.append((-len(labels), items[0][0], items[0][1], labels))
        result, used = {}, set()
        for _, _, gid, labels in sorted(found):
            if not labels & used:
                result[gid] = sorted(labels)
                used |= labels
        return result

    def lookalikes(self, gid):
        """Gestures for the same hands closer than ACCEPT: easy to mix up."""
        own = self.components.get(gid)
        if not own:
            return []
        out = []
        for other, comps in self.components.items():
            if other == gid or set(comps) != set(own):
                continue
            d = max(float(np.median(np.linalg.norm(own[label][:, None] - comps[label][None], axis=2).min(axis=1)))
                    for label in own)
            if d < ACCEPT:
                out.append(other)
        return out
