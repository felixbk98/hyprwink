"""Where on the screens the user is looking: a gaze ray in 3D.

MediaPipe's face model gives the head as a 3D transform in centimetres
(rotation R and position t in camera space, the camera looking along -z)
and the iris inside each eye. The gaze ray starts at the head position;
its direction is the head's forward direction turned by the eyes (iris
offset × gain). Where it meets the screen plane (taken as the plane of the
camera, z = 0) gives a point in centimetres, which an affine map turns into
Hyprland layout coordinates.

Sitting elsewhere moves the start of the ray, which is physically taken
into account. The calibration only learns what stays fixed: the eye gains
and, for every monitor on its own (they may be tilted or stand apart), the
map from the camera plane to that monitor.

Clean data: frames with closed eyes (blinks) are skipped, the first part of
every calibration dot (eyes still moving) and outliers are dropped, and the
gaze point is the median of the last frames, so single jumps do not count.
"""

import numpy as np

# Landmarks of the face model (478 points with iris).
EYES = ((33, 133, 468), (263, 362, 473))   # (corner, corner, iris centre)
MEDIAN = 7           # frames in the running median of the gaze point (~0.3 s)
BLINK = 0.45         # eye-blink blendshape above this: eyes closed
SETTLE = 0.25        # share of each calibration dot dropped at its start


def blinking(result):
    if not result.face_blendshapes:
        return False
    scores = {c.category_name: c.score for c in result.face_blendshapes[0]}
    return max(scores.get("eyeBlinkLeft", 0), scores.get("eyeBlinkRight", 0)) > BLINK


def features(result, aspect):
    """[R (9), t (3), iris x, iris y], "blink" while the eyes are closed, or
    None without a face."""
    if not result.face_landmarks or not result.facial_transformation_matrixes:
        return None
    if blinking(result):
        return "blink"
    pts = np.array([(p.x * aspect, p.y) for p in result.face_landmarks[0]])
    if len(pts) < 478:
        return None
    m = np.asarray(result.facial_transformation_matrixes[0])
    # Iris position inside the eye, along the face's left-right axis and across.
    across = pts[263] - pts[33]
    across /= np.linalg.norm(across) or 1e-6
    down = np.array([-across[1], across[0]])
    iris = []
    for a, b, centre in EYES:
        width = np.linalg.norm(pts[b] - pts[a]) or 1e-6
        offset = pts[centre] - (pts[a] + pts[b]) / 2
        iris.append((offset @ across / width, offset @ down / width))
    ix, iy = np.mean(iris, axis=0)
    return np.concatenate([m[:3, :3].ravel(), m[:3, 3], [ix, iy]])


def hits(feats, eyes):
    """Points (cm) where the gaze rays meet the camera plane.
    feats: N×14; eyes: (gain x, gain y, offset x, offset y) in radians."""
    feats = np.atleast_2d(feats)
    r = feats[:, :9].reshape(-1, 3, 3)
    t = feats[:, 9:12]
    gx, gy, bx, by = eyes
    yaw = gx * feats[:, 12] + bx
    pitch = gy * feats[:, 13] + by
    local = np.stack([np.sin(yaw) * np.cos(pitch), np.sin(pitch), np.cos(yaw) * np.cos(pitch)], axis=1)
    d = np.einsum("nij,nj->ni", r, local)
    dz = np.where(np.abs(d[:, 2]) < 1e-3, 1e-3, d[:, 2])
    s = -t[:, 2] / dz
    return t[:, :2] + s[:, None] * d[:, :2]


def _affine(h, y):
    """Least-squares map [hx, hy, 1] -> layout px, and the residuals."""
    a = np.hstack([h, np.ones((len(h), 1))])
    m, *_ = np.linalg.lstsq(a, y, rcond=None)
    return m, a @ m - y


def clean(samples):
    """Per calibration dot and round: drop the start (eyes still moving) and
    outliers (iris far from the dot's median)."""
    by_dot = {}
    for s in samples:
        by_dot.setdefault((s[1], s[2]["name"], s[2]["round"]), []).append(s)
    kept = []
    for items in by_dot.values():
        items = items[int(len(items) * SETTLE):]
        if len(items) < 3:
            continue
        iris = np.array([f[12:14] for f, _, _ in items])
        dev = np.linalg.norm(iris - np.median(iris, axis=0), axis=1)
        limit = 3 * (np.median(dev) or 1e-6)
        kept += [s for s, d in zip(items, dev) if d <= limit]
    return kept


def _maps(h, y, monitors):
    """One affine map per monitor; all residuals."""
    maps, res = {}, np.zeros_like(y)
    for name in set(monitors):
        sel = np.array([m == name for m in monitors])
        maps[name], res[sel] = _affine(h[sel], y[sel])
    return maps, res


def fit(samples):
    """samples: [(features, (x, y), {"name", "rect"})] -> model dict, median
    error in px. The eye gains are found by a small Gauss-Newton search; for
    each guess the best map per monitor follows in closed form."""
    samples = clean(samples)
    x = np.array([f for f, _, _ in samples])
    y = np.array([p for _, p, _ in samples], dtype=np.float64)
    monitors = [m["name"] for _, _, m in samples]
    rects = {m["name"]: m["rect"] for _, _, m in samples}

    def residual(p):
        return _maps(hits(x, p), y, monitors)[1].ravel()

    p = np.array([1.5, 1.5, 0.0, 0.0])
    for _ in range(40):
        r = residual(p)
        jac = np.empty((len(r), 4))
        for i in range(4):
            step = np.zeros(4)
            step[i] = 1e-4
            jac[:, i] = (residual(p + step) - r) / 1e-4
        delta = np.linalg.solve(jac.T @ jac + 1e-3 * np.eye(4) * len(r), -jac.T @ r)
        p += delta
        if np.abs(delta).max() < 1e-5:
            break
    h = hits(x, p)
    maps, res = _maps(h, y, monitors)
    overall, _ = _affine(h, y)
    model = {"eyes": p.tolist(), "map": overall.tolist(),
             "monitors": {n: {"rect": rects[n], "map": maps[n].tolist()} for n in maps}}
    return model, float(np.median(np.linalg.norm(res, axis=1)))


def _outside(point, rect):
    x, y, w, h = rect
    return np.hypot(max(x - point[0], 0, point[0] - x - w), max(y - point[1], 0, point[1] - y - h))


class Gaze:
    def __init__(self, model):
        self.eyes = np.asarray(model["eyes"])
        self.map = np.asarray(model["map"])
        self.monitors = [(m["rect"], np.asarray(m["map"])) for m in model["monitors"].values()]
        self.recent = []
        self.point = None

    def update(self, feats):
        """Screen point for this frame's features (None: no face). While
        blinking the last point stays."""
        if feats is None:
            self.recent, self.point = [], None
            return None
        if isinstance(feats, str):
            return self.point
        h = np.append(hits(feats, self.eyes)[0], 1)
        # Each monitor's map gives a point; the monitor whose point lies on
        # (or nearest to) itself is the one looked at. Several fit: the one
        # nearest to the overall map decides.
        rough = h @ self.map
        candidates = [(_outside(h @ m, rect), float(np.linalg.norm(h @ m - rough)), tuple(h @ m))
                      for rect, m in self.monitors]
        raw = np.array(min(candidates)[2])
        self.recent = (self.recent + [raw])[-MEDIAN:]
        self.point = np.median(self.recent, axis=0)
        return self.point
