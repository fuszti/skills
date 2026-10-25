"""Landscape (1920x1080) explainer-video engine: timed sprites, narration-synced markers, keyword
captions, real screen recordings with a virtual camera. Element times are absolute seconds."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name
from pygments.token import Token

W, H, FPS = 1920, 1080, 30
SS = 2  # supersample factor for sprites
# 16:9 for a laptop screen: header y 40-170, content y 200-900, captions centred at y 972, footer y 1036.
X0, X1 = 80, 1840
CW = X1 - X0
CX = (X0 + X1) // 2
CONTENT_TOP, CONTENT_BOTTOM = 200, 900
Y0, Y1 = CONTENT_TOP, CONTENT_BOTTOM
CAPTION_Y = 972
# Two columns: a recording, code or diagram on the left; notes, evidence or a verdict on the right.
LEFT_W = 1010
RX = X0 + LEFT_W + 40
RW = X1 - RX
RCX = RX + RW // 2

BG = (11, 15, 23)
PANEL = (22, 27, 38)
PANEL2 = (30, 37, 51)
LINE = (58, 68, 88)
T1 = (240, 244, 250)
T2 = (190, 198, 212)
T3 = (130, 140, 160)
AMBER = (245, 176, 65)
GREEN = (74, 210, 140)
RED = (244, 98, 98)
BLUE = (100, 170, 255)
PURPLE = (190, 140, 255)

import os as _os_fonts

SANS = "/System/Library/Fonts/SFNS.ttf"
MONO = "/System/Library/Fonts/SFNSMono.ttf"
# Linux / cloud: static Inter + JetBrains Mono files in EXPLAINER_FONT_DIR (the setup script downloads them).
FONT_DIR = _os_fonts.environ.get("EXPLAINER_FONT_DIR", _os_fonts.path.expanduser("~/.local/share/explainer-fonts"))
_SANS_FILES = {
    "Regular": "Inter-Regular",
    "Medium": "Inter-Medium",
    "Semibold": "Inter-SemiBold",
    "Bold": "Inter-Bold",
    "Heavy": "Inter-ExtraBold",
    "Black": "Inter-Black",
}
_MONO_FILES = {
    "Regular": "JetBrainsMono-Regular",
    "Medium": "JetBrainsMono-Medium",
    "Semibold": "JetBrainsMono-Bold",
    "Bold": "JetBrainsMono-Bold",
    "Heavy": "JetBrainsMono-Bold",
}
USE_SF = _os_fonts.path.exists(SANS) and not _os_fonts.environ.get("EXPLAINER_FONT_DIR")
_fonts: dict = {}


def font(size: float, weight: str = "Regular", mono: bool = False):
    key = (round(size), weight, mono)
    if key not in _fonts:
        if USE_SF:
            f = ImageFont.truetype(MONO if mono else SANS, round(size))
            f.set_variation_by_name(weight)
        else:
            name = (_MONO_FILES if mono else _SANS_FILES).get(
                weight, "JetBrainsMono-Regular" if mono else "Inter-Regular"
            )
            path = _os_fonts.path.join(FONT_DIR, name + ".ttf")
            if not _os_fonts.path.exists(path):
                raise SystemExit(f"font {path} missing: run the setup script or set EXPLAINER_FONT_DIR")
            f = ImageFont.truetype(path, round(size))
        _fonts[key] = f
    return _fonts[key]


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def with_alpha(c, a=255):
    return (*c[:3], a)


# ---------------------------------------------------------------- elements
@dataclass
class El:
    t0: float
    t1: float | None = None
    rise: int = 22
    fade: float = 0.28
    z: int = 0
    _sprite: tuple | None = field(default=None, repr=False)

    def sprite(self):  # -> (RGBA image, x, y)
        if self._sprite is None:
            self._sprite = self.build()
        return self._sprite

    def build(self):
        raise NotImplementedError

    def alpha_at(self, t: float, end: float) -> float:
        t1 = self.t1 if self.t1 is not None else end
        if t < self.t0 or t >= t1:
            return 0.0
        a = ease((t - self.t0) / self.fade) if self.fade else 1.0
        out = min(1.0, (t1 - t) / 0.2)
        return max(0.0, min(a, out))

    def draw(self, frame: Image.Image, t: float, end: float):
        a = self.alpha_at(t, end)
        if a <= 0:
            return
        img, x, y = self.sprite()
        dy = int(self.rise * (1 - ease((t - self.t0) / max(self.fade, 1e-6)))) if self.rise else 0
        if a < 0.999:
            img = img.copy()
            alpha = img.getchannel("A").point(lambda v: int(v * a))
            img.putalpha(alpha)
        frame.alpha_composite(img, (int(x), int(y + dy)))


def _canvas(w, h):
    img = Image.new("RGBA", (int(w * SS), int(h * SS)), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _down(img):
    return img.resize((img.width // SS, img.height // SS), Image.LANCZOS)


def wrap(text: str, f, maxw: float) -> list[str]:
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            test = f"{line} {word}".strip()
            if f.getlength(test) <= maxw or not line:
                line = test
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


class Txt(El):
    def __init__(
        self,
        t0,
        x,
        y,
        text,
        size=44,
        color=T1,
        weight="Regular",
        mono=False,
        maxw=None,
        anchor="l",
        lh=1.22,
        t1=None,
        strike_color=None,
        **kw,
    ):
        super().__init__(t0, t1, **kw)
        self.x, self.y, self.text, self.size, self.color = x, y, text, size, color
        self.weight, self.mono, self.maxw, self.anchor, self.lh = weight, mono, maxw, anchor, lh

    def build(self):
        f = font(self.size * SS, self.weight, self.mono)
        lines = wrap(self.text, f, self.maxw * SS) if self.maxw else self.text.split("\n")
        lhp = self.size * SS * self.lh
        w = max(f.getlength(l) for l in lines) + 8 * SS
        h = lhp * len(lines) + 6 * SS
        img, d = _canvas(w / SS + 2, h / SS + 2)
        for i, l in enumerate(lines):
            lx = {"l": 0, "c": (w - f.getlength(l)) / 2, "r": w - f.getlength(l)}[self.anchor]
            d.text((lx, i * lhp), l, font=f, fill=with_alpha(self.color))
        img = _down(img)
        x = {"l": self.x, "c": self.x - img.width / 2, "r": self.x - img.width}[self.anchor]
        return img, x, self.y

    @property
    def size_px(self):
        img, _, _ = self.sprite()
        return img.size


# ---- icons (drawn in a s×s box at (x,y) on a supersampled draw)
def icon(d: ImageDraw.ImageDraw, name: str, x, y, s, c):
    w = max(2, int(s / 9))
    c = with_alpha(c)
    if name == "check":
        d.line(
            [(x + s * 0.15, y + s * 0.55), (x + s * 0.4, y + s * 0.78), (x + s * 0.85, y + s * 0.22)],
            fill=c,
            width=w,
            joint="curve",
        )
    elif name == "cross":
        d.line([(x + s * 0.2, y + s * 0.2), (x + s * 0.8, y + s * 0.8)], fill=c, width=w)
        d.line([(x + s * 0.8, y + s * 0.2), (x + s * 0.2, y + s * 0.8)], fill=c, width=w)
    elif name == "trash":
        d.rounded_rectangle(
            [x + s * 0.22, y + s * 0.3, x + s * 0.78, y + s * 0.92], radius=s * 0.08, outline=c, width=w
        )
        d.line([(x + s * 0.1, y + s * 0.22), (x + s * 0.9, y + s * 0.22)], fill=c, width=w)
        d.line([(x + s * 0.38, y + s * 0.1), (x + s * 0.62, y + s * 0.1)], fill=c, width=w)
        for k in (0.42, 0.58):
            d.line([(x + s * k, y + s * 0.42), (x + s * k, y + s * 0.8)], fill=c, width=max(1, w - 1))
    elif name == "pencil":
        d.line([(x + s * 0.2, y + s * 0.8), (x + s * 0.78, y + s * 0.22)], fill=c, width=int(w * 1.6))
        d.line([(x + s * 0.12, y + s * 0.88), (x + s * 0.22, y + s * 0.78)], fill=c, width=w)
    elif name == "db":
        d.ellipse([x + s * 0.15, y + s * 0.08, x + s * 0.85, y + s * 0.3], outline=c, width=w)
        d.line([(x + s * 0.15, y + s * 0.19), (x + s * 0.15, y + s * 0.82)], fill=c, width=w)
        d.line([(x + s * 0.85, y + s * 0.19), (x + s * 0.85, y + s * 0.82)], fill=c, width=w)
        d.arc([x + s * 0.15, y + s * 0.7, x + s * 0.85, y + s * 0.94], 0, 180, fill=c, width=w)
        d.arc([x + s * 0.15, y + s * 0.42, x + s * 0.85, y + s * 0.64], 0, 180, fill=c, width=w)
    elif name == "lock":
        d.rounded_rectangle(
            [x + s * 0.18, y + s * 0.45, x + s * 0.82, y + s * 0.92], radius=s * 0.08, outline=c, width=w
        )
        d.arc([x + s * 0.3, y + s * 0.1, x + s * 0.7, y + s * 0.62], 180, 360, fill=c, width=w)
        d.line([(x + s * 0.3, y + s * 0.36), (x + s * 0.3, y + s * 0.47)], fill=c, width=w)
        d.line([(x + s * 0.7, y + s * 0.36), (x + s * 0.7, y + s * 0.47)], fill=c, width=w)
    elif name == "person":
        d.ellipse([x + s * 0.33, y + s * 0.08, x + s * 0.67, y + s * 0.42], outline=c, width=w)
        d.arc([x + s * 0.12, y + s * 0.5, x + s * 0.88, y + s * 1.2], 180, 360, fill=c, width=w)
    elif name == "bot":
        d.rounded_rectangle(
            [x + s * 0.15, y + s * 0.3, x + s * 0.85, y + s * 0.88], radius=s * 0.14, outline=c, width=w
        )
        d.line([(x + s * 0.5, y + s * 0.1), (x + s * 0.5, y + s * 0.3)], fill=c, width=w)
        d.ellipse([x + s * 0.44, y + s * 0.03, x + s * 0.56, y + s * 0.15], fill=c)
        for k in (0.36, 0.64):
            d.ellipse([x + s * (k - 0.06), y + s * 0.5, x + s * (k + 0.06), y + s * 0.62], fill=c)
    elif name == "spark":
        cx, cy = x + s / 2, y + s / 2
        pts = []
        for i in range(8):
            r = s * (0.48 if i % 2 == 0 else 0.14)
            a = i * math.pi / 4 - math.pi / 2
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        d.polygon(pts, fill=c)
    elif name == "screen":
        d.rounded_rectangle(
            [x + s * 0.08, y + s * 0.15, x + s * 0.92, y + s * 0.72], radius=s * 0.06, outline=c, width=w
        )
        d.line([(x + s * 0.35, y + s * 0.88), (x + s * 0.65, y + s * 0.88)], fill=c, width=w)
        d.line([(x + s * 0.5, y + s * 0.72), (x + s * 0.5, y + s * 0.88)], fill=c, width=w)
    elif name == "lambda":
        f = font(s * 0.95, "Bold")
        d.text((x + s * 0.18, y - s * 0.05), "λ", font=f, fill=c)
    elif name == "test":
        d.ellipse([x + s * 0.05, y + s * 0.05, x + s * 0.95, y + s * 0.95], outline=c, width=w)
        icon(d, "check", x + s * 0.12, y + s * 0.12, s * 0.76, c[:3])


class Box(El):
    def __init__(
        self,
        t0,
        x,
        y,
        w,
        h,
        title="",
        sub=None,
        fill=PANEL,
        border=LINE,
        tcolor=T1,
        scolor=T3,
        tsize=40,
        ssize=28,
        icon_name=None,
        icolor=None,
        radius=20,
        align="c",
        bw=3,
        mono_sub=False,
        t1=None,
        **kw,
    ):
        super().__init__(t0, t1, **kw)
        self.__dict__.update(
            dict(
                x=x,
                y=y,
                w=w,
                h=h,
                title=title,
                sub=sub,
                fill=fill,
                border=border,
                tcolor=tcolor,
                scolor=scolor,
                tsize=tsize,
                ssize=ssize,
                icon_name=icon_name,
                icolor=icolor or tcolor,
                radius=radius,
                align=align,
                bw=bw,
                mono_sub=mono_sub,
            )
        )

    def build(self):
        img, d = _canvas(self.w, self.h)
        S = SS
        d.rounded_rectangle(
            [S, S, self.w * S - S, self.h * S - S],
            radius=self.radius * S,
            fill=with_alpha(self.fill) if self.fill else None,
            outline=with_alpha(self.border) if self.border else None,
            width=self.bw * S,
        )
        ft = font(self.tsize * S, "Bold")
        fs = font(self.ssize * S, "Regular", self.mono_sub)
        isz = self.tsize * 1.15 * S if self.icon_name else 0
        gap = 14 * S if self.icon_name else 0
        tlines = wrap(self.title, ft, (self.w - 40) * S - isz - gap) if self.title else []
        slines = wrap(self.sub, fs, (self.w - 40) * S) if self.sub else []
        th = len(tlines) * self.tsize * 1.18 * S
        sh = len(slines) * self.ssize * 1.25 * S + (8 * S if slines else 0)
        top = (self.h * S - th - sh) / 2
        for i, l in enumerate(tlines):
            lw = ft.getlength(l) + isz + gap
            lx = (self.w * S - lw) / 2 if self.align == "c" else 22 * S
            if i == 0 and self.icon_name:
                icon(d, self.icon_name, lx, top + self.tsize * 0.05 * S, isz, self.icolor)
            d.text((lx + isz + gap, top + i * self.tsize * 1.18 * S), l, font=ft, fill=with_alpha(self.tcolor))
        for i, l in enumerate(slines):
            lx = (self.w * S - fs.getlength(l)) / 2 if self.align == "c" else 22 * S
            d.text((lx, top + th + 8 * S + i * self.ssize * 1.25 * S), l, font=fs, fill=with_alpha(self.scolor))
        return _down(img), self.x, self.y


class Pill(El):
    def __init__(
        self,
        t0,
        x,
        y,
        text,
        fg=AMBER,
        bg=None,
        size=30,
        icon_name=None,
        anchor="l",
        weight="Semibold",
        outline=True,
        t1=None,
        **kw,
    ):
        super().__init__(t0, t1, **kw)
        self.__dict__.update(
            dict(
                x=x,
                y=y,
                text=text,
                fg=fg,
                bg=bg,
                size=size,
                icon_name=icon_name,
                anchor=anchor,
                weight=weight,
                outline=outline,
            )
        )

    def build(self):
        f = font(self.size * SS, self.weight)
        isz = self.size * 1.0 * SS if self.icon_name else 0
        gap = 10 * SS if self.icon_name else 0
        pw = f.getlength(self.text) + isz + gap + self.size * 1.1 * SS
        ph = self.size * 1.75 * SS
        img, d = _canvas(pw / SS + 2, ph / SS + 2)
        bg = self.bg or tuple(int(c * 0.16 + b * 0.84) for c, b in zip(self.fg, BG))
        d.rounded_rectangle(
            [0, 0, pw, ph],
            radius=ph / 2,
            fill=with_alpha(bg),
            outline=with_alpha(self.fg) if self.outline else None,
            width=2 * SS,
        )
        x = self.size * 0.55 * SS
        if self.icon_name:
            icon(d, self.icon_name, x, (ph - isz) / 2, isz, self.fg)
        d.text((x + isz + gap, ph / 2), self.text, font=f, fill=with_alpha(self.fg), anchor="lm")
        img = _down(img)
        x0 = {"l": self.x, "c": self.x - img.width / 2, "r": self.x - img.width}[self.anchor]
        return img, x0, self.y


class Rect(El):
    """Plain (optionally translucent) rounded rect — highlights, dims, rows."""

    def __init__(self, t0, x, y, w, h, fill=None, outline=None, alpha=255, radius=10, bw=3, t1=None, **kw):
        kw.setdefault("rise", 0)
        super().__init__(t0, t1, **kw)
        self.__dict__.update(dict(x=x, y=y, w=w, h=h, fill=fill, outline=outline, alpha=alpha, radius=radius, bw=bw))

    def build(self):
        img, d = _canvas(self.w, self.h)
        d.rounded_rectangle(
            [0, 0, self.w * SS - 1, self.h * SS - 1],
            radius=self.radius * SS,
            fill=with_alpha(self.fill, self.alpha) if self.fill else None,
            outline=with_alpha(self.outline) if self.outline else None,
            width=self.bw * SS,
        )
        return _down(img), self.x, self.y


class Arrow(El):
    """Polyline that is drawn in over `grow` seconds, with optional head and label."""

    def __init__(
        self,
        t0,
        pts,
        color=T2,
        width=5,
        head=True,
        dashed=False,
        label=None,
        lpos=None,
        lsize=27,
        lcolor=None,
        grow=0.45,
        t1=None,
        both=False,
        **kw,
    ):
        kw.setdefault("rise", 0)
        kw.setdefault("fade", 0.0)
        super().__init__(t0, t1, **kw)
        self.__dict__.update(
            dict(
                pts=pts,
                color=color,
                width=width,
                head=head,
                dashed=dashed,
                label=label,
                lpos=lpos,
                lsize=lsize,
                lcolor=lcolor or color,
                grow=grow,
                both=both,
            )
        )
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.bx, self.by = min(xs) - 30, min(ys) - 30
        self.bw, self.bh = max(xs) - min(xs) + 60, max(ys) - min(ys) + 60
        self._steps: dict = {}
        self._label = None
        if label:
            lx, ly = lpos if lpos else ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
            self._label = LabelTag(t0 + grow * 0.8, lx, ly, label, lsize, self.lcolor, t1=t1)

    def _render(self, p):
        img, d = _canvas(self.bw, self.bh)
        pts = [((x - self.bx) * SS, (y - self.by) * SS) for x, y in self.pts]
        segs = list(zip(pts, pts[1:]))
        total = sum(math.dist(a, b) for a, b in segs)
        left = total * p
        drawn = []
        for a, b in segs:
            L = math.dist(a, b)
            if left <= 0:
                break
            f = min(1, left / L) if L else 1
            e = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
            drawn.append((a, e))
            left -= L
        c = with_alpha(self.color)
        w = self.width * SS
        for a, e in drawn:
            if self.dashed:
                L = math.dist(a, e)
                n = int(L / (22 * SS)) + 1
                for i in range(n):
                    s0 = i / n
                    s1 = min(1, s0 + 0.55 / n)
                    d.line(
                        [
                            (a[0] + (e[0] - a[0]) * s0, a[1] + (e[1] - a[1]) * s0),
                            (a[0] + (e[0] - a[0]) * s1, a[1] + (e[1] - a[1]) * s1),
                        ],
                        fill=c,
                        width=w,
                    )
            else:
                d.line([a, e], fill=c, width=w)
                d.ellipse([e[0] - w / 2, e[1] - w / 2, e[0] + w / 2, e[1] + w / 2], fill=c)

        def head_at(a, e):
            ang = math.atan2(e[1] - a[1], e[0] - a[0])
            hl = 22 * SS
            d.polygon(
                [
                    e,
                    (e[0] - hl * math.cos(ang - 0.45), e[1] - hl * math.sin(ang - 0.45)),
                    (e[0] - hl * math.cos(ang + 0.45), e[1] - hl * math.sin(ang + 0.45)),
                ],
                fill=c,
            )

        if self.head and drawn:
            head_at(*drawn[-1])
        if self.both and drawn and p >= 1:
            head_at(pts[1], pts[0])
        return _down(img)

    def draw(self, frame, t, end):
        t1 = self.t1 if self.t1 is not None else end
        if t < self.t0 or t >= t1:
            return
        p = 1.0 if self.grow <= 0 else min(1.0, (t - self.t0) / self.grow)
        k = min(12, int(ease(p) * 12))
        if k not in self._steps:
            self._steps[k] = self._render(max(0.02, k / 12))
        img = self._steps[k]
        a = min(1.0, (t1 - t) / 0.2)
        if a < 0.999:
            img = img.copy()
            img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
        frame.alpha_composite(img, (int(self.bx), int(self.by)))
        if self._label and p >= 0.8:
            self._label.draw(frame, t, end)


class LabelTag(El):
    def __init__(self, t0, cx, cy, text, size, color, t1=None):
        super().__init__(t0, t1, rise=0, fade=0.2)
        self.cx, self.cy, self.text, self.size, self.color = cx, cy, text, size, color

    def build(self):
        f = font(self.size * SS, "Semibold")
        lines = self.text.split("\n")
        tw = max(f.getlength(l) for l in lines) + 22 * SS
        th = self.size * 1.25 * SS * len(lines) + 12 * SS
        img, d = _canvas(tw / SS + 1, th / SS + 1)
        d.rounded_rectangle([0, 0, tw, th], radius=10 * SS, fill=with_alpha(BG, 235))
        for i, l in enumerate(lines):
            d.text(
                (tw / 2, 6 * SS + self.size * 1.25 * SS * (i + 0.5)),
                l,
                font=f,
                fill=with_alpha(self.color),
                anchor="mm",
            )
        img = _down(img)
        return img, self.cx - img.width / 2, self.cy - img.height / 2


# ---- code panel
TOKEN_COLORS = [
    (Token.Comment, (125, 135, 155)),
    (Token.Keyword, (255, 123, 114)),
    (Token.Name.Builtin, (121, 192, 255)),
    (Token.Name.Function, (210, 168, 255)),
    (Token.Name.Class, (255, 166, 87)),
    (Token.Name.Tag, (126, 231, 135)),
    (Token.Name.Attribute, (121, 192, 255)),
    (Token.Literal.String, (165, 214, 255)),
    (Token.Literal.Number, (121, 192, 255)),
    (Token.Operator, (255, 123, 114)),
    (Token.Name.Decorator, (210, 168, 255)),
]


def tok_color(tt):
    for base, col in TOKEN_COLORS:
        if tt in base:
            return col
    return (225, 230, 238)


class Code(El):
    """Syntax-highlighted panel. Lines starting with '+ '/'- ' render as a diff."""

    def __init__(self, t0, x, y, lines, lang="python", size=40, w=CW, title=None, t1=None, **kw):
        super().__init__(t0, t1, **kw)
        self.x, self.y, self.lines, self.lang, self.size, self.w, self.title = x, y, lines, lang, size, w, title
        self.lh = int(size * 1.42)
        self.pad = 26
        self.top = self.pad + (52 if title else 0)

    @property
    def h(self):
        return self.top + self.lh * len(self.lines) + self.pad

    def line_box(self, i, j=None, x_pad=10):
        j = i if j is None else j
        return (self.x + x_pad, self.y + self.top + i * self.lh - 4, self.w - 2 * x_pad, (j - i + 1) * self.lh + 6)

    def build(self):
        img, d = _canvas(self.w, self.h)
        S = SS
        d.rounded_rectangle(
            [0, 0, self.w * S - 1, self.h * S - 1],
            radius=22 * S,
            fill=with_alpha((16, 20, 30)),
            outline=with_alpha(LINE),
            width=2 * S,
        )
        if self.title:
            for k, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
                d.ellipse([(22 + k * 26) * S, 20 * S, (38 + k * 26) * S, 36 * S], fill=with_alpha(col))
            d.text((112 * S, 28 * S), self.title, font=font(25 * S, "Medium"), fill=with_alpha(T3), anchor="lm")
            d.line([(0, 52 * S), (self.w * S, 52 * S)], fill=with_alpha(LINE), width=2 * S)
        f = font(self.size * S, "Regular", True)
        lexer = get_lexer_by_name(self.lang)
        for i, raw in enumerate(self.lines):
            y = (self.top + i * self.lh) * S
            x = self.pad * S
            diff = raw[:2] if raw[:2] in ("+ ", "- ") else None
            body = raw[2:] if diff else raw
            if diff:
                col = GREEN if diff == "+ " else RED
                d.rectangle([2 * S, y - 4 * S, self.w * S - 2 * S, y + (self.lh - 4) * S], fill=with_alpha(col, 38))
                d.text((x - 16 * S, y), diff[0], font=f, fill=with_alpha(col))
                x += 14 * S
            for tt, val in lex(body, lexer):
                val = val.rstrip("\n")
                if not val:
                    continue
                d.text((x, y), val, font=f, fill=with_alpha(tok_color(tt)))
                x += f.getlength(val)
        return _down(img), self.x, self.y

    def hl(self, t0, i, j=None, t1=None, color=AMBER):
        x, y, w, h = self.line_box(i, j)
        return Rect(t0, x, y, w, h, fill=color, alpha=40, outline=color, radius=10, bw=3, t1=t1, fade=0.18)

    def focus(self, t0, keep: list[int], t1=None):
        """Dim every line not in `keep`."""
        els = []
        for i in range(len(self.lines)):
            if i not in keep:
                x, y, w, h = self.line_box(i, x_pad=4)
                els.append(Rect(t0, x, y, w, h, fill=(16, 20, 30), alpha=170, radius=4, t1=t1, fade=0.2))
        return els


# ---------------------------------------------------------------- script parsing
TOKEN_RE = re.compile(r"\[(\w+)\]|\{([^|}]*)\|([^}]*)\}|(\S+)|(\s+)")


def parse(narration: str):
    """-> spoken text, markers {name: char_idx}, words [(display, start, end)]."""
    spoken, markers, words = "", {}, []
    for m in TOKEN_RE.finditer(narration):
        if m.group(1):
            markers[m.group(1)] = len(spoken)
        elif m.group(2) is not None:
            s = len(spoken)
            spoken += m.group(3)
            words.append([m.group(2), s, len(spoken)])
        elif m.group(4):
            s = len(spoken)
            spoken += m.group(4)
            tok = m.group(4)
            if words and re.fullmatch(r"[\.,:;!?…]+", tok):
                words[-1][0] += tok
                words[-1][2] = len(spoken)
            else:
                words.append([tok, s, len(spoken)])
        else:
            spoken += " "
    return spoken, markers, words


def char_time(align, idx, end=False):
    st, en = align["character_start_times_seconds"], align["character_end_times_seconds"]
    idx = max(0, min(idx, len(st) - 1))
    return en[idx] if end else st[idx]


# ---------------------------------------------------------------- captions
class Captions:
    def __init__(self, words_t, emphasis=()):
        self.chunks = []
        cur = []
        for w in words_t:
            cur.append(w)
            text = " ".join(x[0] for x in cur)
            if len(cur) >= 4 or len(text) >= 26 or re.search(r"[\.,:;!?]$", w[0]):
                self.chunks.append(cur)
                cur = []
        if cur:
            self.chunks.append(cur)
        self.emph = {re.sub(r"[^\w#\-/·]", "", e).lower() for e in emphasis}
        self._cache: dict = {}

    def _img(self, k):
        if k in self._cache:
            return self._cache[k]
        words = [w[0] for w in self.chunks[k]]
        f = font(52 * SS, "Heavy")
        parts = []
        for wd in words:
            clean = re.sub(r"[^\w#\-/·]", "", wd).lower()
            parts.append((wd, AMBER if clean in self.emph else T1))
        text = " ".join(p[0] for p in parts)
        tw = f.getlength(text)
        pad = 26 * SS
        img, d = _canvas(tw / SS + 2 * pad / SS, 88)
        d.rounded_rectangle([0, 0, tw + 2 * pad, 88 * SS], radius=22 * SS, fill=(0, 0, 0, 175))
        x = pad
        for wd, col in parts:
            d.text((x, 44 * SS), wd, font=f, fill=with_alpha(col), anchor="lm")
            x += f.getlength(wd + " ")
        img = _down(img)
        if img.width > CW:
            img = img.resize((CW, int(img.height * CW / img.width)), Image.LANCZOS)
        self._cache[k] = img
        return img

    def draw(self, frame, t):
        for k, ch in enumerate(self.chunks):
            start = ch[0][1]
            nxt = self.chunks[k + 1][0][1] if k + 1 < len(self.chunks) else ch[-1][2] + 0.4
            end = min(nxt, ch[-1][2] + 0.6)
            if start <= t < end:
                img = self._img(k)
                pop = ease((t - start) / 0.12)
                if pop < 1:
                    s = 0.9 + 0.1 * pop
                    img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))))
                frame.alpha_composite(img, (int((X0 + X1) / 2 - img.width / 2), int(CAPTION_Y - img.height / 2)))
                return


# ---------------------------------------------------------------- real screen recordings
import bisect
import json as _json
import os as _os

SCR_X, SCR_Y, SCR_W, SCR_H = X0, CONTENT_TOP, LEFT_W, 710  # 1280x900 recordings fit at 0.79
REC_DIR = "rec"  # build.py points this at <project>/rec

# Per-series text; build.py fills it from the project's episodes.SERIES.
SERIES = {"tag": "PR #000", "footer": "", "badge": "REAL UI"}


class Clip:
    _all: dict = {}

    @classmethod
    def get(cls, name):
        if name not in cls._all:
            cls._all[name] = Clip(name)
        return cls._all[name]

    def __init__(self, name):
        d = _json.load(open(_os.path.join(REC_DIR, name, "clip.json")))
        self.dir = _os.path.join(REC_DIR, name)
        f0 = d["frames"][0]["t"]
        self.times = [f["t"] - f0 for f in d["frames"]]
        self.files = [f["f"] for f in d["frames"]]
        self.dsf = d["dsf"]
        self.end = self.times[-1]
        self.events = {}
        for e in d["events"]:
            b = e["box"]
            self.events[e["label"]] = (e["t"] - f0, (b["x"], b["y"], b["width"], b["height"]) if b else None)
        self._cache = {}

    def frame(self, ct):
        i = max(0, min(len(self.times) - 1, bisect.bisect_right(self.times, ct) - 1))
        if i not in self._cache:
            if len(self._cache) > 4:
                self._cache.pop(next(iter(self._cache)))
            self._cache[i] = Image.open(_os.path.join(self.dir, self.files[i])).convert("RGB")
        return self._cache[i]


def cam_for(box, max_zoom=2.3, lift=0):
    """Camera (cx, cy, s) in CSS px; s = output px per CSS px. Captions sit below the screen, so the
    target is centred."""
    if box == "full":
        return (640.0, 450.0, SCR_W / 1280)
    x, y, w, h = box
    s = max(SCR_W / 1280, min(SCR_W / (w + 70), (SCR_H - 40) / (h + 60), max_zoom))
    cx, cy = x + w / 2, y + h / 2 + lift / s
    hw, hh = SCR_W / 2 / s, SCR_H / 2 / s
    if 2 * hw <= 1280:
        cx = min(max(cx, hw), 1280 - hw)
    if 2 * hh <= 900:
        cy = min(max(cy, hh), 900 - hh)
    return (cx, cy, s)


class Screen(El):
    """A recorded clip in the content box. shots: [(t_video, clip_t, cam)], each plays at 1x from clip_t."""

    def __init__(self, t0, clip, shots, t1=None, badge=True, **kw):
        kw.setdefault("rise", 0)
        super().__init__(t0, t1, **kw)
        self.clip = Clip.get(clip)
        self.shots = sorted(shots, key=lambda s: s[0])
        self.badge = badge
        mask = Image.new("L", (SCR_W * SS, SCR_H * SS), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, SCR_W * SS - 1, SCR_H * SS - 1], radius=22 * SS, fill=255)
        self.mask = mask.resize((SCR_W, SCR_H), Image.LANCZOS)
        ov, d = _canvas(SCR_W, SCR_H)
        d.rounded_rectangle(
            [0, 0, SCR_W * SS - 1, SCR_H * SS - 1], radius=22 * SS, outline=with_alpha(LINE), width=3 * SS
        )
        self.overlay = _down(ov)
        self.tag = (
            Pill(0, SCR_X + 16, SCR_Y + 14, SERIES["badge"], RED, size=20, bg=(20, 10, 12), icon_name="spark")
            if badge
            else None
        )

    def cam_at(self, t):
        i = max(0, bisect.bisect_right([s[0] for s in self.shots], t) - 1)
        cur = self.shots[i][2]
        if i == 0:
            return cur, i
        prev = self.shots[i - 1][2]
        k = ease((t - self.shots[i][0]) / 0.75)
        if k >= 1:
            return cur, i
        # zoom in log space so a big zoom change does not lurch
        s = math.exp(math.log(prev[2]) + (math.log(cur[2]) - math.log(prev[2])) * k)
        return (prev[0] + (cur[0] - prev[0]) * k, prev[1] + (cur[1] - prev[1]) * k, s), i

    def draw(self, frame, t, end):
        a = self.alpha_at(t, end)
        if a <= 0:
            return
        (cx, cy, s), i = self.cam_at(t)
        tv, ct, _cam, *rest = self.shots[i]
        rate = rest[0] if rest else 1.0
        img = self.clip.frame(ct + (t - tv) * rate)
        dsf = self.clip.dsf
        k = s / dsf
        x0, y0 = (cx - SCR_W / 2 / s) * dsf, (cy - SCR_H / 2 / s) * dsf
        x1, y1 = x0 + SCR_W / k, y0 + SCR_H / k
        ix0, iy0, ix1, iy1 = max(0, x0), max(0, y0), min(img.width, x1), min(img.height, y1)
        out = Image.new("RGB", (SCR_W, SCR_H), (8, 10, 14))
        if ix1 > ix0 and iy1 > iy0:
            region = img.crop((int(ix0), int(iy0), int(ix1), int(iy1)))
            w, h = max(1, round((ix1 - ix0) * k)), max(1, round((iy1 - iy0) * k))
            region = region.resize((w, h), Image.BILINEAR, reducing_gap=2.0 if k < 1 else None)
            out.paste(region, (round((ix0 - x0) * k), round((iy0 - y0) * k)))
        out = out.convert("RGBA")
        out.putalpha(self.mask if a >= 0.999 else self.mask.point(lambda v: int(v * a)))
        frame.alpha_composite(out, (SCR_X, SCR_Y))
        if a >= 0.999:
            frame.alpha_composite(self.overlay, (SCR_X, SCR_Y))
            if self.tag:
                sp, x, y = self.tag.sprite()
                frame.alpha_composite(sp, (int(x), int(y)))


def shot(tv, clip, label=None, lead=0.5, box=None, ct=None, **cam):
    """A shot that starts at narration time tv on clip event `label` (or clip time ct), framed on the
    event's element box (or `box`)."""
    c = Clip.get(clip)
    et, ebox = c.events.get(label, (0.0, None)) if label else (0.0, None)
    start = ct if ct is not None else max(0.0, et - lead)
    return (tv, start, cam_for(box or ebox or "full", **cam))


# ---------------------------------------------------------------- composite helpers


def lifelines(t0, names, xs, top=CONTENT_TOP + 10, bottom=CONTENT_BOTTOM, icons=None):
    """UML sequence-diagram heads + dashed lifelines. Pair with msg()."""
    els = []
    for k, (n, x) in enumerate(zip(names, xs)):
        els.append(
            Box(
                t0 + k * 0.12,
                x - 125,
                top,
                250,
                86,
                n,
                tsize=32,
                icon_name=(icons or [None] * len(names))[k],
                fill=PANEL2,
            )
        )
        els.append(
            Arrow(
                t0 + 0.2 + k * 0.12,
                [(x, top + 90), (x, bottom)],
                color=LINE,
                width=3,
                head=False,
                dashed=True,
                grow=0.5,
            )
        )
    return els


def msg(t0, x0, x1, y, label, color=T2, dashed=False, lsize=26):
    """One sequence-diagram message; dashed = a reply."""
    return Arrow(
        t0,
        [(x0, y), (x1, y)],
        color=color,
        dashed=dashed,
        label=label,
        lpos=((x0 + x1) / 2, y - 26),
        lsize=lsize,
        lcolor=color if color != T2 else T1,
        grow=0.4,
    )


def review_card(m, keys, title, bullets):
    """'REVIEW CHECK' card. keys: marker names; keys[0] shows the card, keys[k+1] reveals bullet k."""
    t0 = m[keys[0]]
    top = CONTENT_TOP + 10
    els = [
        Pill(t0, X0 + 30, top + 22, "REVIEW CHECK", AMBER, size=24, icon_name="check"),
        Txt(t0, X0 + 30, top + 88, title, 44, T1, "Heavy", maxw=CW - 60),
    ]
    y = top + 88 + els[-1].size_px[1] + 26
    for k, b in enumerate(bullets):
        t = m[keys[k + 1]] if k + 1 < len(keys) else m[keys[-1]] + 1.2 * (k + 2 - len(keys))
        tx = Txt(t, X0 + 62, y, b, 32, T1, maxw=CW - 100, lh=1.28)
        els += [Rect(t, X0 + 32, y + 14, 14, 14, fill=AMBER, radius=3), tx]
        y += tx.size_px[1] + 22
    panel = Rect(t0, X0, top, CW, y - top + 14, fill=PANEL, outline=AMBER, radius=22, bw=3, rise=12)
    return [panel, *els]


def with_shots(clip, m, plan, t1=None):
    """A Screen from a shot plan. plan rows: (marker|seconds, event_label|None, css_box|"full", lead|None,
    clip_time|None, rate). With an event label the shot starts `lead` s before that event; else at clip_time."""
    shots = []
    for when, label, box, lead, ct, rate in plan:
        tv = m[when] if isinstance(when, str) else when
        s = shot(tv, clip, label, lead=lead if lead is not None else 0.5, box=box, ct=ct)
        shots.append((s[0], s[1], s[2], rate))
    return Screen(shots[0][0], clip, shots, t1=t1)


def log_panel(t0, lines, title, size=30, t1=None, y=CONTENT_TOP, x=X0, w=CW):
    """Raw log / test output lines (plain text lexer). Redact secrets and PII before you pass them in.
    x=RX, w=RW puts it in the right column next to a recording."""
    return Code(t0, x, y, lines, lang="text", size=size, w=w, title=title, t1=t1)


def waterfall(t0, spans, total_ms=None, y=CONTENT_TOP + 50, row_h=50, label_w=480, step=0.22, reveal=None, t1=None):
    """Trace waterfall. spans: [{name, start_ms, dur_ms, depth, color?, note?}] in display order.
    reveal: optional list of times, one per span (else t0 + i*step)."""
    total = total_ms or max(s["start_ms"] + s["dur_ms"] for s in spans)
    bar_w = CW - label_w - 10
    els = [
        Txt(t0, X0, y - 44, "0 ms", 22, T3, mono=True, t1=t1),
        Txt(t0, X1, y - 44, f"{total / 1000:.1f} s", 22, T3, mono=True, anchor="r", t1=t1),
    ]
    for i, sp in enumerate(spans):
        t = reveal[i] if reveal else t0 + i * step
        ry = y + i * row_h
        col = sp.get("color", BLUE)
        name = sp["name"] if len(sp["name"]) <= 34 else sp["name"][:33] + "…"
        els.append(Txt(t, X0 + 16 * sp.get("depth", 0), ry + 8, name, 24, T2, mono=True, t1=t1))
        bx = X0 + label_w + bar_w * sp["start_ms"] / total
        bw = max(4, bar_w * sp["dur_ms"] / total)
        els.append(Rect(t, bx, ry + 6, bw, row_h - 14, fill=col, alpha=200, radius=5, t1=t1))
        if sp.get("note"):
            if bx + bw + 8 + 13 * len(sp["note"]) <= X1:
                els.append(Txt(t + 0.2, bx + bw + 8, ry + 8, sp["note"], 21, col, "Semibold", t1=t1))
            else:  # no room right of the bar: write it inside the bar
                els.append(Txt(t + 0.2, bx + 8, ry + 8, sp["note"], 21, BG, "Bold", t1=t1))
    return els


def state(t0, x, y, w, name, color=AMBER, h=100, tsize=34, t1=None):
    """UML state (rounded pill). Connect states with Arrow polylines; the initial state is
    Rect(t0, x, y, 32, 32, fill=T1, radius=16) plus an Arrow."""
    return Box(t0, x, y, w, h, name, fill=PANEL2, border=color, tcolor=color, radius=h // 2, tsize=tsize, t1=t1)


# ---------------------------------------------------------------- check parts (question → guess → experiment → verdict)
class Stamp(El):
    """Rotated verdict stamp that pops in (scale 1.5 → 1.0)."""

    def __init__(self, t0, cx, cy, text, color, size=64, angle=-8, t1=None):
        super().__init__(t0, t1, rise=0, fade=0.12)
        self.cx, self.cy, self.text, self.color, self.size, self.angle = cx, cy, text, color, size, angle

    def build(self):
        f = font(self.size * SS, "Heavy")
        tw = f.getlength(self.text)
        pad = self.size * 0.45 * SS
        w, h = tw + 2 * pad, self.size * 1.5 * SS
        img = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [3 * SS, 3 * SS, w - 3 * SS, h - 3 * SS],
            radius=14 * SS,
            outline=with_alpha(self.color),
            width=6 * SS,
            fill=with_alpha(BG, 225),
        )
        d.text((w / 2, h / 2), self.text, font=f, fill=with_alpha(self.color), anchor="mm")
        img = _down(img).rotate(self.angle, expand=True, resample=Image.BICUBIC)
        return img, self.cx - img.width / 2, self.cy - img.height / 2

    def draw(self, frame, t, end):
        a = self.alpha_at(t, end)
        if a <= 0:
            return
        img, _, _ = self.sprite()
        k = ease((t - self.t0) / 0.22)
        s = 1.5 - 0.5 * k
        if s > 1.001:
            img = img.resize((int(img.width * s), int(img.height * s)), Image.BILINEAR)
        if a < 0.999:
            img = img.copy()
            img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
        frame.alpha_composite(img, (int(self.cx - img.width / 2), int(self.cy - img.height / 2)))


VERDICT_COLORS = {"VERIFIED": GREEN, "FAILED": RED, "NOT RUN": AMBER, "YOUR CALL": BLUE}


def check_question(t0, k, question, t1=None):
    """Opening of a check part: 'CHECK k' pill + the question in big type."""
    return [
        Pill(t0, X0, CONTENT_TOP + 6, f"CHECK {k}", PURPLE, size=26, icon_name="test", t1=t1),
        Txt(t0 + 0.15, X0, CONTENT_TOP + 66, question, 56, T1, "Heavy", maxw=CW, lh=1.15, t1=t1),
    ]


def guess(t0, options, reveal, correct, y=CONTENT_TOP + 300, x=X0, w=LEFT_W, t1=None):
    """'Pause and guess' choices, in the left column under the question. At `reveal` the correct one turns
    green and the rest dim. correct: index, or None when the experiment did not run (nothing is revealed).
    The feed pauses the video where the narration says "Pause and guess", so say it after the options appear."""
    label = "The answer" if correct is not None and reveal is not None else "Pause and guess"
    els = [Txt(t0, X0, y - 52, label, 28, PURPLE, "Bold", t1=t1)]
    for i, opt in enumerate(options):
        oy = y + i * 108
        els.append(
            Box(
                t0 + 0.15 * i,
                x,
                oy,
                w,
                92,
                f"{'ABC'[i]}   {opt}",
                fill=PANEL,
                border=LINE,
                tsize=32,
                align="l",
                radius=16,
                t1=t1,
            )
        )
        if correct is not None and reveal is not None:
            if i == correct:
                els.append(Rect(reveal, x, oy, w, 92, outline=GREEN, radius=16, bw=5, t1=t1, fade=0.15))
            else:
                els.append(Rect(reveal, x, oy, w, 92, fill=BG, alpha=170, radius=16, t1=t1, fade=0.15))
    return els


def verdict(t0, state, evidence=None, cy=CONTENT_TOP + 330, question=None, cx=RCX, maxw=RW, t1=None):
    """The reveal: a VERIFIED / FAILED / NOT RUN / YOUR CALL stamp, with one evidence line under it.
    question: a verified trade-off still needs a person's decision -> a blue "Your call:" line."""
    col = VERDICT_COLORS[state]
    els = [Stamp(t0, cx, cy, state, col, t1=t1)]
    if evidence:
        els.append(Txt(t0 + 0.5, cx, cy + 90, evidence, 30, T2, anchor="c", maxw=maxw, t1=t1))
    if question:
        els.append(
            Txt(t0 + 1.0, cx, cy + 150, f"Your call: {question}", 30, BLUE, "Semibold", anchor="c", maxw=maxw, t1=t1)
        )
    return els


def test_panel(t0, lines, title="pytest", passed_at=None, y=CONTENT_TOP, size=30, x=X0, w=CW, t1=None):
    """Test-runner output; lines with PASSED / ✓ turn green and FAILED / ✗ red at `passed_at`."""
    c = Code(t0, x, y, lines, lang="text", size=size, w=w, title=title, t1=t1)
    els = [c]
    if passed_at is not None:
        for i, ln in enumerate(lines):
            if "PASSED" in ln or "✓" in ln or " passed" in ln:
                els.append(c.hl(passed_at + 0.08 * i, i, color=GREEN, t1=t1))
            elif "FAILED" in ln or "✗" in ln or "×" in ln or " failed" in ln:
                els.append(c.hl(passed_at + 0.08 * i, i, color=RED, t1=t1))
    return els


# ---------------------------------------------------------------- flow animation (mental-model parts)
def _along(pts, k):
    """The point at fraction k (0..1) of a polyline's length."""
    segs = [(a, b, math.dist(a, b)) for a, b in zip(pts, pts[1:])]
    d = k * (sum(s[2] for s in segs) or 1)
    for i, (a, b, seg) in enumerate(segs):
        if d <= seg or i == len(segs) - 1:
            f = 0 if seg == 0 else min(1.0, d / seg)
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        d -= seg
    return pts[-1]


def _faded(img, a):
    if a >= 0.999:
        return img
    img = img.copy()
    img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return img


class Packet(El):
    """A labelled chip that travels along `pts` from t0 to t0 + dur, then waits at the end for `hold` s (or
    until t1). Follow one real request, id or object hop by hop with it: the label is the real value."""

    def __init__(self, t0, pts, text, color=AMBER, dur=0.9, hold=0.8, size=24, icon_name=None, t1=None, **kw):
        kw.setdefault("rise", 0)
        kw.setdefault("fade", 0.12)
        super().__init__(t0, t1 if t1 is not None else (t0 + dur + hold if hold is not None else None), **kw)
        self.pts, self.dur = pts, dur
        self.pill = Pill(0, 0, 0, text, color, size=size, icon_name=icon_name, bg=(12, 16, 24))

    def draw(self, frame, t, end):
        a = self.alpha_at(t, end)
        if a <= 0:
            return
        img = _faded(self.pill.sprite()[0], a)
        # Start and stop half a chip away from the ends, so the chip never covers the boxes it connects.
        length = sum(math.dist(p, q) for p, q in zip(self.pts, self.pts[1:])) or 1
        (x0, y0), (x1, y1) = self.pts[0], self.pts[-1]
        half = (img.width if abs(x1 - x0) >= abs(y1 - y0) else img.height) / 2 + 8
        lo, hi = (half / length, 1 - half / length) if length > 2 * half else (0.5, 0.5)
        k = ease(min(1.0, max(0.0, (t - self.t0) / self.dur)))
        x, y = _along(self.pts, lo + (hi - lo) * k)
        frame.alpha_composite(img, (int(x - img.width / 2), int(y - img.height / 2)))


class Pulse(El):
    """A glowing outline that breathes around a box while the narration names it."""

    def __init__(self, t0, x, y, w, h, color=AMBER, t1=None, period=1.1, radius=22, **kw):
        kw.setdefault("rise", 0)
        kw.setdefault("fade", 0.15)
        super().__init__(t0, t1, **kw)
        self.__dict__.update(dict(x=x, y=y, w=w, h=h, color=color, period=period, radius=radius))

    def build(self):
        pad = 10
        img, d = _canvas(self.w + 2 * pad, self.h + 2 * pad)
        for k, (inset, width, alpha) in enumerate([(0, 10, 60), (4, 6, 120), (8, 4, 255)]):
            d.rounded_rectangle(
                [inset * SS, inset * SS, (self.w + 2 * pad - inset) * SS, (self.h + 2 * pad - inset) * SS],
                radius=(self.radius + pad - inset) * SS,
                outline=with_alpha(self.color, alpha),
                width=width * SS,
            )
        return _down(img), self.x - pad, self.y - pad

    def draw(self, frame, t, end):
        a = self.alpha_at(t, end)
        if a <= 0:
            return
        img, x, y = self.sprite()
        a *= 0.6 + 0.4 * math.sin((t - self.t0) * 2 * math.pi / self.period) ** 2
        frame.alpha_composite(_faded(img, a), (int(x), int(y)))


class SystemMap:
    """One layout of the system, reused in every part, so the viewer's spatial memory builds up part by part.

    nodes: {key: (x, y, w, h, title, sub, icon, color)}. Keep the same nodes and positions across the series;
    a part shows the nodes it needs and dims the rest with focus()."""

    def __init__(self, nodes, routes=None):
        self.nodes = nodes
        self.routes = routes or {}  # {(a, b): [(x, y), ...]} for an edge that must bend around a box

    @classmethod
    def load(cls, path):
        """The repo's own map (docs/agents/system-map.json), so every thread about a repo draws the same system at
        the same places: {"nodes": {key: {x, y, w, h, title, sub, icon, color}}, "routes": {"a>b": [[x, y], ...]}}.
        color is a name: amber, green, red, blue, purple, t2."""
        import json

        names = {"amber": AMBER, "green": GREEN, "red": RED, "blue": BLUE, "purple": PURPLE, "t2": T2}
        d = json.load(open(path))
        nodes = {
            k: (n["x"], n["y"], n["w"], n["h"], n["title"], n.get("sub"), n.get("icon"), names[n.get("color", "amber")])
            for k, n in d["nodes"].items()
        }
        routes = {tuple(k.split(">")): [tuple(p) for p in pts] for k, pts in d.get("routes", {}).items()}
        return cls(nodes, routes)

    def rect(self, k):
        x, y, w, h = self.nodes[k][:4]
        return x, y, w, h

    def center(self, k):
        x, y, w, h = self.rect(k)
        return x + w / 2, y + h / 2

    def anchor(self, a, b):
        """Where an edge from a toward b leaves a: the middle of the side that faces b."""
        x, y, w, h = self.rect(a)
        (ax, ay), (bx, by) = self.center(a), self.center(b)
        if abs(bx - ax) * h >= abs(by - ay) * w:
            return (x + w + 4, ay) if bx > ax else (x - 4, ay)
        return (ax, y + h + 4) if by > ay else (ax, y - 4)

    def path(self, a, b, shift=0):
        """Straight path from a to b; `shift` moves it sideways (px) so two edges between the same pair do not
        overlap (a request and its reply)."""
        if (a, b) in self.routes:
            return [(x, y + shift) for x, y in self.routes[(a, b)]]
        if (b, a) in self.routes:
            return [(x, y + shift) for x, y in reversed(self.routes[(b, a)])]
        p, q = self.anchor(a, b), self.anchor(b, a)
        if abs(q[0] - p[0]) >= abs(q[1] - p[1]):
            return [(p[0], p[1] + shift), (q[0], q[1] + shift)]
        return [(p[0] + shift, p[1]), (q[0] + shift, q[1])]

    def show(self, t0, keys=None, step=0.12, t1=None, tsize=30, ssize=21):
        els = []
        for i, k in enumerate(keys or list(self.nodes)):
            x, y, w, h, title, sub, ic, col = self.nodes[k]
            els.append(
                Box(t0 + i * step, x, y, w, h, title, sub, icon_name=ic, icolor=col, tsize=tsize, ssize=ssize, t1=t1)
            )
        return els

    def edge(self, t0, a, b, label=None, color=LINE, dashed=False, shift=0, t1=None, lsize=22):
        pts = self.path(a, b, shift)
        i = (len(pts) - 1) // 2
        mid = ((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2 - 22)
        return Arrow(
            t0,
            pts,
            color=color,
            width=4,
            dashed=dashed,
            label=label,
            lpos=mid if label else None,
            lsize=lsize,
            lcolor=color if color != LINE else T2,
            t1=t1,
        )

    def focus(self, t0, keep, t1=None, alpha=175):
        """Dim every node not in `keep` (the 'you are here' view)."""
        return [
            Rect(t0, x - 2, y - 2, w + 4, h + 4, fill=BG, alpha=alpha, radius=20, t1=t1, fade=0.25)
            for k, (x, y, w, h, *_r) in self.nodes.items()
            if k not in keep
        ]

    def pulse(self, t0, k, color=AMBER, t1=None):
        return Pulse(t0, *self.rect(k), color=color, t1=t1)

    def packet(self, t0, a, b, text, color=AMBER, dur=0.9, hold=0.8, shift=0, **kw):
        return Packet(t0, self.path(a, b, shift), text, color, dur=dur, hold=hold, **kw)

    def note(self, t0, k, lines, side="below", w=None, size=20, t1=None, color=T2):
        """A log line or fact that pops up at the component that wrote it (spatial contiguity)."""
        x, y, bw, bh = self.rect(k)
        w = w or max(bw, max(font(size, mono=True).getlength(ln) for ln in lines) + 28)
        h = 16 + len(lines) * size * 1.45
        nx = min(max(x + bw / 2 - w / 2, X0), X1 - w)
        ny = {"below": y + bh + 12, "above": y - h - 12}[side]
        els = [Rect(t0, nx, ny, w, h, fill=(12, 16, 24), outline=color, alpha=240, radius=10, bw=2, t1=t1, fade=0.2)]
        for i, ln in enumerate(lines):
            els.append(Txt(t0, nx + 12, ny + 8 + i * size * 1.45, ln, size, color, mono=True, t1=t1))
        return els


def store(t0, x, y, w, title, shelves, color=GREEN, icon_name="db", shelf_h=78, t1=None):
    """A data store drawn as a container with labelled shelves (bucket prefixes, tables, keys). Returns
    (elements, slots): slots[i] is the (x, y, w, h) of shelf i, for store_item()."""
    h = 70 + len(shelves) * (shelf_h + 10)
    els = [
        Box(t0, x, y, w, h, "", fill=PANEL, border=color, radius=18, t1=t1),
        Txt(t0, x + 20, y + 16, title, 28, color, "Bold", t1=t1),
    ]
    if icon_name:
        els[-1] = Pill(t0, x + 16, y + 12, title, color, size=24, icon_name=icon_name, t1=t1)
    slots = []
    for i, name in enumerate(shelves):
        sy = y + 64 + i * (shelf_h + 10)
        els.append(
            Rect(t0 + 0.1 * i, x + 14, sy, w - 28, shelf_h, fill=BG, outline=LINE, alpha=255, radius=10, bw=2, t1=t1)
        )
        els.append(Txt(t0 + 0.1 * i, x + 28, sy + 8, name, 20, T3, "Semibold", mono=True, t1=t1))
        slots.append((x + 14, sy, w - 28, shelf_h))
    return els, slots


def store_item(t0, slot, text, color=GREEN, col=0.0, deleted_at=None, size=21, t1=None, icon_name=None, row=0):
    """A chip that drops into a shelf of a store at t0, at `col` (0..1) of the shelf width. deleted_at: the chip is
    struck through there and fades out."""
    sx, sy, sw, sh = slot
    x, y = sx + 14 + col * sw, sy + sh - 34 - row * 40
    end = t1 if deleted_at is None else deleted_at + 0.9
    els = [Pill(t0, x, y, text, color, size=size, icon_name=icon_name, t1=end, rise=-36, fade=0.3)]
    if deleted_at is not None:
        tw = font(size).getlength(text) + size * 1.6 + (size if icon_name else 0)
        els.append(
            Arrow(
                deleted_at,
                [(x - 6, y + size * 0.9), (x + tw + 6, y + size * 0.9)],
                color=RED,
                width=4,
                head=False,
                grow=0.3,
                t1=end,
            )
        )
    return els


def timeline(t0, x, y, w, marks, color=AMBER, t1=None):
    """A time axis with labelled marks: marks = [(fraction 0..1, label, sub, time it appears)]."""
    els = [Arrow(t0, [(x, y), (x + w, y)], color=LINE, width=4, t1=t1)]
    for frac, label, sub, tm in marks:
        mx = x + w * frac
        els.append(Rect(tm, mx - 9, y - 9, 18, 18, fill=color, radius=9, t1=t1))
        els.append(Txt(tm, mx, y - 62, label, 26, T1, "Bold", anchor="c", t1=t1))
        if sub:
            els.append(Txt(tm + 0.1, mx, y + 24, sub, 21, T3, anchor="c", t1=t1))
    return els
