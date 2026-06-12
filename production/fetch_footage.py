"""Prayed Anyway — episode footage fetcher (Pexels).

Searches Pexels per shot cue, scores candidates (resolution, duration, and
darkness measured from the preview thumbnail — the brand is dark/moody),
downloads the best file per shot to assets/footage/, and writes a manifest
with attribution.

Usage: python3 production/fetch_footage.py
Requires: PEXELS_API_KEY
"""

import io
import json
import os
import pathlib
import time
import urllib.request

from PIL import Image

API = "https://api.pexels.com/videos/search"
KEY = os.environ["PEXELS_API_KEY"]
OUT = pathlib.Path("assets/footage")
OUT.mkdir(parents=True, exist_ok=True)

# shot key -> (search query, want_dark)
SHOTS = {
    "rain_window": ("rain on window night", True),
    "phone_bed": ("person lying in bed at night phone", True),
    "city_rain_night": ("city rain night bokeh", True),
    "church_silhouette": ("church worship silhouette hands raised", True),
    "empty_chair": ("empty chair dark room", True),
    "man_alone_window": ("man sitting alone dark window", True),
    "fog_forest": ("fog forest dark", True),
    "page_turn": ("turning pages old book close up", False),
    "ruins_clouds": ("ancient ruins clouds", False),
    "candle_burn": ("candle burning dark", True),
    "oil_lamp": ("oil lamp flame dark", True),
    "old_man_silhouette": ("old man silhouette dark", True),
    "temple_columns": ("ancient temple columns", False),
    "incense_smoke": ("smoke incense dark", True),
    "candle_macro": ("candle flame macro dark", True),
    "light_match": ("hands lighting match candle dark", True),
    "kettle_morning": ("kettle steam morning kitchen", False),
    "notebook_writing": ("hand writing notebook morning light", False),
    "dawn_blinds": ("morning sunlight through window blinds", False),
    "door_ajar": ("door ajar warm light dark", True),
    "walk_fog": ("silhouette person walking fog", True),
    "night_sky": ("night sky stars timelapse", True),
    "hands_open": ("open hands palms dark", True),
    "lamp_dark_room": ("lamp glowing dark room cozy", True),
}


def get(url, headers=None, retries=4):
    for i in range(retries):
        try:
            h = {"User-Agent": "prayed-anyway-production/1.0"}
            h.update(headers or {})
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(2 ** (i + 1))


def thumb_luma(url):
    try:
        data = get(url.split("?")[0] + "?auto=compress&w=120")
        img = Image.open(io.BytesIO(data)).convert("L").resize((32, 18))
        px = list(img.getdata())
        return sum(px) / len(px) / 255.0
    except Exception:
        return 0.5


def best_file(video):
    """Pick the best mp4 file: closest to 1920x1080 without exceeding it."""
    cands = [f for f in video["video_files"] if f.get("file_type") == "video/mp4"
             and f.get("width") and f.get("height") and f["width"] >= f["height"]]
    if not cands:
        return None
    le = [f for f in cands if f["height"] <= 1080]
    pool = le or cands
    return max(pool, key=lambda f: f["height"])


def score(video, want_dark):
    f = best_file(video)
    if f is None:
        return -1, None
    s = 0.0
    s += min(video.get("duration", 0), 30) / 30 * 2.0          # length up to 30s
    s += 1.0 if f["height"] >= 1080 else f["height"] / 1080.0   # resolution
    if abs(f["width"] / f["height"] - 16 / 9) > 0.05:
        s -= 0.7
    luma = thumb_luma(video["image"])
    s += (1 - luma) * 2.5 if want_dark else (1 - abs(luma - 0.45)) * 1.5
    return s, f


def main():
    manifest = {}
    for key, (query, want_dark) in SHOTS.items():
        dest = OUT / f"{key}.mp4"
        if dest.exists() and dest.stat().st_size > 0:
            print(f"skip {key} (exists)")
            continue
        q = urllib.parse.quote(query)
        data = json.loads(get(f"{API}?query={q}&per_page=12&orientation=landscape",
                              {"Authorization": KEY}))
        scored = []
        for v in data.get("videos", []):
            if v.get("duration", 0) < 7:
                continue
            s, f = score(v, want_dark)
            if f:
                scored.append((s, v, f))
        if not scored:
            print(f"!! no results for {key}: {query}")
            continue
        scored.sort(key=lambda x: -x[0])
        s, v, f = scored[0]
        print(f"{key}: #{v['id']} {f['width']}x{f['height']} {v['duration']}s "
              f"score={s:.2f} by {v['user']['name']}")
        dest.write_bytes(get(f["link"]))
        manifest[key] = {"pexels_id": v["id"], "url": v["url"],
                         "duration": v["duration"], "width": f["width"],
                         "height": f["height"], "by": v["user"]["name"],
                         "query": query}
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print("done:", len(manifest), "downloaded")


if __name__ == "__main__":
    import urllib.parse
    main()
