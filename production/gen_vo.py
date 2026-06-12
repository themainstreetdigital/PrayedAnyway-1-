"""Generate episode VO with ElevenLabs (voice: Joseff Sweet).

Per-beat MP3s land in assets/vo/<beat-id>.mp3 with previous/next text passed
for prosody continuity. Durations measured via ffmpeg and saved to
assets/vo/durations.json. Re-runs skip beats that already have audio.

Usage: python3 production/gen_vo.py
Requires: ELEVENLABS_API_KEY with text_to_speech + voices_read.
"""

import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(__file__))
from episode01_beats import BEATS, TTS_MODEL, VOICE_SETTINGS

API = "https://api.elevenlabs.io/v1"
KEY = os.environ["ELEVENLABS_API_KEY"]
OUT = pathlib.Path("assets/vo")
OUT.mkdir(parents=True, exist_ok=True)
VOICE_NAME = "joseff sweet"


def req(url, data=None, retries=4):
    for i in range(retries):
        try:
            r = urllib.request.Request(
                url, data=json.dumps(data).encode() if data else None,
                headers={"xi-api-key": KEY, "Content-Type": "application/json",
                         "User-Agent": "prayed-anyway-production/1.0"})
            with urllib.request.urlopen(r, timeout=120) as resp:
                return resp.read()
        except Exception as e:
            body = e.read().decode()[:300] if hasattr(e, "read") else str(e)
            if i == retries - 1:
                raise RuntimeError(f"{url}: {body}")
            time.sleep(2 ** (i + 1))


def find_voice():
    voices = json.loads(req(f"{API}/voices?show_legacy=true"))["voices"]
    for v in voices:
        if v["name"].strip().lower() == VOICE_NAME:
            return v["voice_id"], v["name"]
    names = ", ".join(v["name"] for v in voices)
    raise SystemExit(f'Voice "Joseff Sweet" not in My Voices. Available: {names}')


def mp3_duration(path):
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = subprocess.run([ff, "-i", str(path), "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "time=" in line:
            t = line.rsplit("time=", 1)[1].split(" ")[0]
            h, m, s = t.split(":")
            dur = int(h) * 3600 + int(m) * 60 + float(s)
    return dur


def main():
    vid, vname = find_voice()
    print(f"voice: {vname} ({vid})")
    spoken = [b for b in BEATS if b["vo"]]
    durs = {}
    if (OUT / "durations.json").exists():
        durs = json.loads((OUT / "durations.json").read_text())
    for i, b in enumerate(spoken):
        dest = OUT / f"{b['id']}.mp3"
        if dest.exists() and b["id"] in durs:
            print(f"skip {b['id']}")
            continue
        payload = {
            "text": b["vo"],
            "model_id": TTS_MODEL,
            "voice_settings": VOICE_SETTINGS,
            "previous_text": spoken[i - 1]["vo"] if i else None,
            "next_text": spoken[i + 1]["vo"] if i + 1 < len(spoken) else None,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        audio = req(f"{API}/text-to-speech/{vid}?output_format=mp3_44100_128",
                    payload)
        dest.write_bytes(audio)
        durs[b["id"]] = round(mp3_duration(dest), 3)
        print(f"{b['id']}: {durs[b['id']]}s  ({len(b['vo'].split())} words)")
        (OUT / "durations.json").write_text(json.dumps(durs, indent=2))
    total = sum(durs.values())
    print(f"done — {len(durs)} segments, {total/60:.1f} min of speech")


if __name__ == "__main__":
    main()
