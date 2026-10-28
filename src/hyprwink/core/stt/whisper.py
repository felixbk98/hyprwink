"""Whisper large-v3-turbo, local (faster-whisper): on the NVIDIA GPU if
there is one, else on the CPU."""

import ctypes
import glob
import logging
import os
import threading

import numpy as np

from ... import paths

LABEL = "Whisper"
CLOUD = False
MODEL = "large-v3-turbo"

log = logging.getLogger("hyprwink.whisper")
_model = None
_lock = threading.Lock()


def _load_cuda():
    """faster-whisper finds the CUDA libraries from the NVIDIA wheels only
    when they are loaded beforehand."""
    try:
        import nvidia.cublas
        import nvidia.cudnn
    except ImportError:
        return False
    for base, pattern in ((nvidia.cublas, "libcublas*.so.*"), (nvidia.cudnn, "libcudnn*.so.*")):
        for path in base.__path__:
            for lib in sorted(glob.glob(os.path.join(path, "lib", pattern))):
                try:
                    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass
    return True


def download():
    """Path of the model; downloaded once, then no request to the model hub."""
    from faster_whisper import download_model
    try:
        return download_model(MODEL, cache_dir=str(paths.WHISPER_DIR), local_files_only=True)
    except Exception:
        return download_model(MODEL, cache_dir=str(paths.WHISPER_DIR))


def prepare():
    global _model
    with _lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel
        model = download()
        if _load_cuda():
            try:
                _model = WhisperModel(model, device="cuda", compute_type="float16")
                log.info("on the GPU")
                return _model
            except Exception as e:
                log.warning("GPU failed, using the CPU: %s", e)
        _model = WhisperModel(model, device="cpu", compute_type="int8")
        log.info("on the CPU")
        return _model


def transcribe(pcm, rate, language):
    # faster-whisper expects 16 kHz, which the dictation records.
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    # The voice filter drops silence (no made-up text there); what it keeps is
    # speech, so Whisper's own no-speech guess, which drops single short words
    # like "go", is not used. Words from 0.1 s on count.
    segments, _ = prepare().transcribe(audio, language=language, beam_size=5, vad_filter=True,
                                       vad_parameters={"min_speech_duration_ms": 100},
                                       no_speech_threshold=None)
    return "".join(s.text for s in segments).strip()
