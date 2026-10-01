# shortform-tool

Automates shortform narrated videos: gameplay background, TTS narration, glowing rainbow subtitles, optional YouTube upload.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

For YouTube uploads: drop your `client_secret_*.json` (Google Cloud OAuth client, YouTube Data API v3 enabled) in the repo root, then run `.venv/bin/python cli.py --auth` once to create `token.json`.

Optional `.env` keys: `GEMINI_API_KEY` (script generation via `--prompt`), `OPENAI_API_KEY` (better TTS voice; otherwise edge-tts is used, which is free).

## Headless CLI

Render from your own scripts (JSON array of `{"script": "line\nline", "caption": "..."}`):

```
.venv/bin/python cli.py --scripts-json scripts.json --gameplay-dir ./gameplay --upload none
```

Render with Gemini-written scripts:

```
.venv/bin/python cli.py --prompt "psychology facts" --count 3 --gameplay-dir ./gameplay
```

Upload an existing video, now or scheduled (RFC3339 UTC):

```
.venv/bin/python cli.py --upload-video Narrated_Cuts/out.mp4 --caption "..." [--publish-at 2026-09-01T17:00:00Z] [--privacy public|unlisted|private]
```

Batch with jittered daily slots (videos publish via YouTube's publishAt, nothing stays running locally). The queue exists because YouTube's API quota allows only ~6 uploads/day:

```
.venv/bin/python cli.py --scripts-json scripts.json --gameplay-dir ./gameplay --schedule --queue
.venv/bin/python cli.py --drain 6         # run daily until the queue is empty
.venv/bin/python cli.py --queue-status
```

Slots and jitter are configurable: `--slots "09:00,17:00" --jitter "-30,45"` (local times).

The last line of stdout is a JSON summary (rendered paths, captions, YouTube URLs).

Drop background mp4s in `gameplay/` (gitignored). Clips of 60+ seconds work best.

## Claude Code skill

`~/.claude/skills/post-video/SKILL.md` wraps this CLI so you can just ask Claude to write, render, and post videos. Claude authors the scripts and captions, renders with this CLI, shows you the result, and uploads after you confirm.

## GUI

The original PyQt app still works: `.venv/bin/python main.py`
