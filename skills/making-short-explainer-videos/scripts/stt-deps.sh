# Sourced by the wrapper scripts: sets STT_DEPS to the `uv run --with` flags for local Whisper (see stt.py).
#   Apple Silicon macOS: mlx-whisper.
#   Everything else: faster-whisper, plus NVIDIA's cuBLAS 12 / cuDNN 9 wheels on Linux when nvidia-smi sees a GPU
#   (about 1 GB, downloaded once into the uv cache). WHISPER_DEVICE=cpu skips them.
# This file exists twice, in making-short-explainer-videos/scripts and grill-deck/scripts: keep both copies equal.
if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then
  STT_DEPS=(--with mlx-whisper)
else
  STT_DEPS=(--with faster-whisper)
  if [ "$(uname -s)" = Linux ] && [ "${WHISPER_DEVICE:-}" != cpu ] && command -v nvidia-smi >/dev/null \
    && nvidia-smi -L >/dev/null 2>&1; then
    STT_DEPS+=(--with nvidia-cublas-cu12 --with "nvidia-cudnn-cu12==9.*")
  fi
fi
