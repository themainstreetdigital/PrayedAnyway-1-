"""Episode 01 video renderer.

Renders the full episode from the beat timeline: graded Pexels footage with
slow push-ins, generated motion-graphics beats (title, texts, generations,
psalm card, silence hold, end card), text overlays, the strike flash, grain,
vignette — then muxes the mixed audio.

Parallelism: beats are split into contiguous chunks rendered by worker
subprocesses, then concatenated.

Usage:
  python3 production/render_episode.py                 # full render
  python3 production/render_episode.py --chunk i n     # worker mode
  python3 production/render_episode.py --preview ID    # one beat, for QC
"""

import json
import math
import os
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(__file__))
from timeline import compute

W, H, FPS = 1920, 1080, 24
FF = imageio_ffmpeg.get_ffmpeg_exe()

INK = np.array([14, 17, 22], np.float32)
SLATE = np.array([42, 49, 64], np.float32)
LAVENDER = np.array([110, 94, 140], np.float32)
AMBER = np.array([224, 164, 88], np.float32)
BONE = (232, 225, 213)

FONT_DIR = "/mnt/skills/examples/canvas-design/canvas-fonts"
F_HAND = f"{FONT_DIR}/NothingYouCouldDo-Regular.ttf"
F_TITLE = f"{FONT_DIR}/Gloock-Regular.ttf"
F_SERIF_I = f"{FONT_DIR}/CrimsonPro-Italic.ttf"
F_SERIF = f"{FONT_DIR}/CrimsonPro-Regular.ttf"

WARM_SECTIONS = {"strike", "act3", "end"}


# --------------------------------------------------------------- shared helpers

def env(t, t0, t1, fin=0.8, fout=0.8):
    if t < t0 or t > t1:
        return 0.0
    return min(1.0, (t - t0) / fin, (t1 - t) / fout)


def text_layer(lines, font_path, size, fill, y_frac, spacing=1.5, tracking=0.0,
               shadow=False):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, size)
    line_h = size * spacing
    y = H * y_frac - line_h * (len(lines) - 1) / 2
    for line in lines:
        widths = [font.getlength(c) + tracking for c in line]
        total = sum(widths) - tracking
        x = (W - total) / 2
        for c, w in zip(line, widths):
            d.text((x, y), c, font=font, fill=fill)
            x += w
        y += line_h
    if shadow:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        alpha = img.split()[3].filter(ImageFilter.GaussianBlur(14))
        sh.putalpha(alpha.point(lambda a: int(a * 0.85)))
        sh.alpha_composite(img)
        return sh
    return img


def glow_sprite(radius, color, hardness=2.2):
    s = radius * 2
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    r = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
    fall = np.exp(-hardness * r ** 2) - np.exp(-hardness)
    fall = np.clip(fall, 0, None) / (1 - np.exp(-hardness))
    return fall[..., None] * color[None, None, :]


def add_glow(buf, sprite, cx, cy, gain):
    s = sprite.shape[0]
    x0, y0 = int(cx - s / 2), int(cy - s / 2)
    x1, y1 = x0 + s, y0 + s
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        return
    buf[y0:y1, x0:x1] += sprite[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)] * gain


def composite(buf, layer_rgba, alpha):
    if alpha <= 0:
        return
    arr = np.asarray(layer_rgba, np.float32)
    a = arr[..., 3:4] / 255.0 * alpha
    buf *= (1 - a)
    buf += arr[..., :3] * a


def noise_field(seed, scale=20):
    rng = np.random.default_rng(seed)
    small = rng.random((H // scale, W // scale)).astype(np.float32)
    img = Image.fromarray((small * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    img = img.filter(ImageFilter.GaussianBlur(40))
    return np.asarray(img, np.float32) / 255.0


YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
_r = np.sqrt(((XX - W / 2) / (W / 2)) ** 2 + ((YY - H / 2) / (H / 2)) ** 2)
VIGNETTE = np.clip(1.12 - 0.5 * _r ** 2, 0.38, 1.0)[..., None]
GRNG = np.random.default_rng(99)


def grain():
    """Half-res film grain upscaled 2x: looks the same on dark footage but
    costs the encoder ~4x less entropy than per-pixel noise."""
    g = GRNG.standard_normal((H // 2, W // 2)).astype(np.float32)
    return np.repeat(np.repeat(g, 2, 0), 2, 1)[..., None]


def grade(buf, warm=0.0, t=0.0):
    """Channel look: desaturate, crush blacks, optional warmth, vignette, grain."""
    luma = (buf @ np.array([0.299, 0.587, 0.114], np.float32))[..., None]
    buf[:] = buf * 0.80 + luma * 0.20
    buf *= 1.07
    buf -= 10.0
    if warm > 0:
        buf *= np.array([1 + 0.06 * warm, 1 + 0.015 * warm, 1 - 0.045 * warm],
                        np.float32)[None, None, :]
    buf *= VIGNETTE
    buf += grain() * 4.0
    np.clip(buf, 0, 255, out=buf)


# --------------------------------------------------------------- footage reader

def beat_frames_footage(beat, n_frames):
    """Yield graded full-res frames for a footage beat with a slow push-in."""
    src = f"assets/footage/{beat['shot']}.mp4"
    off = beat.get("shot_offset", 0)
    dur_need = n_frames / FPS
    # second shot for long beats that specify one
    srcs = [(src, off, dur_need)]
    if beat.get("shot2"):
        half = dur_need / 2
        srcs = [(src, off, half),
                (f"assets/footage/{beat['shot2']}.mp4", 0, dur_need - half)]
    i_global = 0
    for path, ss, want in srcs:
        n_want = int(round(want * FPS))
        reader = imageio_ffmpeg.read_frames(
            path, input_params=["-stream_loop", "-1", "-ss", str(ss)],
            output_params=["-vf",
                           f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                           f"crop={W}:{H},fps={FPS}", "-pix_fmt", "rgb24"])
        meta = next(reader)
        got = 0
        for raw in reader:
            if got >= n_want:
                break
            frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
            # push-in: shrink crop window 100% -> 95.5% across the beat
            p = i_global / max(1, n_frames - 1)
            z = 1.0 - 0.045 * p
            cw, ch = int(W * z) // 2 * 2, int(H * z) // 2 * 2
            x0, y0 = (W - cw) // 2, (H - ch) // 2
            img = Image.fromarray(frame[y0:y0 + ch, x0:x0 + cw])
            img = img.resize((W, H), Image.BILINEAR)
            yield np.asarray(img, np.float32).copy()
            got += 1
            i_global += 1
        reader.close()
        # safety: pad with last frame if the clip came up short
        while got < n_want:
            yield np.asarray(img, np.float32).copy()
            got += 1
            i_global += 1


# --------------------------------------------------------------- MG beats

def mg_title(beat, n):
    fog_a, fog_b = noise_field(1), noise_field(2)
    flash = glow_sprite(900, AMBER * 1.15, hardness=1.2)
    bloom = glow_sprite(420, AMBER, hardness=2.6)
    TITLE = text_layer(["GOD WENT SILENT"], F_TITLE, 124, BONE, 0.46, tracking=10)
    SUB = text_layer(["prayed anyway."], F_HAND, 60, tuple(AMBER.astype(int)), 0.60)
    rng = np.random.default_rng(4)
    ux = np.arange(W * 0.30, W * 0.70, 3, dtype=np.float32)
    uy = H * 0.585 + 4 * np.sin(ux * 0.018) + np.cumsum(rng.standard_normal(len(ux)) * 0.35)
    dur = n / FPS
    for i in range(n):
        t = i / FPS
        buf = np.tile(INK, (H, W, 1)).astype(np.float32)
        fog = np.roll(fog_a, int(t * 22) % W, 1) * 0.6 + np.roll(fog_b, -int(t * 13) % W, 1) * 0.4
        buf += fog[..., None] * (SLATE + LAVENDER * 0.35)[None, None, :] * 0.16
        if t < 0.75:
            add_glow(buf, flash, W * 0.5, H * 0.55, 1.5 * (1 - t / 0.75) ** 2)
        add_glow(buf, bloom, W * 0.5, H * 0.72, 0.18 + 0.05 * math.sin(t * 2.2))
        composite(buf, TITLE, env(t, 0.9, dur - 1.0, fin=1.0))
        composite(buf, SUB, env(t, 2.0, dur - 1.0))
        rev = env(t, 1.6, dur - 1.0, fin=0.01, fout=0.6)
        if rev > 0:
            p = min(1.0, max(0.0, (t - 1.9) / 1.3))
            m = int(len(ux) * p)
            if m > 1:
                ul = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(ul).line(list(zip(ux[:m].tolist(), uy[:m].tolist())),
                                        fill=(*tuple(AMBER.astype(int)), 230), width=4)
                composite(buf, ul, rev)
        yield buf


def mg_texts(beat, n):
    """Unanswered text thread, then '...' that gives up."""
    fog_a = noise_field(3)
    msgs = ["hey", "you up?", "did I do something?"]
    font = ImageFont.truetype(F_HAND, 44)
    small = ImageFont.truetype(F_SERIF, 26)
    bubbles = []
    y = 0.30
    for mtext in msgs:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        tw = d.textlength(mtext, font=font)
        x1 = W * 0.72
        x0 = x1 - tw - 70
        y0 = H * y
        d.rounded_rectangle([x0, y0, x1, y0 + 86], 40, fill=(52, 60, 78, 235))
        d.text((x0 + 35, y0 + 16), mtext, font=font, fill=BONE)
        bubbles.append(img)
        y += 0.115
    delivered = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(delivered).text((W * 0.72 - 110, H * (y - 0.02)), "Delivered",
                                   font=small, fill=(150, 150, 160, 220))
    dur = n / FPS
    dots_xy = (W * 0.30, H * 0.62)
    for i in range(n):
        t = i / FPS
        buf = np.tile(INK, (H, W, 1)).astype(np.float32)
        fog = np.roll(fog_a, int(t * 18) % W, 1)
        buf += fog[..., None] * (SLATE * 0.9)[None, None, :] * 0.14
        for j, bimg in enumerate(bubbles):
            composite(buf, bimg, env(t, 1.0 + j * 2.0, dur - 1.0, fin=0.4, fout=1.0))
        composite(buf, delivered, env(t, 7.4, dur - 1.0, fin=0.5, fout=1.0))
        # typing dots that appear... then give up (the reply that never comes)
        cyc = (t - 9.0) % 6.0
        if t > 9.0 and t < dur - 4 and cyc < 3.2:
            a = env(cyc, 0, 3.2, fin=0.4, fout=0.6)
            dl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dd = ImageDraw.Draw(dl)
            dd.rounded_rectangle([dots_xy[0], dots_xy[1], dots_xy[0] + 150,
                                  dots_xy[1] + 70], 35, fill=(36, 42, 56, 220))
            for k in range(3):
                ph = (math.sin(t * 6 - k * 1.1) + 1) / 2
                dd.ellipse([dots_xy[0] + 30 + k * 36 - 7, dots_xy[1] + 35 - 7 - ph * 6,
                            dots_xy[0] + 30 + k * 36 + 7, dots_xy[1] + 35 + 7 - ph * 6],
                           fill=(170, 170, 180, int(120 + 100 * ph)))
            composite(buf, dl, a)
        yield buf


def mg_gap(beat, n):
    mal = text_layer(["MALACHI"], F_SERIF, 64, BONE, 0.48)
    mat = text_layer(["MATTHEW"], F_SERIF, 64, BONE, 0.48)
    mal = mal.transform(mal.size, Image.AFFINE, (1, 0, W * 0.27, 0, 1, 0))
    mat = mat.transform(mat.size, Image.AFFINE, (1, 0, -W * 0.27, 0, 1, 0))
    dur = n / FPS
    for i in range(n):
        t = i / FPS
        buf = np.tile(INK, (H, W, 1)).astype(np.float32)
        composite(buf, mal, env(t, 0.3, dur - 0.4, fin=0.6))
        composite(buf, mat, env(t, 0.6, dur - 0.4, fin=0.6))
        # the gap, marked by a hand-wobbled amber bracket
        a = env(t, 1.2, dur - 0.4, fin=0.5)
        if a > 0:
            gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(gl)
            xs = np.linspace(W * 0.40, W * 0.60, 40)
            ys = H * 0.58 + 3 * np.sin(xs * 0.05 + t)
            gd.line(list(zip(xs, ys)), fill=(*tuple(AMBER.astype(int)), 220), width=4)
            gd.line([(xs[0], ys[0]), (xs[0], ys[0] - 18)],
                    fill=(*tuple(AMBER.astype(int)), 220), width=4)
            gd.line([(xs[-1], ys[-1]), (xs[-1], ys[-1] - 18)],
                    fill=(*tuple(AMBER.astype(int)), 220), width=4)
            composite(buf, gl, a)
        yield buf


def _figure(d, cx, cy, s, color, bend=0.0):
    """Tiny hand-drawn person: head + bent line body + legs."""
    d.ellipse([cx - s * 0.16, cy - s, cx + s * 0.16, cy - s * 0.68], outline=color, width=3)
    d.line([cx, cy - s * 0.66, cx + bend * s * 0.3, cy - s * 0.2], fill=color, width=3)
    d.line([cx + bend * s * 0.3, cy - s * 0.2, cx - s * 0.14, cy], fill=color, width=3)
    d.line([cx + bend * s * 0.3, cy - s * 0.2, cx + s * 0.2, cy], fill=color, width=3)
    d.line([cx - s * 0.02, cy - s * 0.52, cx - s * 0.22, cy - s * 0.34], fill=color, width=3)


def mg_generations(beat, n):
    """Generations passing a small flame down a hand-drawn amber thread."""
    fog_a = noise_field(6)
    ember = glow_sprite(60, AMBER, hardness=3.0)
    amber = tuple(AMBER.astype(int))
    faint = text_layer(["Elijah is coming."], F_HAND, 46, (*BONE, 120), 0.18)
    dur = n / FPS
    n_fig = 6
    xs = [W * (0.14 + 0.145 * k) for k in range(n_fig)]
    for i in range(n):
        t = i / FPS
        buf = np.tile(INK, (H, W, 1)).astype(np.float32)
        fog = np.roll(fog_a, int(t * 15) % W, 1)
        buf += fog[..., None] * (SLATE + LAVENDER * 0.3)[None, None, :] * 0.15
        composite(buf, faint, env(t, 2.0, dur - 1.0, fin=2.0, fout=2.0) * 0.8)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        step = (dur - 4.0) / n_fig
        flame_x = None
        for k, cx in enumerate(xs):
            born, gone = 1.0 + k * step, 1.0 + (k + 2.2) * step
            a = env(t, born, min(gone, dur - 0.5), fin=0.8, fout=1.2)
            if a <= 0:
                continue
            age = min(1.0, (t - born) / (gone - born + 1e-6))
            col = (*amber, int(200 * a))
            _figure(d, cx, H * 0.70, 130 - 25 * age, col, bend=0.5 * age)
            if t < born + step * 1.3:
                flame_x = cx + 18
        # the thread, written on left to right
        p = min(1.0, t / (dur - 3.0))
        txs = np.linspace(xs[0], xs[0] + (xs[-1] - xs[0]) * p, 60)
        tys = H * 0.73 + 6 * np.sin(txs * 0.01 + 1)
        if p > 0.02:
            d.line(list(zip(txs, tys)), fill=(*amber, 200), width=3)
        composite(buf, lay, 1.0)
        if flame_x is not None:
            add_glow(buf, ember, flame_x, H * 0.70 - 92,
                     0.8 + 0.2 * math.sin(t * 7))
        yield buf


def mg_hold(beat, n):
    ember = glow_sprite(110, AMBER, hardness=3.0)
    rng = np.random.default_rng(2)
    flick = np.convolve(rng.standard_normal(n).astype(np.float32),
                        np.ones(7, np.float32) / 7, "same") * 0.3
    for i in range(n):
        buf = np.tile(INK * 0.55, (H, W, 1)).astype(np.float32)
        add_glow(buf, ember, W * 0.5, H * 0.62, 0.55 * (1 + flick[i]))
        yield buf


def mg_psalm(beat, n):
    verse = text_layer(['"How long, O Lord?', 'Will you forget me forever?"'],
                       F_SERIF_I, 64, BONE, 0.40, spacing=1.5)
    cite = text_layer(["P S A L M   1 3 : 1"], F_SERIF, 30,
                      tuple((AMBER * 0.95).astype(int)), 0.55)
    scrawl = text_layer(["this is in the Bible"], F_HAND, 52,
                        tuple(AMBER.astype(int)), 0.66)
    dur = n / FPS
    fog_a = noise_field(8)
    # write-on mask for the scrawl: reveal left to right
    scr = np.asarray(scrawl, np.float32)
    cols = np.where(scr[..., 3].sum(0) > 0)[0]
    cx0, cx1 = (cols[0], cols[-1]) if len(cols) else (0, W)
    for i in range(n):
        t = i / FPS
        buf = np.tile(INK, (H, W, 1)).astype(np.float32)
        fog = np.roll(fog_a, int(t * 12) % W, 1)
        buf += fog[..., None] * (SLATE * 0.8)[None, None, :] * 0.12
        composite(buf, verse, env(t, 0.8, dur - 0.8, fin=1.2))
        composite(buf, cite, env(t, 1.6, dur - 0.8, fin=1.2))
        a = env(t, 5.0, dur - 0.8, fin=0.01)
        if a > 0:
            p = min(1.0, (t - 5.0) / 1.6)
            m = scr.copy()
            m[:, int(cx0 + (cx1 - cx0) * p):, 3] = 0
            composite(buf, Image.fromarray(m.astype(np.uint8)), a)
        yield buf


def mg_endcard(beat, n):
    verse = text_layer(["The light shines in the darkness,",
                        "and the darkness has not overcome it."],
                       F_SERIF_I, 50, BONE, 0.42, spacing=1.45)
    cite = text_layer(["J O H N   1 : 5"], F_SERIF, 30,
                      tuple((AMBER * 0.95).astype(int)), 0.54)
    mark = text_layer(["prayed anyway."], F_HAND, 64,
                      tuple(AMBER.astype(int)), 0.70)
    ember = glow_sprite(220, AMBER, hardness=2.8)
    dur = n / FPS
    for i in range(n):
        t = i / FPS
        buf = np.tile(INK, (H, W, 1)).astype(np.float32)
        add_glow(buf, ember, W * 0.5, H * 0.88, 0.15)
        composite(buf, verse, env(t, 0.5, dur - 1.2, fin=1.2, fout=1.5))
        composite(buf, cite, env(t, 1.2, dur - 1.2, fin=1.2, fout=1.5))
        composite(buf, mark, env(t, 2.4, dur - 1.0, fin=1.2, fout=1.5))
        if t > dur - 1.2:
            buf *= max(0.0, (dur - t) / 1.2)
        yield buf


MG = {"mg:title": mg_title, "mg:texts": mg_texts, "mg:gap": mg_gap,
      "mg:generations": mg_generations, "mg:hold": mg_hold,
      "mg:psalm": mg_psalm, "mg:endcard": mg_endcard}


# --------------------------------------------------------------- overlays

def overlay_layer(beat):
    kind, lines, _ = beat["overlay"]
    if kind == "caption":
        return text_layer(lines, F_HAND, 60, BONE, 0.76, shadow=True)
    if kind == "bignum":
        return text_layer(lines, F_TITLE, 150, BONE, 0.5, tracking=8, shadow=True)
    raise ValueError(kind)


def overlay_window(beat):
    """(t0, t1) within the beat when the overlay is up."""
    _, _, when = beat["overlay"]
    dur = beat["dur"]
    if when == "tail":
        return max(1.0, dur * 0.45), dur - 0.15
    return dur * 0.25, dur * 0.8


# --------------------------------------------------------------- beat renderer

def render_beat(beat, writer, strike_flash):
    n = int(round(beat["dur"] * FPS))
    warm = 1.0 if beat["section"] in WARM_SECTIONS else 0.0
    if beat["shot"].startswith("mg:"):
        gen = MG[beat["shot"]](beat, n)
        is_mg = True
    else:
        gen = beat_frames_footage(beat, n)
        is_mg = False
    ov = overlay_layer(beat) if beat.get("overlay") else None
    ow = overlay_window(beat) if ov else None
    flash = glow_sprite(900, AMBER * 1.15, hardness=1.2) if strike_flash else None
    bloom = glow_sprite(540, AMBER, hardness=2.4) if strike_flash else None
    for i, buf in enumerate(gen):
        t = i / FPS
        if not is_mg:
            grade(buf, warm=warm, t=t)
        else:
            buf *= VIGNETTE
            buf += grain() * 3.2
            np.clip(buf, 0, 255, out=buf)
        if strike_flash:
            if t < 0.5:
                add_glow(buf, flash, W * 0.5, H * 0.55, 1.4 * (1 - t / 0.5) ** 2)
            add_glow(buf, bloom, W * 0.5, H * 0.6,
                     0.10 * min(1.0, t / 2.0))
            np.clip(buf, 0, 255, out=buf)
        if ov:
            a = env(t, ow[0], ow[1], fin=0.7, fout=0.6)
            if a > 0:
                composite(buf, ov, a)
        # gentle dip to black at the very end of some beats (section seams)
        if beat.get("fade_out"):
            if t > beat["dur"] - 0.5:
                buf *= max(0.0, (beat["dur"] - t) / 0.5)
        if beat.get("fade_in") and t < 0.5:
            buf *= t / 0.5
        writer.send(buf.astype(np.uint8).tobytes())
    return n


def mark_seams(rows):
    prev = None
    for r in rows:
        if prev is not None and r["section"] != prev["section"]:
            prev["fade_out"] = True
            r["fade_in"] = True
        prev = r
    # the strike must hit as a cut-flash, not a fade
    for r in rows:
        if r["id"] == "s1":
            r.pop("fade_in", None)
        if r["id"] == "hold":
            r["fade_out"] = False


def open_writer(path):
    w = imageio_ffmpeg.write_frames(
        path, (W, H), fps=FPS, codec="libx264", macro_block_size=8,
        output_params=["-crf", "22", "-preset", "medium", "-pix_fmt", "yuv420p"])
    w.send(None)
    return w


def main():
    rows, total = compute()
    mark_seams(rows)
    pathlib.Path("output").mkdir(exist_ok=True)

    if "--preview" in sys.argv:
        bid = sys.argv[sys.argv.index("--preview") + 1]
        beat = next(r for r in rows if r["id"] == bid)
        wri = open_writer(f"output/preview-{bid}.mp4")
        render_beat(beat, wri, strike_flash=(bid == "s1"))
        wri.close()
        print(f"preview done: output/preview-{bid}.mp4")
        return

    if "--chunk" in sys.argv:
        ci = int(sys.argv[sys.argv.index("--chunk") + 1])
        nc = int(sys.argv[sys.argv.index("--chunk") + 2])
    else:
        # orchestrate: spawn workers, concat, mux
        nc = min(4, os.cpu_count() or 1)
        procs = [subprocess.Popen([sys.executable, __file__, "--chunk", str(k), str(nc)])
                 for k in range(nc)]
        for p in procs:
            if p.wait() != 0:
                raise SystemExit("worker failed")
        listing = "\n".join(f"file 'seg-{k}.mp4'" for k in range(nc))
        pathlib.Path("output/concat.txt").write_text(listing)
        subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i",
                        "output/concat.txt", "-c", "copy", "output/video.mp4"],
                       check=True, capture_output=True)
        subprocess.run([FF, "-y", "-i", "output/video.mp4", "-i",
                        "assets/audio/episode01.wav", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest",
                        "output/episode01.mp4"], check=True, capture_output=True)
        print(f"EPISODE DONE: output/episode01.mp4 ({total/60:.2f} min)")
        return

    # worker: contiguous beat ranges balanced by frame count
    frames = [int(round(r["dur"] * FPS)) for r in rows]
    targets = np.cumsum(frames) / sum(frames)
    bounds = [0] + [int(np.searchsorted(targets, (k + 1) / nc) + 1) for k in range(nc)]
    bounds[-1] = len(rows)
    lo, hi = bounds[ci], bounds[ci + 1]
    wri = open_writer(f"output/seg-{ci}.mp4")
    done = 0
    for r in rows[lo:hi]:
        done += render_beat(r, wri, strike_flash=(r["id"] == "s1"))
        print(f"[chunk {ci}] {r['id']} done ({done} frames)", flush=True)
    wri.close()


if __name__ == "__main__":
    main()
