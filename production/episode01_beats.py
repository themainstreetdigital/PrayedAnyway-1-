"""Episode 01 — "God Went Silent" — beat sheet as data.

Each beat: VO text (None for silent/visual-only beats), the visual that plays
under it (a footage key from assets/footage/ or an mg: generated motion-graphics
segment), pre/post gaps (seconds of breathing room around the VO), and an
optional on-screen text overlay.

Overlay kinds: caption (handwritten, centered), bignum (display serif),
scripture (serif italic + small-caps cite handled by the renderer).
The renderer decides exact in/out within the beat.
"""

BEATS = [
    # ---- COLD OPEN — rain + room tone only, no music --------------------------
    dict(id="c1", section="open",
         vo="It's 1:43 in the morning, and you're praying into the dark again — and if you're honest, it's starting to feel like leaving voicemails for someone who changed their number.",
         shot="phone_bed", pre=2.5, post=1.0),
    dict(id="c2", section="open",
         vo="You've heard people say God spoke to them. He told them which job to take. Which city. Which person.",
         shot="rain_window", pre=0.4, post=0.8),
    dict(id="c3", section="open",
         vo="You've gotten... ceiling.",
         shot="phone_dark", pre=0.3, post=1.4),
    dict(id="c4", section="open",
         vo="And somewhere under the tiredness there's a quieter question you don't say out loud, because saying it out loud makes it real: what if the silence means He left?",
         shot="rain_window", pre=0.4, post=1.8,
         overlay=("caption", ["what if the silence", "means He left?"], "tail")),

    # ---- TITLE STRIKE-IN — generated -----------------------------------------
    dict(id="title", section="title", vo=None, shot="mg:title", dur=11.0),

    # ---- ACT 1 — SIT IN IT ----------------------------------------------------
    dict(id="a1", section="act1",
         vo="Here's what nobody tells you about silence: it's not neutral. Silence gets interpreted. A friend doesn't text back, and within three hours you've written an entire story about what you did wrong. Now run that same software on the Creator of the universe, and watch what it builds: He's disappointed in me. I asked wrong. I'm not one of the ones He talks to.",
         shot="mg:texts", pre=0.8, post=0.8),
    dict(id="a2", section="act1",
         vo='And the church doesn\'t always help. Everyone around you seems to have a direct line. "God told me." "I just felt led." Meanwhile you\'re sitting in the same room, wondering if your receiver is broken.',
         shot="church_silhouette", pre=0.3, post=0.8),
    dict(id="a3", section="act1",
         vo="So you do the math most people do in the dark: silence equals absence. No answer means no one's there.",
         shot="man_alone_window", pre=0.3, post=1.0,
         overlay=("caption", ["silence = absence"], "tail")),
    dict(id="a4", section="act1",
         vo="I want to show you why that math is wrong. And I want to show you using the part of the Bible nobody preaches on — because it isn't a verse.",
         shot="fog_forest", pre=0.4, post=0.6),
    dict(id="a5", section="act1",
         vo="It's a gap.",
         shot="mg:gap", pre=0.4, post=1.6),

    # ---- PIVOT ----------------------------------------------------------------
    dict(id="p1", section="pivot",
         vo="Open a Bible to the last page of the Old Testament. Malachi. Now turn one page — to Matthew.",
         shot="page_turn", pre=0.5, post=1.0),
    dict(id="p2", section="pivot",
         vo="That page-turn took four hundred years.",
         shot="page_turn", shot_offset=10, pre=0.3, post=2.2,
         overlay=("bignum", ["400 YEARS"], "tail")),

    # ---- ACT 2 — THE STORY, TOLD DARKLY ---------------------------------------
    dict(id="b1", section="act2",
         vo="The Old Testament ends with a promise. Malachi, the last prophet, says: Elijah is coming. Hearts will turn. Get ready.",
         shot="temple_columns", pre=0.6, post=0.8),
    dict(id="b2", section="act2",
         vo="And then — nothing.",
         shot="night_sky", pre=0.4, post=1.6),
    dict(id="b3", section="act2",
         vo="No prophet. No vision. No voice. Not for a year. Not for a decade. For four. hundred. years. Generations are born, grow old, and die inside that silence. They bury parents and children inside it. Empires roll over them — Persia, then Greece, then Rome — and heaven says nothing.",
         shot="ruins_clouds", pre=0.3, post=1.0),
    dict(id="b4", section="act2",
         vo="Think about what that does to a people. Grandmothers teaching grandchildren the old promise — Elijah is coming — while privately wondering if they're passing down a memory, or a fantasy. Whole lifetimes of prayers that end in ceiling.",
         shot="mg:generations", pre=0.4, post=0.8),
    dict(id="b5", section="act2",
         vo="You think your silence is long.",
         shot="empty_chair", pre=0.4, post=1.8),
    dict(id="b6", section="act2",
         vo="And here's the strange part — the part that should not have happened: they kept praying. Not all of them. But enough. In the dark, with zero evidence, somebody kept lighting the lamps. Somebody kept teaching the promise. An old man named Simeon kept showing up at the temple, because of a whisper he'd staked his whole life on — that he wouldn't die before he saw the answer.",
         shot="oil_lamp", pre=0.5, post=0.8),
    dict(id="b7", section="act2",
         vo="Four hundred years of nothing... and they prayed anyway.",
         shot="lamp_dark_room", pre=0.4, post=1.6,
         overlay=("caption", ["prayed anyway."], "tail")),
    dict(id="b8", section="act2",
         vo="Then one ordinary afternoon, an old priest named Zechariah draws temple duty. He goes in to burn the incense — a once-in-a-lifetime assignment — and standing next to the altar... is an angel.",
         shot="incense_smoke", pre=0.5, post=1.0),
    dict(id="b9", section="act2",
         vo='The first words out of heaven in four centuries — the very first words — are these: "Do not be afraid, Zechariah... for your prayer has been heard."',
         shot="candle_macro", pre=0.4, post=0.0),
    dict(id="hold", section="act2", vo=None, shot="mg:hold", dur=4.5),

    # ---- THE STRIKE ------------------------------------------------------------
    dict(id="s1", section="strike",
         vo="Your prayer has been heard.",
         shot="light_match", shot_offset=4.5, pre=1.2, post=1.0),
    dict(id="s2", section="strike",
         vo='Not "your prayer has finally been noticed." Heard. Past tense. The whole time. Every unanswered prayer of those four hundred years had been landing.',
         shot="candle_macro", shot_offset=20, pre=0.3, post=1.0),
    dict(id="s3", section="strike",
         vo="Silence isn't absence. Sometimes it's the held breath before the answer.",
         shot="page_turn", pre=0.5, post=2.0,
         overlay=("caption", ["silence isn't absence."], "tail")),

    # ---- ACT 3 — WHAT THIS MEANS AT 1AM ----------------------------------------
    dict(id="d1", section="act3",
         vo="So what do you do with that, tonight, in your own gap between Malachi and Matthew?",
         shot="walk_fog", pre=0.6, post=0.8),
    dict(id="d2", section="act3",
         vo="First: stop grading God's presence by God's volume. The four hundred years weren't empty — they were assembling the world the answer needed. Roads. A common language. A people leaning forward. Some of what looks like delay... is staging.",
         shot="temple_columns", shot_offset=20, pre=0.4, post=1.0),
    dict(id="d3", section="act3",
         vo='Second: notice that the Bible never shames the people who got tired in the silence. Psalm 13 is in the Bible — "How long, O Lord? Will you forget me forever?" — that\'s scripture. Which means the angry, exhausted, doubting prayer counts as prayer. The door stays open for people who knock with less and less hope. David wrote the complaint into the hymnbook.',
         shot="mg:psalm", pre=0.5, post=1.0),
    dict(id="d4", section="act3",
         vo="Third — and this is the one I can't get over — the silence broke in the middle of somebody's ordinary routine. Zechariah wasn't doing anything spectacular. He was doing his shift. Simeon was doing another regular day at the temple. The answer came to people who kept showing up to the ordinary thing.",
         shot="kettle_morning", shot2="notebook_writing", pre=0.4, post=0.8),
    dict(id="d5", section="act3",
         vo="Maybe faithfulness in the silence isn't feeling something. Maybe it's just... showing up to your shift.",
         shot="dawn_blinds", pre=0.4, post=1.6,
         overlay=("caption", ["showing up to your shift."], "tail")),

    # ---- OPEN HAND ---------------------------------------------------------------
    dict(id="e1", section="end",
         vo="So here's the small thing I'd put in your hands tonight.",
         shot="light_match", shot_offset=14, pre=0.6, post=0.8),
    dict(id="e2", section="end",
         vo="That prayer you've stopped saying out loud — pray it once more. Not because the silence broke. Before it breaks. That's what the four hundred years were full of: people praying anyway. It's kind of the whole reason this channel has its name.",
         shot="candle_burn", pre=0.3, post=1.0),
    dict(id="e3", section="end",
         vo="And if you want — tell me in the comments: what's the prayer you've stopped saying out loud, but haven't actually stopped praying? I read them. So do a few thousand people who feel exactly like you do, at 1:43 in the morning.",
         shot="hands_phone_warm", shot_offset=6, pre=0.4, post=0.8,
         overlay=("caption", ["the prayer you've stopped", "saying out loud —"], "mid")),
    dict(id="e4", section="end",
         vo="The light shines in the darkness. The darkness has not overcome it.",
         shot="door_ajar", pre=0.6, post=1.0),
    dict(id="e5", section="end",
         vo="Goodnight.",
         shot="door_ajar", shot_offset=8, pre=0.2, post=1.5),
    dict(id="endcard", section="end", vo=None, shot="mg:endcard", dur=9.0),
]

# Sections where the post-strike warm grade applies
WARM_SECTIONS = {"strike", "act3", "end"}

# TTS settings (docs/06-api-setup.md)
TTS_MODEL = "eleven_multilingual_v2"
VOICE_SETTINGS = {"stability": 0.55, "similarity_boost": 0.75,
                  "style": 0.2, "speed": 0.93}
