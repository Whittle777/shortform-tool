# Handoff: shortform-tool session state (2026-09-01)

Read this plus README.md before touching anything. The Claude skill lives at
`~/.claude/skills/post-video/SKILL.md` and is the workflow authority.

## What is set up and verified

- Repo cloned to `~/projects/shortform-tool`, venv at `.venv` (system Python 3.9).
- Headless `cli.py` added: render from scripts JSON or Gemini prompt, upload
  (now / scheduled / private / unlisted), jittered batch scheduling, quota queue,
  drain, stats, auth. GUI (`main.py`) untouched and still works.
- YouTube uploader is OAuth-linked to the Study Surfers channel account
  `stdysurfers@gmail.com`. Verified with a real private upload:
  video ID oUuLQw80-jU ("Connection test", safe to delete in YT Studio).
- Google Cloud project: `study-surfer0` (Henry's Firebase project, console access
  via henrywhittle2001@gmail.com). YouTube Data API v3 enabled. OAuth app
  "Study Surfers Uploader" (External, Testing). Desktop client "shortform-tool";
  secret JSON is in the repo root (gitignored). Test users: henrywhittle2001,
  stdysurfers.
- End-to-end render verified (TTS + glowing captions + 1080x1920 export).

## Standing caveats

- Testing mode = token.json dies every ~7 days. Fix per re-auth:
  `cd ~/projects/shortform-tool && .venv/bin/python cli.py --auth`
  and sign in as stdysurfers@gmail.com. Permanent fix: finish Branding page in
  Google Auth Platform and push app to production (not done yet).
- YouTube API quota: ~6 uploads/day (1600 units each / 10000 cap). Hence the
  queue + `--drain 6`. Quota resets midnight Pacific.
- Unverified-project risk: first real PUBLIC post may get locked private by
  YouTube. Check the first public post; if locked, project needs verification.
- youtube.readonly scope was added to SCOPES for `--stats` AFTER token.json was
  minted. `--stats` will 403 until the next re-auth (weekly re-auth picks it up).

## Pending / not done

- `gameplay/` folder is EMPTY. Henry must drop Study Surfers screen recordings
  (mp4, 60+ seconds) there before the first real video.
- Drain automation (daily cron/launchd) NOT installed; Henry chooses ping-me vs
  automated. Production push is a prerequisite for reliable automation.
- Production push attempted 2026-09-01: all required Branding fields are filled
  and saved, but the Audience page still shows "configuration incomplete" and
  Publish app is greyed out. This looks like Google-side propagation delay
  (console warns settings can take minutes to hours). Next session: open
  https://console.cloud.google.com/auth/audience?project=study-surfer0 as
  henrywhittle2001, click Publish app, confirm, then have Henry re-auth once
  (cli.py --auth as stdysurfers) to mint a non-expiring token that also carries
  the youtube.readonly scope for --stats. Do NOT upload an app logo; a logo
  triggers mandatory Google verification review.
- Delete the duplicate client secret download left in ~/Downloads ("...(1).json").
- Test video oUuLQw80-jU still on the channel (private).

## Batch workflow (the point of all this)

1. Claude writes N scripts+captions (see SKILL.md format), shows Henry.
2. Render + schedule + queue:
   `.venv/bin/python cli.py --scripts-json S.json --gameplay-dir ./gameplay --schedule --queue`
   (slots default 09:00,17:00 local, jitter -30..+45 min, 2/day)
3. Upload 6/day until empty: `.venv/bin/python cli.py --drain 6`
   Publish times ride with each upload (YouTube publishAt), so drain day never
   changes posting day.
4. Feedback loop: `.venv/bin/python cli.py --stats` returns views/likes/comments
   per posted video (sorted by views, caption attached from the queue log).
   Review before writing the next batch; bias toward what performed.
