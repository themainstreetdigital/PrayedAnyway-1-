# Episode 01 — Upload Kit

Deliverable: `output/episode01.mp4` (1920×1080, 24fps, 6:34, −16 LUFS).
The strike hits at 4:00 — 61% of runtime, inside the brand's 55–70% window.
Clean visual cut: **no on-screen text, no captions** — add any titles/cards in
your editor or rely on YouTube captions.

## Title (≤60 chars)

> God went silent for 400 years. Here's what that means at 1am.

## Description

You've prayed into the dark and gotten ceiling. The Bible has a page for that —
it's the blank one between Malachi and Matthew, and it took four hundred years
to turn. Here's why the silence was never absence.

Passages: Malachi 4:5–6 · Psalm 13:1–6 · Luke 1:5–17 · Luke 2:25–32

What's the prayer you've stopped saying out loud — but haven't actually
stopped praying? Tell me below. I read them.

Narration is AI-generated (ElevenLabs). Footage from Pexels — full credits in
`assets/footage/manifest.json`.

## Chapters

0:00 1:43am · cold open
0:36 the title strike
0:47 silence gets interpreted
1:48 one page = 400 years
2:02 the story, told darkly
4:00 your prayer has been heard
4:23 what this means at 1am
5:41 pray it once more

## Thumbnail (make in Photopea)

Ink Night `#0E1116` background · one amber subject (the struck match frame —
grab from ~4:01) · handwritten: **"400 years of nothing"**

## Voice note

This cut is narrated by stock "George" because the API key couldn't look up
"Joseff Sweet". To re-voice: set `ELEVENLABS_VOICE_ID` to the Joseff Sweet ID,
`rm -rf assets/vo`, then re-run `gen_vo.py`, `build_audio.py`,
`render_episode.py`.
