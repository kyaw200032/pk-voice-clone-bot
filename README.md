# PK Voice Clone — Telegram Bot

Send Burmese text, get it back as a voice message in a cloned voice.
Powered by [VoxCPM2](https://github.com/OpenBMB/VoxCPM) (Apache-2.0, Burmese supported).

## How it works

- User sends Burmese text → bot calls the VoxCPM2 Gradio API → returns MP3 audio.
- No GPU needed on the bot server — the heavy lifting happens on the API side.
- Default voice: `assets/default_voice.mp3` (bundled sample).
- `/myvoice`: user sends a voice message → bot clones **their** voice for future texts.
- `/resetvoice`: back to the default voice.

## Run locally

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="...from @BotFather..."
python bot.py
```

## Deploy (Railway)

1. Push this repo to GitHub.
2. Railway → New Project → Deploy from GitHub repo.
3. Add variable `TELEGRAM_BOT_TOKEN`.
4. Deploy — the bot uses long polling, no webhook needed.

## Notes

- The default `VOXCPM_API_BASE` is the public VoxCPM2 demo (free, shared, queued).
  For heavy use, self-host VoxCPM2 on a GPU box and set `VOXCPM_API_BASE` to it.
- Per-user reference voices live in `data/` (ephemeral on Railway redeploys — v1 limitation).
- Max 500 characters per request to keep generations fast.
