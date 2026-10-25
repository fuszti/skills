"""Render a short-video series.

    bash scripts/explainer <project_dir> [--keys] [--dry] [--check] [--long] [--site] [part numbers...]

(The wrapper runs this file under uv with its dependencies.) Flags: --keys (key-frame sheets), --dry (with --keys: estimated timing, no TTS run), --check (streams +
volume of every out/part-N.mp4), --long (join the parts into out/full.mp4 with chapters), --site (feed page; it adds
full.mp4 when it exists).

Videos are 1920x1080 (16:9). Each render also writes out/part-N.json with the question pauses: every point where
the narration says "Pause and guess", plus every marker whose name starts with "pause". The feed stops there.

<project_dir>/episodes.py defines SERIES and EPISODES (see example/episodes.py). Outputs:
    <project_dir>/tts/        narration cache (one local Kokoro run per part, reused while the text is unchanged)
    <project_dir>/out/        part-N.mp4, or key-N.jpg with --keys (last frame of every scene + every camera shot)
    <project_dir>/site/       with --site: the feed page, parts.json, videos and posters, ready to publish
"""

import hashlib
import importlib.util
import json
import os
import re

PAUSE_PHRASE = re.compile(r"pause and guess[.!]?", re.I)
import filecmp
import shutil
import subprocess
import sys
from multiprocessing import Pool

import imageio_ffmpeg
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E  # noqa: E402

DEFAULTS = {
    "voice": "am_michael",  # Kokoro voice ids: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
    "model": "hexgrad/Kokoro-82M",
    "lang": "a",  # a = American English, b = British (bm_george, bf_emma)
    "speed": 1.08,
    "tail": 1.6,
}


def load(project):
    spec = importlib.util.spec_from_file_location("episodes", os.path.join(project, "episodes.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, project)
    spec.loader.exec_module(mod)
    cfg = {**DEFAULTS, **getattr(mod, "SERIES", {})}
    E.SERIES.update(cfg)
    E.REC_DIR = os.path.join(project, "rec")
    return mod, cfg


def fake_alignment(text, cps=15.5):
    """--dry: even timing at ~185 wpm, so key frames can be checked before paying for narration."""
    st = [i / cps for i in range(len(text))]
    return {
        "characters": list(text),
        "character_start_times_seconds": st,
        "character_end_times_seconds": [t + 1 / cps for t in st],
    }


_PIPELINE = {}
# Kokoro leaves no silence after a sentence, so the next scene would start the instant "guess." ends and the
# question would fade out before the feed stops. The gap keeps the question on screen at the pause.
PAUSE_GAP = 0.8
SR = 24000


def kokoro_alignment(text, results, sr=SR):
    """Spread Kokoro's word timestamps over the characters of `text`, in the alignment shape engine.char_time reads."""
    n = len(text)
    st, en = [None] * n, [None] * n
    cur, off = 0, 0.0
    for r in results:
        for tk in r.tokens or []:
            i = text.find(tk.text, cur, cur + len(tk.text) + 40) if tk.text else -1
            if i < 0:
                continue
            j = i + len(tk.text)
            cur = j
            if tk.start_ts is None or tk.end_ts is None:
                continue
            a, b = off + tk.start_ts, off + tk.end_ts
            for k in range(i, j):
                st[k] = a + (b - a) * (k - i) / (j - i)
                en[k] = a + (b - a) * (k - i + 1) / (j - i)
        off += len(r.audio) / sr
    last = 0.0
    for k in range(n):  # spaces and unmatched characters take the end of the character before them
        if st[k] is None:
            st[k] = en[k] = last
        last = en[k] = max(en[k], st[k])
    return {"characters": list(text), "character_start_times_seconds": st, "character_end_times_seconds": en}


def tts(project, cfg, text):
    if os.environ.get("EXPLAINER_DRY"):
        return None, fake_alignment(text)
    d = os.path.join(project, "tts")
    os.makedirs(d, exist_ok=True)
    h = hashlib.sha1(
        f"gap{PAUSE_GAP}|{cfg['voice']}|{cfg['model']}|{cfg['lang']}|{cfg['speed']}|{text}".encode()
    ).hexdigest()[:16]
    meta, wav = os.path.join(d, h + ".json"), os.path.join(d, h + ".wav")
    if not os.path.exists(meta):
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline

        key = (cfg["lang"], cfg["model"])
        if key not in _PIPELINE:
            _PIPELINE[key] = KPipeline(lang_code=cfg["lang"], repo_id=cfg["model"])
        results = list(_PIPELINE[key](text, voice=cfg["voice"], speed=cfg["speed"], split_pattern=None))
        audio = np.concatenate([r.audio.numpy() for r in results])
        align = kokoro_alignment(text, results)
        st, en = align["character_start_times_seconds"], align["character_end_times_seconds"]
        for p in reversed(list(PAUSE_PHRASE.finditer(text))):
            at = int(en[p.end() - 1] * SR)
            audio = np.concatenate([audio[:at], np.zeros(int(PAUSE_GAP * SR), audio.dtype), audio[at:]])
            for k in range(p.end(), len(text)):
                st[k] += PAUSE_GAP
                en[k] += PAUSE_GAP
        sf.write(wav, audio, SR)
        json.dump(align, open(meta, "w"))
    align = json.load(open(meta))
    if "".join(align["characters"]) != text:
        raise SystemExit("alignment text differs from the narration; markers would drift")
    return wav, align


def timeline(project, cfg, ep):
    """Builders get m = {marker: seconds, "s": scene start, "end": scene end}. Never name a marker s or end."""
    parts, info, off = [], [], 0
    for narration, builder in ep["scenes"]:
        spoken, markers, words = E.parse(narration)
        bad = {"s", "end"} & set(markers)
        if bad:
            raise SystemExit(f"part {ep['n']}: marker names {bad} are reserved")
        info.append((off, markers, words, builder, spoken))
        parts.append(spoken)
        off += len(spoken) + 1
    text = " ".join(parts)
    audio, align = tts(project, cfg, text)
    audio_end = align["character_end_times_seconds"][-1]
    starts = [0.0 if k == 0 else E.char_time(align, o) - 0.05 for k, (o, *_r) in enumerate(info)]
    total = audio_end + cfg["tail"]
    elements, words_t, pauses = [], [], []
    for k, (o, markers, words, builder, spoken) in enumerate(info):
        s = starts[k]
        e = starts[k + 1] if k + 1 < len(starts) else audio_end + 0.15
        m = {name: E.char_time(align, o + idx) for name, idx in markers.items()}
        m["s"], m["end"] = s, e
        pauses += [t for name, t in m.items() if name.startswith("pause")]
        # The gap to the next scene is often only 0.3 s, and elements fade 0.2 s before their scene ends, so
        # stop right after the phrase and before that fade, or the frozen frame no longer shows the options.
        for p in PAUSE_PHRASE.finditer(spoken):
            said = E.char_time(align, o + p.end() - 1, end=True)
            pauses.append(max(said - 0.02, min(said + 0.05, e - 0.22)))
        for el in builder(m):
            if el.t1 is None:
                el.t1 = e
            elements.append(el)
        for disp, a, b in words:
            words_t.append((disp, E.char_time(align, o + a), E.char_time(align, o + b - 1, end=True)))
    return audio, elements, words_t, audio_end, total, sorted(round(p, 2) for p in pauses)


def base_frame(ep, n_parts):
    from PIL import ImageDraw

    img = Image.new("RGBA", (E.W, E.H), (*E.BG, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, E.H, 48):
        for x in range(0, E.W, 48):
            d.point((x, y), fill=(32, 40, 56, 255))
    tag = E.Pill(0, E.X0, 40, E.SERIES["tag"], E.BLUE, size=26)
    tag_w = tag.sprite()[0].width
    for el in [
        tag,
        E.Txt(0, E.X0 + tag_w + 16, 44, f"PART {ep['n']}", 30, E.T3, "Bold"),
        E.Txt(0, E.X0, 86, ep["label"], 54, E.T1, "Heavy", maxw=E.CW),
        E.Txt(0, E.X0, 1036, E.SERIES.get("footer", ""), 22, (50, 60, 78), "Semibold"),
    ]:
        if getattr(el, "text", None) == "":
            continue
        sp, x, y = el.sprite()
        img.alpha_composite(sp, (int(x), int(y)))
    return img


def end_card(ep, eps, t0):
    i = [e["n"] for e in eps].index(ep["n"])
    if i + 1 < len(eps):
        title, sub = f"Next: Part {eps[i + 1]['n']}", eps[i + 1]["label"]
    else:
        title, sub = "↻ Start again: Part 1", eps[0]["label"]
    return [
        E.Box(
            t0,
            E.CX - 450,
            380,
            900,
            250,
            title,
            sub,
            fill=E.PANEL2,
            border=E.AMBER,
            tcolor=E.AMBER,
            tsize=52,
            ssize=40,
            scolor=E.T1,
            t1=9999,
        )
    ]


def compose(ep, eps, project, cfg):
    audio, elements, words_t, audio_end, total, pauses = timeline(project, cfg, ep)
    elements += end_card(ep, eps, audio_end + 0.1)
    caps = E.Captions(words_t, ep.get("emph", ()))
    base = base_frame(ep, len(eps))

    def frame_at(t):
        from PIL import ImageDraw

        f = base.copy()
        d = ImageDraw.Draw(f)
        d.rounded_rectangle([E.X0, 168, E.X1, 173], radius=3, fill=(*E.LINE, 255))
        d.rounded_rectangle([E.X0, 168, E.X0 + int(E.CW * min(1, t / total)), 173], radius=3, fill=(*E.AMBER, 255))
        for el in sorted(elements, key=lambda e: e.z):
            el.draw(f, t, total)
        if t < audio_end + 0.3:
            caps.draw(f, t)
        return f.convert("RGB")

    return audio, elements, total, frame_at, pauses


def render(project, n, mode):
    mod, cfg = load(project)
    eps = mod.EPISODES
    ep = next(e for e in eps if e["n"] == n)
    audio, elements, total, frame_at, pauses = compose(ep, eps, project, cfg)
    out_dir = os.path.join(project, "out")
    os.makedirs(out_dir, exist_ok=True)
    if mode == "keys":
        ends = sorted({el.t1 for el in elements if el.t1 and el.t1 < total})
        times = [t - 0.25 for t in ends] + [total - 0.1]
        times += [sh[0] + 1.1 for el in elements if hasattr(el, "shots") for sh in el.shots]
        times += pauses
        tiles = [frame_at(t).resize((960, 540)) for t in sorted({round(t, 2) for t in times})]
        cols = 3
        sheet = Image.new("RGB", (cols * 960, ((len(tiles) + cols - 1) // cols) * 540))
        for i, im in enumerate(tiles):
            sheet.paste(im, ((i % cols) * 960, (i // cols) * 540))
        path = os.path.join(out_dir, f"key-{n}.jpg")
        sheet.save(path, quality=85)
        return path
    if audio is None:
        raise SystemExit("--dry renders key frames only; drop --dry to render video")
    path = os.path.join(out_dir, f"part-{n}.mp4")
    p = subprocess.Popen(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{E.W}x{E.H}",
            "-r",
            str(E.FPS),
            "-i",
            "-",
            "-i",
            audio,
            "-af",
            f"apad=pad_dur={cfg['tail']}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-t",
            f"{total:.3f}",
            "-movflags",
            "+faststart",
            path,
        ],
        stdin=subprocess.PIPE,
    )
    for i in range(int(total * E.FPS)):
        p.stdin.write(frame_at(i / E.FPS).tobytes())
    p.stdin.close()
    p.wait()
    json.dump({"duration": round(total, 2), "pauses": pauses}, open(os.path.join(out_dir, f"part-{n}.json"), "w"))
    return f"{path} {total:.1f}s"


def meta(project, n):
    path = os.path.join(project, "out", f"part-{n}.json")
    return json.load(open(path)) if os.path.exists(path) else {}


def _put(src, dst):
    """Copy src to dst only when dst is missing or differs, by temp file + atomic rename. True if written."""
    if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
        return False
    tmp = dst + ".tmp"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)
    return True


def site(project):
    """Copy videos + posters next to the feed template and write parts.json from EPISODES."""
    mod, _cfg = load(project)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    dst = os.path.join(project, "site")
    os.makedirs(os.path.join(dst, "v"), exist_ok=True)
    os.makedirs(os.path.join(dst, "p"), exist_ok=True)
    _put(os.path.join(HERE, "..", "feed", "index.html"), os.path.join(dst, "index.html"))
    parts = []
    for ep in mod.EPISODES:
        n = ep["n"]
        src = os.path.join(project, "out", f"part-{n}.mp4")
        poster = os.path.join(dst, "p", f"part-{n}.jpg")
        # A feed may be playing this file right now: leave an unchanged video and its poster alone.
        if _put(src, os.path.join(dst, "v", f"part-{n}.mp4")) or not os.path.exists(poster):
            subprocess.run(
                [
                    ff,
                    "-y",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{min(6.0, meta(project, n).get('duration', 12) / 2):.2f}",
                    "-i",
                    src,
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=960:-1",
                    "-q:v",
                    "4",
                    poster,
                ],
                check=True,
            )
        parts.append(
            {
                "n": n,
                "title": ep["label"],
                "summary": ep.get("summary", ""),
                "files": ep.get("files", []),
                "real": bool(ep.get("real")),
                "pauses": meta(project, n).get("pauses", []),
                "followup": bool(ep.get("followup")),
                "request": ep.get("request"),
            }
        )
    page = dict(getattr(mod, "PAGE", {}))
    full = os.path.join(project, "out", "full.mp4")
    if os.path.exists(full):
        _put(full, os.path.join(dst, "v", "full.mp4"))
        page["full"] = "v/full.mp4"
    if page.get("title"):
        index = os.path.join(dst, "index.html")
        html = open(index).read().replace("<title>Explainer Shorts</title>", f"<title>{page['title']}</title>", 1)
        open(index, "w").write(html)
    json.dump({"page": page, "parts": parts}, open(os.path.join(dst, "parts.json.tmp"), "w"), indent=1)
    os.replace(os.path.join(dst, "parts.json.tmp"), os.path.join(dst, "parts.json"))
    print(f"site ready: {dst} ({len(parts)} parts). Publish index.html with files v/*, p/*, parts.json.")


def long_video(project):
    """Join the rendered parts into out/full.mp4, one chapter per part. The parts share one encoder setup, so the
    streams are copied, not encoded again. The long video plays straight through: only the feed stops at questions."""
    mod, _cfg = load(project)
    out = os.path.join(project, "out")
    eps = [e for e in mod.EPISODES if os.path.exists(os.path.join(out, f"part-{e['n']}.mp4"))]
    if not eps:
        raise SystemExit("no out/part-N.mp4 yet: render the parts first")
    with open(os.path.join(out, "full.txt"), "w") as f:
        f.writelines(f"file 'part-{e['n']}.mp4'\n" for e in eps)
    chapters, t = [";FFMETADATA1", f"title={getattr(mod, 'PAGE', {}).get('title', 'Explainer')}"], 0
    for e in eps:
        dur = int(meta(project, e["n"]).get("duration", 0) * 1000)
        title = e["label"].replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")
        chapters += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={t}", f"END={t + dur}", f"title=Part {e['n']}: {title}"]
        t += dur
    open(os.path.join(out, "full.meta"), "w").write("\n".join(chapters) + "\n")
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            os.path.join(out, "full.txt"),
            "-i",
            os.path.join(out, "full.meta"),
            "-map_metadata",
            "1",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            os.path.join(out, "full.mp4"),
        ],
        check=True,
    )
    print(f"{os.path.join(out, 'full.mp4')} {t / 1000:.1f}s, {len(eps)} chapters")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    project = os.path.abspath(args[0])
    flags = [a for a in args[1:] if a.startswith("--")]
    mod, cfg = load(project)
    if "--dry" in flags:
        os.environ["EXPLAINER_DRY"] = "1"
    if "--long" in flags:
        long_video(project)
        raise SystemExit(0)
    if "--site" in flags:
        site(project)
        raise SystemExit(0)
    if "--check" in flags:
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        for ep in mod.EPISODES:
            f = os.path.join(project, "out", f"part-{ep['n']}.mp4")
            info = subprocess.run([ff, "-hide_banner", "-i", f], capture_output=True, text=True).stderr
            vol = subprocess.run(
                [ff, "-hide_banner", "-i", f, "-af", "volumedetect", "-vn", "-f", "null", "-"],
                capture_output=True,
                text=True,
            ).stderr
            dur = re.search(r"Duration: (\S+),", info)
            mean = re.search(r"mean_volume: (\S+) dB", vol)
            ok = (
                "Video: h264" in info
                and f"{E.W}x{E.H}" in info
                and "Audio: aac" in info
                and mean
                and float(mean.group(1)) > -40
            )
            print(
                f"part {ep['n']}: {'OK ' if ok else 'BAD'} {dur.group(1) if dur else '?'} "
                f"mean {mean.group(1) if mean else '?'} dB · pauses {meta(project, ep['n']).get('pauses', '?')}"
            )
        raise SystemExit(0)
    nums = [int(a) for a in args[1:] if a.isdigit()] or [e["n"] for e in mod.EPISODES]
    for n in nums:  # TTS serially first (cached), then render in parallel
        timeline(project, cfg, next(e for e in mod.EPISODES if e["n"] == n))
    mode = "keys" if "--keys" in flags else "video"
    with Pool(min(len(nums), os.cpu_count() or 4)) as pool:
        for r in pool.starmap(render, [(project, n, mode) for n in nums]):
            print(r)
