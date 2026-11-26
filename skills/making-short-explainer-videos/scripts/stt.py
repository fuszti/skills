"""Local Whisper for the feed and grill-deck servers: mlx-whisper on Apple Silicon, faster-whisper everywhere else.

    from stt import transcribe, BACKEND
    out = transcribe(audio, model="mlx-community/whisper-large-v3-turbo", language="en")
    out["text"], out["segments"]  # segments: dicts with text, no_speech_prob, avg_logprob (the mlx-whisper shape)

`audio` is float32 mono at 16 kHz. Model names are given in their mlx form; on faster-whisper
"mlx-community/whisper-<name>[-mlx]" becomes "<name>" (large-v3-turbo, large-v3, small, ...). Any other name or a
local path is passed through as is.

faster-whisper uses a CUDA GPU when it can load one (cuBLAS 12 and cuDNN 9 from the system or from the
nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels that the wrapper scripts add), else the CPU with int8.
Overrides: WHISPER_DEVICE=cpu|cuda, WHISPER_COMPUTE_TYPE=float16|int8_float16|int8|float32.
This file exists twice, in making-short-explainer-videos/scripts and grill-deck/scripts: keep both copies equal.
"""

import os
import platform
import sys
import threading

BACKEND = "mlx" if sys.platform == "darwin" and platform.machine() == "arm64" else "faster-whisper"

_models = {}
_load_lock = threading.Lock()
_device = None  # chosen on the first load; "cpu" after a CUDA failure


def _fw_name(model):
    if model.startswith("mlx-community/whisper-"):
        name = model[len("mlx-community/whisper-") :]
        return name.removesuffix("-mlx")
    return model


def _preload_cuda_wheels():
    """Load cuBLAS / cuDNN from the pip wheels, if present, so ctranslate2 finds them without LD_LIBRARY_PATH."""
    import ctypes
    import glob

    try:
        import nvidia  # namespace package of the nvidia-*-cu12 wheels
    except ImportError:
        return
    for base in getattr(nvidia, "__path__", []):
        for pattern in ("cublas/lib/libcublasLt.so*", "cublas/lib/libcublas.so*", "cudnn/lib/libcudnn*.so*"):
            for lib in sorted(glob.glob(os.path.join(base, pattern))):
                try:
                    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    pass


def _pick_device():
    want = os.environ.get("WHISPER_DEVICE")
    if want:
        return want
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


def _fw_model(model):
    global _device
    with _load_lock:
        if _device is None:
            _device = _pick_device()
            if _device == "cuda":
                _preload_cuda_wheels()
        key = (_fw_name(model), _device)
        if key not in _models:
            from faster_whisper import WhisperModel

            compute = os.environ.get("WHISPER_COMPUTE_TYPE") or ("float16" if _device == "cuda" else "int8")
            _models[key] = WhisperModel(key[0], device=_device, compute_type=compute)
        return _models[key]


def _fw_transcribe(audio, model, language, condition_on_previous_text):
    segments, info = _fw_model(model).transcribe(
        audio, language=language, condition_on_previous_text=condition_on_previous_text, beam_size=5
    )
    segs = [
        {
            "text": s.text,
            "start": s.start,
            "end": s.end,
            "no_speech_prob": s.no_speech_prob,
            "avg_logprob": s.avg_logprob,
        }
        for s in segments  # a generator: decoding happens here
    ]
    return {"text": "".join(s["text"] for s in segs).strip(), "segments": segs, "language": info.language}


def transcribe(audio, model, language=None, condition_on_previous_text=True):
    """Not thread-safe: the callers hold their own lock around it."""
    global _device
    if BACKEND == "mlx":
        import mlx_whisper

        kw = {"language": language} if language else {}
        return mlx_whisper.transcribe(
            audio, path_or_hf_repo=model, condition_on_previous_text=condition_on_previous_text, **kw
        )
    try:
        return _fw_transcribe(audio, model, language, condition_on_previous_text)
    except Exception as exc:
        # a missing or wrong cuDNN / cuBLAS only shows up on the first decode: fall back to the CPU once
        if _device != "cuda" or os.environ.get("WHISPER_DEVICE") == "cuda":
            raise
        print(f"whisper: CUDA failed ({str(exc)[:120]}); using the CPU", flush=True)
        with _load_lock:
            _models.clear()
            _device = "cpu"
        return _fw_transcribe(audio, model, language, condition_on_previous_text)


def describe():
    """One line for the server log: which backend and device the next transcription uses."""
    if BACKEND == "mlx":
        return "mlx-whisper (Apple Silicon)"
    return f"faster-whisper ({_device or 'device not chosen yet'})"
