"""Episode 01 audio: VO placement, synthesized score, sound design, mix.

Everything non-VO is synthesized in numpy (per the production decision: no
sound-generation API). Pieces:
  - rain + room tone bed (cold open, fading out as the score enters)
  - felt-piano ambient score, minor pre-strike, resolving major post-strike
  - the match-strike SFX + first major chord at the strike (the brand cue)
  - VO-keyed ducking of the bed, silence hold kept genuinely quiet
Final mix is loudness-normalized to -16 LUFS via ffmpeg loudnorm.

Usage: python3 production/build_audio.py [out.wav]
"""

import json
import os
import pathlib
import subprocess
import sys

import numpy as np
import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(__file__))
from timeline import compute, sections

SR = 48000
FF = imageio_ffmpeg.get_ffmpeg_exe()
rng = np.random.default_rng(11)

# D natural-minor palette pre-strike; F-major-leaning post-strike
CHORDS_MINOR = [["D3", "F3", "A3", "D4"], ["Bb2", "D3", "F3", "Bb3"],
                ["F3", "A3", "C4", "F4"], ["A2", "C3", "E3", "A3"]]
CHORDS_MAJOR = [["F3", "A3", "C4", "F4"], ["C3", "E3", "G3", "C4"],
                ["D3", "F3", "A3", "D4"], ["Bb2", "D3", "F3", "C4"]]

NOTE_BASE = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}


def freq(name):
    base = NOTE_BASE[name[0]]
    if name[1] in "b#":
        base += 1 if name[1] == "#" else -1
        octave = int(name[2:])
    else:
        octave = int(name[1:])
    return 440.0 * 2 ** (base / 12 + octave - 4)


def felt_note(f, dur, vel=1.0):
    """Soft felt-piano-ish note: rolled-off harmonics, slow attack, long decay."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n, np.float32)
    for k in range(1, 7):
        fk = k * f * np.sqrt(1 + 0.0004 * k * k)
        if fk > 9000:
            break
        amp = vel / k ** 2.1 * np.exp(-fk / 2600)
        x += (amp * np.sin(2 * np.pi * fk * t + rng.random() * 6.28)).astype(np.float32)
    att = int(0.04 * SR)
    env = np.minimum(t / (att / SR), 1.0) * np.exp(-t / (0.9 + 140.0 / f))
    return x * env.astype(np.float32)


def pad_chord(freqs, dur, vel=1.0):
    """Slow-breathing detuned sine pad."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n, np.float32)
    for f in freqs:
        for det in (-1.5, 1.5):
            ph = rng.random() * 6.28
            x += np.sin(2 * np.pi * (f + det * f / 800) * t + ph).astype(np.float32)
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t + rng.random() * 6.28)
    edge = np.minimum(np.minimum(t / 4.0, (dur - t) / 4.0), 1.0).clip(0)
    return (x * lfo * edge).astype(np.float32) * (vel / (2 * len(freqs)))


def make_ir(t60=2.8, ms=18):
    n = int(t60 * SR)
    ir = rng.standard_normal((n, 2)).astype(np.float32)
    decay = np.exp(-3 * np.log(10) * np.arange(n) / n)[:, None]
    k = int(ms / 1000 * SR)
    ir[:k] *= np.linspace(0.2, 1, k)[:, None]
    return ir * decay * 0.05


def fft_reverb(x, ir):
    """x mono float32 -> stereo with convolution reverb (overlap-add via FFT)."""
    n = len(x) + len(ir)
    X = np.fft.rfft(x, n)
    out = np.empty((n, 2), np.float32)
    for c in range(2):
        out[:, c] = np.fft.irfft(X * np.fft.rfft(ir[:, c], n), n)
    return out


def lowpass_noise(n, cutoff, seed=0):
    r = np.random.default_rng(seed)
    x = r.standard_normal(n).astype(np.float32)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** 2)
    return np.fft.irfft(X, n).astype(np.float32)


def rain_bed(dur, seed=3):
    """Rain on glass: hiss + sparse droplet ticks, gently moving."""
    n = int(dur * SR)
    hiss = lowpass_noise(n, 1500, seed) * 0.5
    r = np.random.default_rng(seed + 1)
    drops = np.zeros(n, np.float32)
    for _ in range(int(dur * 22)):
        p = r.integers(0, n - 400)
        f0 = 800 + r.random() * 3200
        tt = np.arange(400) / SR
        drops[p:p + 400] += (np.sin(2 * np.pi * f0 * tt) *
                             np.exp(-tt * 900) * (0.1 + r.random() * 0.25))
    sway = 0.7 + 0.3 * np.sin(2 * np.pi * 0.05 * np.arange(n) / SR)
    x = (hiss + drops) * sway
    return x / max(1e-6, np.abs(x).max()) * 0.5


def match_strike():
    """The signature: scratch -> flare whoosh -> tiny crackle."""
    dur = 1.6
    n = int(dur * SR)
    t = np.arange(n) / SR
    r = np.random.default_rng(9)
    noise = r.standard_normal(n).astype(np.float32)
    X = np.fft.rfft(noise)
    f = np.fft.rfftfreq(n, 1 / SR)
    band = np.exp(-((f - 3400) / 1800) ** 2)
    scratch = np.fft.irfft(X * band, n)
    scratch *= np.exp(-((t - 0.07) / 0.05) ** 2) * 1.6
    flare = lowpass_noise(n, 900, 10) * np.exp(-((t - 0.28) / 0.16) ** 2) * 1.1
    crack = np.zeros(n, np.float32)
    for _ in range(26):
        p = int((0.25 + r.random() * 1.1) * SR)
        if p < n - 120:
            tt = np.arange(120) / SR
            crack[p:p + 120] += np.sin(2 * np.pi * (2000 + r.random() * 5000) * tt) \
                * np.exp(-tt * 2500) * 0.22 * r.random()
    thump = np.sin(2 * np.pi * 70 * t) * np.exp(-((t - 0.26) / 0.1) ** 2) * 0.5
    x = scratch + flare + crack + thump
    return x / np.abs(x).max() * 0.9


def decode_vo(path):
    out = subprocess.run(
        [FF, "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
        capture_output=True)
    return np.frombuffer(out.stdout, np.float32)


def add(buf, x, t0, gain=1.0):
    """Add mono or stereo x into stereo buf at time t0."""
    i = int(t0 * SR)
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    seg = x[: max(0, len(buf) - i)]
    buf[i:i + len(seg)] += seg * gain


def compose_score(rows, total, strike_t):
    """Sparse felt-piano arpeggios + pads following the section arc."""
    n = int(total * SR) + SR
    music = np.zeros(n, np.float32)          # mono, reverb applied at the end
    secs = sections(rows)

    def arp(t0, t1, chords, density, vel, oct_up=0.35):
        t = t0
        ci = 0
        r = np.random.default_rng(int(t0 * 7) + 1)
        while t < t1:
            chord = chords[ci % len(chords)]
            for _ in range(r.integers(2, 5)):
                if t >= t1:
                    break
                name = chord[r.integers(0, len(chord))]
                f = freq(name) * (2 if r.random() < oct_up else 1)
                note = felt_note(f, min(6.0, t1 - t + 2), vel * (0.7 + 0.6 * r.random()))
                add_mono(music, note, t)
                t += density * (0.7 + 0.8 * r.random())
            ci += 1

    def add_mono(buf, x, t0):
        i = int(t0 * SR)
        seg = x[: max(0, len(buf) - i)]
        buf[i:i + len(seg)] += seg

    def pads(t0, t1, chords, vel):
        t = t0
        ci = 0
        while t < t1:
            d = min(16.0, t1 - t + 4)
            add_mono(music, pad_chord([freq(x) for x in chords[ci % len(chords)]],
                                      d, vel), t)
            t += d * 0.75
            ci += 1

    # title: the score is born — single low D, then sparse minor motif
    t0, t1 = secs["title"]
    add_mono(music, felt_note(freq("D3"), 8, 1.2), t0 + 1.0)
    add_mono(music, felt_note(freq("A3"), 7, 0.8), t0 + 3.2)
    add_mono(music, felt_note(freq("F3"), 7, 0.9), t0 + 5.4)
    arp(t1 - 2, secs["act1"][1], CHORDS_MINOR, 2.6, 0.55)
    pads(t1, secs["act1"][1], CHORDS_MINOR, 0.10)

    # pivot + act2: thinner and thinner toward the hold
    p0, p1 = secs["pivot"][0], secs["act2"][1]
    hold_start = next(r["start"] for r in rows if r["id"] == "hold")
    arp(p0, hold_start - 6, CHORDS_MINOR, 3.4, 0.45)
    pads(p0, hold_start - 8, CHORDS_MINOR, 0.07)
    # b9 into the hold: one lone repeated A3, heartbeat-slow, then nothing
    b9 = next(r for r in rows if r["id"] == "b9")
    for k in range(3):
        add_mono(music, felt_note(freq("A3"), 5, 0.5 - 0.12 * k),
                 b9["start"] + 2 + k * 4.0)

    # strike: first major chord, then the warm bed
    s0, s_end = secs["strike"]
    chord = [freq(x) for x in ["F2", "F3", "A3", "C4", "F4"]]
    for j, f in enumerate(chord):
        add_mono(music, felt_note(f, 10, 1.5 - j * 0.15), strike_t + 0.12 + j * 0.06)
    pads(s0 + 2, secs["act3"][1], CHORDS_MAJOR, 0.13)
    arp(s0 + 6, secs["act3"][1], CHORDS_MAJOR, 2.4, 0.6, oct_up=0.5)

    # end: resolve home and decay
    e0, e1 = secs["end"]
    arp(e0, e1 - 10, CHORDS_MAJOR, 3.0, 0.5)
    pads(e0, e1 - 4, CHORDS_MAJOR[:1], 0.10)
    for j, f in enumerate([freq(x) for x in ["F2", "C3", "F3", "A3"]]):
        add_mono(music, felt_note(f, 12, 0.9), e1 - 11 + j * 0.08)

    return music[:int(total * SR)]


def main(out_path="assets/audio/episode01.wav"):
    pathlib.Path("assets/audio").mkdir(parents=True, exist_ok=True)
    rows, total = compute()
    strike_row = next(r for r in rows if r["id"] == "s1")
    strike_t = strike_row["start"]
    n = int(total * SR)
    mix = np.zeros((n, 2), np.float32)

    # --- VO ---------------------------------------------------------------
    vo_track = np.zeros(n, np.float32)
    for r in rows:
        if not r["vo"]:
            continue
        x = decode_vo(f"assets/vo/{r['id']}.mp3")
        i = int(r["vo_start"] * SR)
        vo_track[i:i + len(x)] += x[: max(0, n - i)]
    peak = np.abs(vo_track).max()
    vo_track *= 0.72 / peak
    # a whisper of room on the voice
    vo_st = np.stack([vo_track, vo_track], 1)
    vo_st += fft_reverb(vo_track, make_ir(0.6))[:n] * 0.10
    mix += vo_st

    # --- score ---------------------------------------------------------------
    music = compose_score(rows, total, strike_t)
    music_st = fft_reverb(music, make_ir(3.2))[:n]
    music_st += np.stack([music, music], 1) * 0.5
    # duck under speech
    env = np.abs(vo_track)
    k = int(0.25 * SR)
    env = np.convolve(env, np.ones(k, np.float32) / k, "same")
    duck = 1.0 / (1.0 + 9.0 * env / max(1e-6, env.max()))
    # silence hold: pull the bed to near zero
    hold = next(r for r in rows if r["id"] == "hold")
    h0, h1 = int(hold["start"] * SR), int((hold["start"] + hold["dur"]) * SR)
    fade = int(1.5 * SR)
    duck[h0:h1] *= 0.06
    duck[h0 - fade:h0] *= np.linspace(1, 0.06, fade)
    mpk = float(np.percentile(np.abs(music_st), 99.5))
    mix += music_st * (0.42 / max(1e-6, mpk)) * duck[:, None]

    # --- rain + room tone -------------------------------------------------------
    open_end = sections(rows)["title"][0]
    rain = rain_bed(open_end + 14)
    fade_out = np.ones(len(rain), np.float32)
    fo = int(10 * SR)
    fade_out[-fo:] = np.linspace(1, 0, fo)
    add(mix, rain * fade_out, 0, 0.16)
    room = lowpass_noise(n, 110, seed=5) * 0.012
    mix += np.stack([room, room], 1)

    # --- the strike SFX -----------------------------------------------------------
    add(mix, match_strike(), strike_t - 0.05, 0.5)
    # faint second strike under the title card for brand continuity
    title = next(r for r in rows if r["id"] == "title")
    add(mix, match_strike(), title["start"] + 0.3, 0.22)

    # --- final fade, soft limit, write ---------------------------------------------
    tail = int(3.0 * SR)
    mix[-tail:] *= np.linspace(1, 0, tail)[:, None]
    mix = np.tanh(mix * 1.1) * 0.95

    raw = pathlib.Path(out_path).with_suffix(".raw.wav")
    import wave
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    subprocess.run([FF, "-y", "-i", str(raw), "-af",
                    "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR),
                    out_path], capture_output=True, check=True)
    raw.unlink()
    print(f"audio done: {out_path} ({total/60:.2f} min)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "assets/audio/episode01.wav")
