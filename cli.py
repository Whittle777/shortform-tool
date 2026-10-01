"""
Headless CLI for the shortform narrator pipeline.

Modes:
  Render:      cli.py --scripts-json scripts.json --gameplay-dir ./gameplay [--upload now|none] [--publish-at ISO]
               cli.py --prompt "topic..." --count 3 --gameplay-dir ./gameplay   (Gemini writes the scripts)
  Upload only: cli.py --upload-video path.mp4 --caption "..." [--publish-at ISO]
  Auth:        cli.py --auth

Prints a JSON summary on the last line so callers can parse results.
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

# Run relative to this file so client_secret_*.json / token.json / .env resolve.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


def parse_rfc3339(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        sys.exit(f"Invalid --publish-at value: {value!r}. Use RFC3339 UTC, e.g. 2026-09-01T17:00:00Z")


def to_rfc3339(dt):
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_slots(s):
    slots = []
    for part in s.split(","):
        hh, mm = part.strip().split(":")
        slots.append((int(hh), int(mm)))
    return slots


def build_schedule(n, slots, jitter_min, jitter_max):
    """
    Local publish times for n videos: walk forward day by day through the
    daily slots, apply random jitter, skip anything not comfortably in the
    future. Returns n datetimes in order.
    """
    times = []
    day = 0
    floor = datetime.now() + timedelta(minutes=20)
    while len(times) < n:
        for hh, mm in slots:
            base = (datetime.now() + timedelta(days=day)).replace(
                hour=hh, minute=mm, second=0, microsecond=0)
            t = base + timedelta(minutes=random.randint(jitter_min, jitter_max))
            if t > floor:
                times.append(t)
                if len(times) == n:
                    break
        day += 1
    return times


QUEUE_FILE = "upload_queue.json"


def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE) as f:
            return json.load(f)
    return {"pending": [], "done": []}


def save_queue(data):
    with open(QUEUE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def main():
    p = argparse.ArgumentParser(description="Headless CLI for the shortform narrator pipeline.")
    p.add_argument("--scripts-json", help="Path to a JSON array of {script, caption} objects (skips Gemini)")
    p.add_argument("--prompt", help="Prompt for Gemini script generation (needs GEMINI_API_KEY)")
    p.add_argument("--count", type=int, default=1, help="Number of scripts to generate with --prompt")
    p.add_argument("--gameplay-dir", help="Folder of background gameplay mp4s")
    p.add_argument("--output-dir", help="Where rendered videos go (default: ./Narrated_Cuts)")
    p.add_argument("--speed", type=float, default=1.0, help="Narration speed factor")
    p.add_argument("--upload", choices=["none", "now"], default="none",
                   help="Whether to upload rendered videos to YouTube immediately")
    p.add_argument("--publish-at",
                   help="RFC3339 UTC time (e.g. 2026-09-01T17:00:00Z). Uploads as private and YouTube "
                        "publishes at that time. With multiple videos, each later video gets +1 day. Implies upload.")
    p.add_argument("--upload-video", help="Upload one existing video file and exit (requires --caption)")
    p.add_argument("--caption", help="Caption for --upload-video")
    p.add_argument("--privacy", choices=["public", "unlisted", "private"], default="public",
                   help="Privacy for uploaded videos (ignored when --publish-at is set)")
    p.add_argument("--schedule", action="store_true",
                   help="Give each rendered video a jittered publish time from the daily --slots, "
                        "walking forward day by day. Uploads private; YouTube publishes on schedule.")
    p.add_argument("--slots", default="09:00,17:00",
                   help="Comma-separated local times of day for --schedule (default 09:00,17:00)")
    p.add_argument("--jitter", default="-30,45",
                   help="Jitter range in minutes around each slot, min,max (default -30,45)")
    p.add_argument("--queue", action="store_true",
                   help="With --schedule: write videos to upload_queue.json instead of uploading. "
                        "Use --drain to upload later (YouTube quota allows ~6 uploads/day).")
    p.add_argument("--drain", type=int, metavar="N",
                   help="Upload up to N pending videos from upload_queue.json and exit")
    p.add_argument("--queue-status", action="store_true", help="Print the upload queue and exit")
    p.add_argument("--stats", action="store_true",
                   help="Fetch YouTube stats (views, likes, comments) for uploaded videos and exit. "
                        "Needs the youtube.readonly scope on token.json (re-run --auth once after upgrading).")
    p.add_argument("--ids", help="Comma-separated video IDs for --stats (default: all done queue entries)")
    p.add_argument("--auth", action="store_true", help="Run the YouTube OAuth flow and exit")
    args = p.parse_args()

    # --- Auth-only mode ---
    if args.auth:
        import youtube_uploader
        ok = youtube_uploader.initialize_youtube_auth(logger=print)
        print(json.dumps({"auth": "ok" if ok else "failed"}))
        sys.exit(0 if ok else 1)

    publish_base = parse_rfc3339(args.publish_at) if args.publish_at else None

    # --- Queue status ---
    if args.queue_status:
        print(json.dumps(load_queue(), indent=2))
        sys.exit(0)

    # --- Stats mode ---
    if args.stats:
        import youtube_uploader
        queue = load_queue()
        by_id = {d["video_id"]: d for d in queue["done"] if d.get("video_id")}
        ids = args.ids.split(",") if args.ids else list(by_id)
        if not ids:
            sys.exit("No video IDs known. Pass --ids or upload through the queue first.")
        yt = youtube_uploader.get_authenticated_service(logger=print)
        stats = []
        for i in range(0, len(ids), 50):
            resp = yt.videos().list(part="statistics,snippet,status",
                                    id=",".join(ids[i:i + 50])).execute()
            for item in resp.get("items", []):
                st = item.get("statistics", {})
                stats.append({
                    "video_id": item["id"],
                    "url": f"https://youtube.com/shorts/{item['id']}",
                    "title": item["snippet"]["title"],
                    "privacy": item["status"].get("privacyStatus"),
                    "published_at": item["snippet"].get("publishedAt"),
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0)),
                    "caption": by_id.get(item["id"], {}).get("caption"),
                })
        stats.sort(key=lambda s: -s["views"])
        print(json.dumps({"stats": stats}, indent=2))
        sys.exit(0)

    # --- Drain mode: upload up to N queued videos ---
    if args.drain is not None:
        import youtube_uploader
        data = load_queue()
        uploaded, remaining = [], []
        for item in data["pending"]:
            if len(uploaded) >= args.drain:
                remaining.append(item)
                continue
            publish_at = item["publish_at"]
            # If the drain ran late and the slot already passed, publish shortly.
            if parse_rfc3339(publish_at) < datetime.now(timezone.utc) + timedelta(minutes=16):
                publish_at = to_rfc3339(datetime.now(timezone.utc) + timedelta(minutes=20))
            video_id = youtube_uploader.upload_video_to_youtube(
                item["path"], item["caption"], logger=print, publish_at=publish_at
            )
            if video_id:
                item["video_id"] = video_id
                item["url"] = f"https://youtube.com/shorts/{video_id}"
                data["done"].append(item)
                uploaded.append(item)
            else:
                remaining.append(item)
        data["pending"] = remaining
        save_queue(data)
        print(json.dumps({"uploaded": uploaded, "still_pending": len(remaining)}, indent=2))
        sys.exit(0)

    # --- Upload-only mode ---
    if args.upload_video:
        if not args.caption:
            sys.exit("--upload-video requires --caption")
        if not os.path.exists(args.upload_video):
            sys.exit(f"Video not found: {args.upload_video}")
        import youtube_uploader
        video_id = youtube_uploader.upload_video_to_youtube(
            args.upload_video, args.caption, logger=print,
            publish_at=to_rfc3339(publish_base) if publish_base else None,
            privacy=args.privacy
        )
        summary = {
            "uploaded": [{
                "path": args.upload_video,
                "video_id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}" if video_id else None,
                "publish_at": to_rfc3339(publish_base) if publish_base else "now",
            }]
        }
        print(json.dumps(summary, indent=2))
        sys.exit(0 if video_id else 1)

    # --- Render mode ---
    if not args.gameplay_dir:
        sys.exit("Render mode requires --gameplay-dir")
    if not os.path.isdir(args.gameplay_dir):
        sys.exit(f"Gameplay dir not found: {args.gameplay_dir}")

    from narrator import process_narrator_batch, generate_scripts_from_prompt

    if args.scripts_json:
        with open(args.scripts_json) as f:
            scripts = json.load(f)
        if not isinstance(scripts, list):
            sys.exit("scripts JSON must be an array of {script, caption} objects")
    elif args.prompt:
        scripts = generate_scripts_from_prompt(args.prompt, args.count, logger=print)
        if not scripts:
            sys.exit("Gemini returned no scripts")
    else:
        sys.exit("Provide --scripts-json or --prompt")

    output_dir = args.output_dir or os.path.join(os.getcwd(), "Narrated_Cuts")

    results = process_narrator_batch(
        scripts=scripts,
        gameplay_dir=args.gameplay_dir,
        output_dir=output_dir,
        use_openai=bool(os.getenv("OPENAI_API_KEY")),
        api_key=os.getenv("OPENAI_API_KEY"),
        speed_factor=args.speed,
        logger=print,
        upload_mode="none",
    )

    summary = {"rendered": results, "uploaded": [], "queued": []}

    schedule_times = None
    if args.schedule:
        jmin, jmax = (int(x) for x in args.jitter.split(","))
        schedule_times = build_schedule(len(results), parse_slots(args.slots), jmin, jmax)

    if args.schedule and args.queue:
        data = load_queue()
        for r, t in zip(results, schedule_times):
            entry = {"path": r["path"], "caption": r["caption"], "publish_at": to_rfc3339(t),
                     "publish_local": t.strftime("%a %Y-%m-%d %H:%M")}
            data["pending"].append(entry)
            summary["queued"].append(entry)
        save_queue(data)
    elif args.upload == "now" or publish_base or args.schedule:
        import youtube_uploader
        for idx, r in enumerate(results):
            if schedule_times:
                publish_at = to_rfc3339(schedule_times[idx])
            elif publish_base:
                publish_at = to_rfc3339(publish_base + timedelta(days=idx))
            else:
                publish_at = None
            video_id = youtube_uploader.upload_video_to_youtube(
                r["path"], r["caption"], logger=print, publish_at=publish_at,
                privacy=args.privacy
            )
            summary["uploaded"].append({
                "path": r["path"],
                "video_id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}" if video_id else None,
                "publish_at": publish_at or "now",
            })

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
