#!/usr/bin/env bash
# One-time setup for making-short-explainer-videos (macOS or Linux).
#
#   bash setup.sh              uv, fonts, Python deps
#   bash setup.sh --model      also download the Kokoro TTS model (~330 MB) with one short synthesis
#   bash setup.sh --recorder   also Playwright + Chromium for screen recordings of the real UI
#
# Env: EXPLAINER_FONT_DIR (default ~/.local/share/explainer-fonts),
#      EXPLAINER_NODE_DIR (default ~/.local/share/explainer-node)
set -euo pipefail

RECORDER=0
MODEL=0
while [ $# -gt 0 ]; do
  case "$1" in
    --recorder) RECORDER=1 ;;
    --model) MODEL=1 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

export PATH="$HOME/.local/bin:$PATH"
FONT_DIR="${EXPLAINER_FONT_DIR:-$HOME/.local/share/explainer-fonts}"
NODE_DIR="${EXPLAINER_NODE_DIR:-$HOME/.local/share/explainer-node}"

# 1. uv (runs every script; supplies Python 3.12 and ffmpeg through imageio-ffmpeg)
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Open fonts (SIL OFL 1.1), pinned releases. The engine uses them on Linux, or when EXPLAINER_FONT_DIR is set.
#    On macOS it uses the SF system fonts when they exist.
mkdir -p "$FONT_DIR"
if [ ! -f "$FONT_DIR/Inter-Regular.ttf" ] || [ ! -f "$FONT_DIR/JetBrainsMono-Regular.ttf" ]; then
  T="$(mktemp -d)"
  curl -fsSL -o "$T/inter.zip" https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip
  curl -fsSL -o "$T/jbm.zip" https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip
  python3 - "$T" "$FONT_DIR" <<'PY'
import os, sys, zipfile
tmp, out = sys.argv[1], sys.argv[2]
want = {"inter.zip": [f"extras/ttf/Inter-{w}.ttf" for w in "Regular Medium SemiBold Bold ExtraBold Black".split()],
        "jbm.zip": [f"fonts/ttf/JetBrainsMono-{w}.ttf" for w in "Regular Medium Bold".split()]}
for name, files in want.items():
    with zipfile.ZipFile(os.path.join(tmp, name)) as z:
        for f in files:
            open(os.path.join(out, os.path.basename(f)), "wb").write(z.read(f))
PY
  rm -rf "$T"
fi
echo "fonts: $FONT_DIR"

# 3. Python deps (cached by uv)
SPACY_EN=https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
uv run -q --no-project --python 3.12 --with imageio-ffmpeg --with pillow --with pygments --with kokoro \
  --with soundfile --with "en-core-web-sm @ $SPACY_EN" --with "preshed==3.0.13" \
  python -c "import imageio_ffmpeg, kokoro; print('ffmpeg:', imageio_ffmpeg.get_ffmpeg_exe())"

# 4. Optional: the Kokoro model, so the first render does not wait for the download
if [ "$MODEL" = 1 ]; then
  uv run -q --no-project --python 3.12 --with kokoro --with soundfile --with "en-core-web-sm @ $SPACY_EN" \
    --with "preshed==3.0.13" python -c 'from kokoro import KPipeline
list(KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")("Ready.", voice="am_michael"))
print("kokoro: model cached")'
fi

# 5. Optional: Playwright + the full Chromium build for screen recordings
if [ "$RECORDER" = 1 ]; then
  mkdir -p "$NODE_DIR"
  cd "$NODE_DIR"
  [ -f package.json ] || npm init -y >/dev/null
  npm i --silent playwright@1.64.1
  if [ "$(uname)" = "Linux" ]; then npx playwright install --with-deps chromium; else npx playwright install chromium; fi
  echo "recorder: write recording scripts in $NODE_DIR (playwright resolves there)"
fi

echo "making-short-explainer-videos ready"
