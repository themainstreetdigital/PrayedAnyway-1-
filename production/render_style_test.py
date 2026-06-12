"""Prayed Anyway — style test renderer.

Renders a ~34s typographic motion-graphics test of the episode 01 cold open:
ink-night base, drifting fog, floating dust, candle ember, the match-strike
turn, title card with hand-drawn underline, scripture end card. No audio.

Usage: python3 production/render_style_test.py [out.mp4]
"""

import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

W, H, FPS = 1920, 1080, 24
DUR = 34.0
N_FRAMES = int(DUR * FPS)

# Palette (docs/01-brand-identity.md)
INK = np.array([14, 17, 22], np.float32)
SLATE = np.array([42, 49, 64], np.float32)
LAVENDER = np.array([110, 94, 140], np.float32)
AMBER = np.array([224, 164, 88], np.float32)
BONE = (232, 225, 213)

FONT_DIR = "/mnt/skills/examples/canvas-design/canvas-fonts"
F_HAND = f"{FONT_DIR}/NothingYouCouldDo-Regular.ttf"   # whimsy / narration captions
F_TITLE = f"{FONT_DIR}/Gloock-Regular.ttf"             # display serif titles
F_SERIF_I = f"{FONT_DIR}/CrimsonPro-Italic.ttf"        # scripture
F_SERIF = f"{FONT_DIR}/CrimsonPro-Regular.ttf"         # small-caps citations

STRIKE_T = 18.5  # the turn


def env(t, t0, t1, fin=0.8, fout=0.8):
    """Trapezoid opacity envelope between t0 and t1."""
    if t < t0 or t > t1:
        return 0.0
    return min(1.0, (t - t0) / fin, (t1 - t) / fout)


def text_layer(lines, font_path, size, fill, y_frac, spacing=1.5, tracking=0.0):
    """Render centered text (one or more lines) onto a full-canvas RGBA layer."""
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
    return img


def glow_sprite(radius, color, hardness=2.2):
    """Soft radial glow as a float32 HxWx3 contribution, centered in its own box."""
    s = radius * 2
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    r = np.sqrt((xx - radius) ** 2 + (yy - radius) ** 2) / radius
    fall = np.exp(-hardness * r ** 2)
    return fall[..., None] * color[None, None, :]


def add_glow(buf, sprite, cx, cy, gain):
    """Additively blend a glow sprite into the frame buffer at (cx, cy)."""
    s = sprite.shape[0]
    x0, y0 = int(cx - s / 2), int(cy - s / 2)
    x1, y1 = x0 + s, y0 + s
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 <= x0 or y1 <= y0:
        return
    buf[y0:y1, x0:x1] += sprite[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)] * gain


def noise_field(seed, scale=20):
    """Large soft noise field for fog, tileable enough for np.roll drift."""
    rng = np.random.default_rng(seed)
    small = rng.random((H // scale, W // scale)).astype(np.float32)
    img = Image.fromarray((small * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    img = img.filter(ImageFilter.GaussianBlur(40))
    return np.asarray(img, np.float32) / 255.0


def composite(buf, layer_rgba, alpha):
    """Alpha-composite a PIL RGBA layer over the float frame buffer."""
    if alpha <= 0:
        return
    arr = np.asarray(layer_rgba, np.float32)
    a = arr[..., 3:4] / 255.0 * alpha
    buf *= (1 - a)
    buf += arr[..., :3] * a


def main(out_path):
    rng = np.random.default_rng(7)

    # --- precomputed elements -------------------------------------------------
    fog_a, fog_b = noise_field(1), noise_field(2)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vignette = np.clip(1.15 - 0.55 * r ** 2, 0.35, 1.0)[..., None]

    ember = glow_sprite(170, AMBER, hardness=3.0)
    bloom = glow_sprite(540, AMBER, hardness=2.4)
    flash = glow_sprite(900, AMBER * 1.15, hardness=1.2)

    # smoothed candle flicker track
    flick = rng.standard_normal(N_FRAMES).astype(np.float32)
    kernel = np.ones(7, np.float32) / 7
    flick = np.convolve(flick, kernel, "same") * 0.35

    # floating dust
    n_dust = 70
    dust = {
        "x": rng.random(n_dust) * W,
        "y": rng.random(n_dust) * H,
        "vy": 8 + rng.random(n_dust) * 18,       # px/s upward
        "vx": rng.standard_normal(n_dust) * 6,
        "s": 1.0 + rng.random(n_dust) * 2.2,
        "ph": rng.random(n_dust) * 6.28,
    }

    # --- text layers ------------------------------------------------------------
    L1 = text_layer(["It's 1:43 in the morning."], F_HAND, 66, BONE, 0.5)
    L2 = text_layer(["and you're praying into", "the dark again."], F_HAND, 66, BONE, 0.5)
    L3 = text_layer(["what if the silence", "means He left?"], F_HAND, 56,
                    (*BONE, 200), 0.5)
    TITLE = text_layer(["GOD WENT SILENT"], F_TITLE, 124, BONE, 0.46, tracking=10)
    SUB = text_layer(["prayed anyway."], F_HAND, 60,
                     tuple(AMBER.astype(int)), 0.60)
    VERSE = text_layer(["The light shines in the darkness,",
                        "and the darkness has not overcome it."],
                       F_SERIF_I, 50, BONE, 0.47, spacing=1.45)
    CITE = text_layer(["J O H N   1 : 5"], F_SERIF, 30,
                      tuple((AMBER * 0.95).astype(int)), 0.60)

    # hand-drawn wavy underline for the title (write-on reveal)
    ux = np.arange(W * 0.30, W * 0.70, 3, dtype=np.float32)
    uy = H * 0.545 + 4 * np.sin(ux * 0.018) + np.cumsum(rng.standard_normal(len(ux)) * 0.35)

    writer = imageio_ffmpeg.write_frames(
        out_path, (W, H), fps=FPS, codec="libx264", macro_block_size=8,
        output_params=["-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p"],
    )
    writer.send(None)

    for i in range(N_FRAMES):
        t = i / FPS
        post = t >= STRIKE_T
        warm = min(1.0, (t - STRIKE_T) / 2.5) if post else 0.0

        # base + fog
        buf = np.tile(INK, (H, W, 1)).astype(np.float32)
        oa, ob = int(t * 22) % W, int(t * 13) % W
        fog = np.roll(fog_a, oa, axis=1) * 0.6 + np.roll(fog_b, -ob, axis=1) * 0.4
        fog_tint = SLATE * (1 - warm * 0.4) + LAVENDER * 0.35 + AMBER * warm * 0.45
        buf += fog[..., None] * fog_tint[None, None, :] * 0.16

        # candle ember (pre-strike) and the growing bloom (post-strike)
        fl = 1.0 + flick[i]
        if not post:
            add_glow(buf, ember, W * 0.62 + np.sin(t * 1.7) * 4, H * 0.78,
                     0.40 * fl * min(1.0, t / 2.0))
        else:
            grow = min(1.0, (t - STRIKE_T) / 4.0)
            add_glow(buf, bloom, W * 0.5, H * 0.66, (0.30 + 0.45 * grow) * fl)
            ft = t - STRIKE_T          # the strike flash, decaying fast
            if ft < 0.45:
                add_glow(buf, flash, W * 0.5, H * 0.6, 1.6 * (1 - ft / 0.45) ** 2)

        # dust motes (brighter and warmer after the strike)
        dl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dd = ImageDraw.Draw(dl)
        dc = tuple((BONE if not post else tuple(AMBER.astype(int))))
        for k in range(n_dust):
            dx = (dust["x"][k] + dust["vx"][k] * t + 14 * np.sin(t * 0.6 + dust["ph"][k])) % W
            dy = (dust["y"][k] - dust["vy"][k] * t) % H
            a = int(60 + 50 * np.sin(t * 1.3 + dust["ph"][k]) ** 2) + (30 if post else 0)
            s = dust["s"][k]
            dd.ellipse([dx - s, dy - s, dx + s, dy + s], fill=(*dc, a))
        composite(buf, dl, 0.8)

        # narration captions → title → verse
        composite(buf, L1, env(t, 2.0, 7.5))
        composite(buf, L2, env(t, 8.0, 13.0))
        composite(buf, L3, env(t, 13.5, 17.2, fout=0.5))
        composite(buf, TITLE, env(t, 19.2, 26.0))
        composite(buf, SUB, env(t, 20.4, 26.0))
        composite(buf, VERSE, env(t, 26.8, 33.2, fin=1.2, fout=1.0))
        composite(buf, CITE, env(t, 27.6, 33.2, fin=1.2, fout=1.0))

        # title underline write-on
        rev = env(t, 19.2, 26.0, fin=0.01, fout=0.6)
        if rev > 0:
            p = min(1.0, max(0.0, (t - 19.8) / 1.4))
            n = int(len(ux) * p)
            if n > 1:
                ul = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ud = ImageDraw.Draw(ul)
                pts = list(zip(ux[:n].tolist(), uy[:n].tolist()))
                ud.line(pts, fill=(*tuple(AMBER.astype(int)), 230), width=4)
                composite(buf, ul, rev)

        # grade: vignette, post-strike warmth, grain, final fade
        buf *= vignette
        if warm:
            buf *= np.array([1 + 0.05 * warm, 1 + 0.015 * warm, 1 - 0.03 * warm],
                            np.float32)[None, None, :]
        buf += rng.standard_normal((H, W, 1)).astype(np.float32) * 5.5
        if t > DUR - 1.0:
            buf *= max(0.0, DUR - t)

        writer.send(np.clip(buf, 0, 255).astype(np.uint8).tobytes())
        if i % 120 == 0:
            print(f"frame {i}/{N_FRAMES}", flush=True)

    writer.close()
    print("done:", out_path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "output/style-test.mp4")
