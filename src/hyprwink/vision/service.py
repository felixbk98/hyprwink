"""Vision service: webcam → hand landmarks → the user's gestures → core,
and face → gaze point → core.

Also serves preview frames, records new gestures and calibrates the gaze
for the window.
"""

import os

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import glob
import logging
import shutil
import threading
import time
from collections import Counter

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from .. import config, gestures, ipc, paths, settings
from . import drag, features, gaze, motion
from .templates import MIN_SAMPLES, Templates
from .tracker import Tracker

log = logging.getLogger("hyprwink.vision")

PREVIEW_WIDTH = 640
PHOTO_SIZE = 320
CLIP_SIZE = 240




class Vision:
    def __init__(self):
        self.cfg = config.load_config()
        self.tracker = Tracker(self.cfg)
        self.recorder = None
        self.record_stop = threading.Event()    # set: the recording is cancelled
        self.segmenter = motion.Segmenter()
        self.motion_shown = None    # (gesture, hands, until): a recognised movement in the preview
        self.active = {}
        self.camera = True
        self.off_sent = 0.0
        self.load_samples()
        self.paused = False
        self.previews = []
        self.lock = threading.Lock()
        self.core = None
        self.fps = 0.0
        self._create_landmarker()
        self.face = None            # face model, only loaded for gaze
        self.gaze_samples = None    # calibration in progress: [(features, point)]
        self.gaze_target = None
        self.gaze_rounds = None
        self.load_gaze()

    def load_samples(self):
        gestures.load()                  # the example gestures on the first start
        self.samples = config.load_json(paths.SAMPLES_FILE, {})
        self.templates = Templates(self.samples)
        self.motions = motion.Motions(self.samples)
        self.drags = drag.Drags(self.samples)

    def load_gaze(self):
        """Gaze is on when switched on in the settings and calibrated."""
        model = config.load_json(paths.GAZE_FILE, {}).get("model")
        s = settings.load()
        # Also computed for the dot alone ("Blickpunkt anzeigen").
        on = s["gaze"] or s["show_gaze"]
        self.gaze = gaze.Gaze(model) if model and on else None

    def _face(self, image, ts, aspect):
        if self.face is None:
            options = vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(paths.FACE_MODEL)),
                running_mode=vision.RunningMode.VIDEO, num_faces=1,
                output_facial_transformation_matrixes=True, output_face_blendshapes=True)
            self.face = vision.FaceLandmarker.create_from_options(options)
        return gaze.features(self.face.detect_for_video(image, ts), aspect)

    def cleanup(self):
        """Remove recordings, photos and clips no saved gesture refers to
        (e.g. after a crash in the middle of recording)."""
        keep = {g["id"] for g in gestures.load()["gestures"]}
        if self.recorder is not None:
            return
        orphans = [gid for gid in self.samples if gid not in keep]
        for gid in orphans:
            self.samples.pop(gid)
        if orphans:
            config.save_json(paths.SAMPLES_FILE, self.samples)
            self.load_samples()
        if paths.PHOTO_DIR.exists():
            for item in paths.PHOTO_DIR.iterdir():
                gid = item.name.removesuffix(".jpg").removesuffix("-clip")
                if gid not in keep:
                    shutil.rmtree(item) if item.is_dir() else item.unlink()

    def _create_landmarker(self):
        r = self.cfg["recognition"]
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(paths.HAND_MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=r["min_detection_confidence"],
            min_hand_presence_confidence=r["min_detection_confidence"],
            min_tracking_confidence=r["min_tracking_confidence"],
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)

    # ------------------------------------------------------------------ camera

    def _device(self):
        device = self.cfg["camera"]["device"]
        if device == "auto":
            found = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
            device = found[0] if found else "/dev/video0"
        return device

    def _open_camera(self):
        c = self.cfg["camera"]
        cap = cv2.VideoCapture(self._device(), cv2.CAP_V4L2)
        # An unplugged camera must not block a read for long.
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1000)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, c["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, c["height"])
        cap.set(cv2.CAP_PROP_FPS, c["fps"])
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def run(self):
        self.cleanup()
        threading.Thread(target=self._core_link, daemon=True).start()
        ipc.Server(paths.VISION_SOCKET, self._handle_client).start()
        start = time.monotonic()
        last_ts = -1
        while True:
            if self.paused:
                # Switched off: the camera is released (its light goes out).
                self._camera_off()
                time.sleep(0.2)
                continue
            cap = self._open_camera()
            if not cap.isOpened():
                self._camera_lost()
                time.sleep(2)
                continue
            frames, fps_since = 0, time.monotonic()
            while not self.paused:
                ok, frame = cap.read()
                if not ok:
                    self._camera_lost()
                    break
                self.camera = True
                now = time.monotonic()
                ts = max(int((now - start) * 1000), last_ts + 1)
                last_ts = ts
                try:
                    self._process(frame, now, ts)
                except Exception:
                    log.exception("frame failed")
                frames += 1
                if now - fps_since >= 1:
                    self.fps = frames / (now - fps_since)
                    frames, fps_since = 0, now
            cap.release()
            if not self.paused:
                time.sleep(1)

    # --------------------------------------------------------------- per frame

    def _process(self, frame, now, ts):
        if self.cfg["camera"]["mirror"]:
            frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(image, ts)
        # Client threads may replace these at any time: read each once.
        estimator, samples, target, recorder = self.gaze, self.gaze_samples, self.gaze_target, self.recorder
        point = None
        if estimator is not None or samples is not None:
            feats = self._face(image, ts, w / h)
            if samples is not None and target is not None and not (feats is None or isinstance(feats, str)):
                samples.append((feats, *target))
            if estimator is not None:
                point = estimator.update(feats)
        hands = self._hands(result, w / h)
        if recorder is not None:
            self._record(recorder, now, hands, frame)

        # Movements count once, in the frame they end.
        moved = {}
        if self.motions:
            done = self.segmenter.update(now, hands)
            movement = motion.describe(done) if done else None
            gid = self.motions.match(movement) if movement else None
            if gid:
                moved[gid] = {}
                self.motion_shown = (gid, sorted(movement), now + 0.8)
        # Grab – drag – release (drag.py): counts on the release, with its direction.
        released = self.drags.update(now, hands) if self.drags else None
        if released:
            moved[released["gesture"]] = {"direction": released["direction"], "x": released["x"]}
        # A hand cut off by the image's edge (being lowered, resting below)
        # makes no gesture, nor does one while dragging and shortly after
        # (releasing passes through other hand shapes).
        busy = self.drags and self.drags.busy(now)
        found = {} if busy else self.templates.match({label: hand["vector"] for label, hand in hands.items()
                                                      if not features.at_edge(hand["img"])})
        present = {gid: tuple(np.mean([hands[label]["center"] for label in labels], axis=0))
                   for gid, labels in found.items()}
        stable = self.tracker.update(now, present)
        gestures = {gid: {} for gid in stable}
        self.active = {gid: found.get(gid) for gid in stable}
        gestures.update(moved)
        grabbed = self.drags.grabbed() if self.drags else None
        if grabbed:
            self.active[grabbed[0]] = [grabbed[1]]     # shown on the hand while dragging
        shown = self.motion_shown
        if shown and now < shown[2]:
            self.active[shown[0]] = shown[1]
        self._send_core({"type": "frame", "t": now, "gestures": gestures,
                         "gaze": None if point is None else [float(point[0]), float(point[1])]})
        if self.previews:
            self._send_preview(frame, hands, gestures)

    def _camera_lost(self, off=False):
        """Tell everyone the camera is gone (unplugged, or switched off while
        paused), instead of showing a still image."""
        if self.camera and not off:
            log.warning("camera %s not available", self._device())
        self.camera = False
        self.tracker.stable.clear()
        self.tracker.seen.clear()
        self._send_core({"type": "frame", "t": time.monotonic(), "gestures": {}, "camera": off})
        with self.lock:
            for preview in self.previews:
                preview.put({"type": "preview", "camera": False, "off": off})

    def _camera_off(self):
        """Paused: repeat the "off" state now and then for newly opened windows."""
        now = time.monotonic()
        if now - self.off_sent > 1:
            self.off_sent = now
            self._camera_lost(off=True)

    def _hands(self, result, aspect):
        """{"Left"|"Right": hand}; two hands with the same label are told apart
        by their position in the mirrored image."""
        found = []
        for i, lms in enumerate(result.hand_landmarks):
            img = np.array([[p.x, p.y] for p in lms])
            world = np.array([[p.x, p.y, p.z] for p in result.hand_world_landmarks[i]])
            found.append({
                "label": result.handedness[i][0].category_name,
                "img": img,
                "aspect": aspect,
                "vector": features.vector(world, img * [aspect, 1]),
                "center": tuple(img[[0, 5, 9, 13, 17]].mean(axis=0)),
            })
        if len(found) == 2 and found[0]["label"] == found[1]["label"]:
            found.sort(key=lambda x: x["img"][0][0])
            found[0]["label"], found[1]["label"] = "Left", "Right"
        return {hand["label"]: hand for hand in found}

    # -------------------------------------------------------------------- core

    def _core_link(self):
        while True:
            try:
                conn = ipc.connect(paths.CORE_SOCKET, timeout=2)
                conn.send({"type": "hello", "role": "vision"})
                self.core = conn
                log.info("connected to core")
                while True:
                    msg, _ = conn.recv()
                    if msg is None:
                        break
                    if msg.get("type") == "paused":
                        self.paused = bool(msg["value"])
            except OSError:
                pass
            self.core = None
            time.sleep(1)

    def _send_core(self, msg):
        conn = self.core
        if conn is None:
            return
        try:
            conn.send(msg)
        except OSError:
            self.core = None

    # ----------------------------------------------------------------- clients

    def _handle_client(self, conn):
        msg, _ = conn.recv()
        if msg is None:
            return
        cmd = msg.get("cmd")
        if cmd == "preview":
            preview = ipc.Mailbox(conn)
            with self.lock:
                self.previews.append(preview)
            try:
                while conn.recv()[0] is not None:
                    pass
            finally:
                with self.lock:
                    self.previews.remove(preview)
                preview.close()
        elif cmd == "record_cancel":
            self.record_stop.set()
            conn.send({"ok": True})
        elif cmd == "record":
            conn.send(self._record_gesture(msg["gesture"], float(msg.get("seconds", 6)), msg.get("kind", "pose")))
        elif cmd == "delete":
            self._delete(msg["gesture"])
            conn.send({"ok": True})
        elif cmd == "delete_all":
            self.samples = {}
            config.save_json(paths.SAMPLES_FILE, self.samples)
            shutil.rmtree(paths.PHOTO_DIR, ignore_errors=True)
            self.load_samples()
            conn.send({"ok": True})
        elif cmd == "cleanup":
            self.cleanup()
            conn.send({"ok": True})
        elif cmd == "gaze_start":
            # add: further rounds on top of the saved calibration.
            self.gaze_samples, self.gaze_rounds = (self._gaze_saved() if msg.get("add") else ([], []))
            self.gaze_target = None
            conn.send({"ok": True, "round": max((r["round"] for r in self.gaze_rounds), default=0) + 1})
        elif cmd == "gaze_sample":
            # Collect while the user looks at one dot (layout coordinates).
            count = len(self.gaze_samples or [])
            rnd = msg.get("round", 1)
            if self.gaze_rounds is not None and rnd not in [r["round"] for r in self.gaze_rounds]:
                self.gaze_rounds.append({"round": rnd, "time": round(time.time()), "full": bool(msg.get("full"))})
            self.gaze_target = ((float(msg["x"]), float(msg["y"])),
                                {"name": msg["monitor"], "rect": msg["rect"], "round": rnd})
            time.sleep(float(msg.get("seconds", 1.0)))
            self.gaze_target = None
            conn.send({"ok": True, "samples": len(self.gaze_samples or []) - count})
        elif cmd == "gaze_finish":
            conn.send(self._gaze_finish(bool(msg.get("save"))))
        elif cmd == "gaze_drop":
            samples, rounds = self._gaze_saved()
            conn.send(self._gaze_save([s for s in samples if s[2]["round"] != msg["round"]], rounds))
        elif cmd == "gaze_reload":
            self.load_gaze()
            conn.send({"ok": True})
        else:
            conn.send({"ok": False, "error": f"unknown command {cmd}"})

    def _gaze_saved(self):
        """Saved calibration: samples and rounds ({round, time, full})."""
        samples = [(np.asarray(f), tuple(p), m) for f, p, m in config.load_json(paths.GAZE_SAMPLES, [])]
        rounds = config.load_json(paths.GAZE_FILE, {}).get("rounds", [])
        return samples, rounds

    def _gaze_finish(self, save):
        samples, rounds = self.gaze_samples or [], self.gaze_rounds or []
        self.gaze_samples, self.gaze_rounds, self.gaze_target = None, None, None
        if not save:
            return {"ok": True}
        return self._gaze_save(samples, rounds)

    def _gaze_save(self, samples, rounds):
        """Fit and save; nothing is written when too few dots were seen."""
        if len({p for _, p, _ in gaze.clean(samples)}) < 5:
            return {"ok": False, "error": "face"}
        model, error = gaze.fit(samples)
        # The measured values are kept: rounds can be added or dropped later.
        config.save_json(paths.GAZE_SAMPLES, [[np.round(f, 5).tolist(), list(p), m] for f, p, m in samples])
        used = {m["round"] for _, _, m in samples}
        config.save_json(paths.GAZE_FILE, {"model": model, "error_px": round(error),
                                           "rounds": [r for r in rounds if r["round"] in used]})
        log.info("gaze calibrated: %d samples, median error %.0f px", len(samples), error)
        self.load_gaze()
        return {"ok": True, "error_px": round(error)}

    # --------------------------------------------------------------- recording

    def _record(self, rec, now, hands, frame):
        rec["frames"].append(hands)
        if rec["kind"] == "motion":
            done = rec["segmenter"].update(now, hands)
            movement = motion.describe(done) if done else None
            if movement and (not rec["takes"] or motion.same_take(rec["takes"][0], movement)):
                rec["takes"].append(movement)
                rec["back"] = True      # next: back to the start position
                if len(rec["takes"]) >= motion.TAKES:
                    rec["done"].set()
            elif movement or not hands:
                rec["back"] = False     # that was the way back (or the hands were lowered)
            rec["phase"] = "back" if rec["back"] else rec["segmenter"].phase(now)
        # Every second frame, scaled down, for the clip of the recording.
        if len(rec["frames"]) % 2 == 0:
            h, w = frame.shape[:2]
            rec["images"].append(cv2.resize(frame, (640, 640 * h // w), interpolation=cv2.INTER_AREA))

    @staticmethod
    def _crop_box(frames, shape):
        """One square around the hands in all frames, so the clip stays still."""
        h, w = shape[:2]
        pts = np.concatenate([hand["img"] for hands in frames for hand in hands.values()])
        xs, ys = pts[:, 0] * w, pts[:, 1] * h
        size = min(max(xs.max() - xs.min(), ys.max() - ys.min()) * 1.3, h, w)
        cx, cy = (xs.max() + xs.min()) / 2, (ys.max() + ys.min()) / 2
        x0 = int(np.clip(cx - size / 2, 0, w - size))
        y0 = int(np.clip(cy - size / 2, 0, h - size))
        return x0, y0, int(size)

    def _save_pictures(self, gid, frames, images):
        """Clip of the recording plus its middle frame as the list picture."""
        clip = paths.PHOTO_DIR / f"{gid}-clip"
        shutil.rmtree(clip, ignore_errors=True)
        if not images:
            return
        clip.mkdir(parents=True)
        x0, y0, size = self._crop_box(frames, images[0].shape)
        # At most 40 pictures, spread over the whole recording.
        step = -(-len(images) // 40)
        for i, image in enumerate(images[::step]):
            crop = image[y0:y0 + size, x0:x0 + size]
            small = cv2.resize(crop, (CLIP_SIZE, CLIP_SIZE), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(clip / f"{i:02d}.jpg"), small, [cv2.IMWRITE_JPEG_QUALITY, 85])
        middle = images[len(images) // 2][y0:y0 + size, x0:x0 + size]
        photo = cv2.resize(middle, (PHOTO_SIZE, PHOTO_SIZE), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(paths.PHOTO_DIR / f"{gid}.jpg"), photo, [cv2.IMWRITE_JPEG_QUALITY, 88])

    def _record_gesture(self, gid, seconds, kind):
        """Record the hand(s) shown for a gesture: one hand or both; a pose
        held, a movement made motion.TAKES times (ends once they are made), or
        (kind "swipe") the hand shape of a swipe in any direction, held like a
        pose with one hand."""
        self.record_stop.clear()
        done = threading.Event()
        self.recorder = {"frames": [], "images": [], "kind": kind, "takes": [], "done": done,
                         "segmenter": motion.Segmenter(), "back": False, "phase": "nohands"}
        deadline = time.monotonic() + seconds
        cancelled = False
        while time.monotonic() < deadline and not done.is_set():
            if self.record_stop.wait(0.05):
                cancelled = True
                break
        rec, self.recorder = self.recorder, None
        if cancelled:
            return {"ok": False, "error": "cancelled"}
        if kind == "motion":
            return self._save_motion(gid, rec)
        frames = rec["frames"]
        # The hands that took part: seen in most frames.
        counts = {}
        for hands in frames:
            for label in hands:
                counts[label] = counts.get(label, 0) + 1
        labels = sorted(label for label, n in counts.items() if n >= 0.7 * len(frames))
        if not labels or len(frames) < MIN_SAMPLES or (kind == "swipe" and len(labels) != 1):
            return {"ok": False, "error": "hand"}
        entry = {"hands": {label: [hands[label]["vector"].round(4).tolist()
                                   for hands in frames if label in hands] for label in labels}}
        if kind == "swipe":
            entry["kind"] = "swipe"
        self.samples[gid] = entry
        config.save_json(paths.SAMPLES_FILE, self.samples)
        paths.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        self._save_pictures(gid, [h for h in frames if h], rec["images"])
        self.load_samples()
        lookalikes = [] if kind == "swipe" else self.templates.lookalikes(gid)
        return {"ok": True, "hands": len(labels), "lookalikes": lookalikes}

    def _save_motion(self, gid, rec):
        # The hands most of the movements were made with.
        common = Counter(tuple(sorted(t)) for t in rec["takes"]).most_common(1)
        takes = [t for t in rec["takes"] if common and tuple(sorted(t)) == common[0][0]]
        if len(takes) < motion.MIN_TAKES:
            return {"ok": False, "error": "motion"}
        self.samples[gid] = {"kind": "motion", "takes": takes}
        config.save_json(paths.SAMPLES_FILE, self.samples)
        paths.PHOTO_DIR.mkdir(parents=True, exist_ok=True)
        self._save_pictures(gid, [h for h in rec["frames"] if h], rec["images"])
        self.load_samples()
        return {"ok": True, "hands": len(common[0][0]), "lookalikes": self.motions.lookalikes(gid)}

    def _delete(self, gid):
        self.samples.pop(gid, None)
        config.save_json(paths.SAMPLES_FILE, self.samples)
        (paths.PHOTO_DIR / f"{gid}.jpg").unlink(missing_ok=True)
        shutil.rmtree(paths.PHOTO_DIR / f"{gid}-clip", ignore_errors=True)
        self.load_samples()

    # ----------------------------------------------------------------- preview

    def _send_preview(self, frame, hands, gestures):
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (PREVIEW_WIDTH, PREVIEW_WIDTH * h // w), interpolation=cv2.INTER_AREA)
        bgra = cv2.cvtColor(small, cv2.COLOR_BGR2BGRA)
        by_hand = {}
        for gid, labels in self.active.items():
            for label in labels or []:
                by_hand[label] = gid
        msg = {
            "type": "preview",
            "camera": True,
            "width": bgra.shape[1],
            "height": bgra.shape[0],
            "fps": round(self.fps, 1),
            "paused": self.paused,
            "gestures": gestures,
            "takes": len(recorder["takes"]) if (recorder := self.recorder) else 0,
            "phase": recorder["phase"] if recorder else None,
            "hands": [{
                "hand": label,
                "landmarks": hand["img"].round(4).tolist(),
                # Only a recognised, held gesture is shown.
                "gesture": by_hand.get(label),
            } for label, hand in hands.items()],
        }
        with self.lock:
            for preview in self.previews:
                preview.put(msg, bgra.tobytes())


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    Vision().run()


if __name__ == "__main__":
    main()
