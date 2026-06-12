# 06 · API & Environment Setup (Claude Code on the web)

One-time setup so production sessions can generate voiceover (ElevenLabs) and pull
stock footage (Pexels). All settings live in the Claude Code **environment**
(claude.ai/code → Environments), not in this repo. Never commit API keys.

## ElevenLabs (voiceover)

1. elevenlabs.io → profile icon → **API Keys** → Create API Key → copy it.
2. Pick the channel narrator in **Voices** (warm, low, intimate, slightly slow).
   Note the voice name/ID — one voice, forever; it's the face of the channel.
3. Claude Code environment settings → **Environment variables / Secrets**:
   - `ELEVENLABS_API_KEY` = your key
   - `ELEVENLABS_VOICE` = voice name or ID (optional; agent will ask otherwise)
4. Environment **network policy** → allow domain: `api.elevenlabs.io`

## Pexels (stock footage, free)

1. pexels.com/api → Get Started → free account → request API key (instant).
2. Environment variable: `PEXELS_API_KEY` = your key
3. Network policy → allow domains:
   - `api.pexels.com`
   - `videos.pexels.com`
   - `images.pexels.com`

## Notes

- Environment changes generally apply to **new sessions**. After saving, start a
  fresh session on the production branch and tell it the keys are set.
- Quick verification an agent can run:
  - `curl -s -H "xi-api-key: $ELEVENLABS_API_KEY" https://api.elevenlabs.io/v1/user`
  - `curl -s -H "Authorization: $PEXELS_API_KEY" "https://api.pexels.com/videos/search?query=candle&per_page=1"`
- Footage search terms that match the brand vibe live in `docs/04-production-workflow.md`
  (e.g. "rain window night", "fog forest", "candle macro", "silhouette walking").
- YouTube uploads are manual for now: the agent delivers the MP4; you upload it.
