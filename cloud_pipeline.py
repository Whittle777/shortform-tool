import os
import random
from datetime import datetime, timedelta
import requests
from google.cloud import storage
from apscheduler.schedulers.background import BackgroundScheduler

# Global scheduler instance
_scheduler = None

def get_scheduler():
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
        _scheduler.start()
    return _scheduler

def upload_to_gcs(local_path, bucket_name, logger=None):
    """
    Uploads a local file to GCS, sets public read, deletes local file, returns public URL.
    """
    if logger: logger(f"Uploading {local_path} to GCS bucket: {bucket_name}...")
    try:
        # Assumes GOOGLE_APPLICATION_CREDENTIALS is set in env
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # Create a unique blob name using timestamp and filename
        base_name = os.path.basename(local_path)
        timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
        blob_name = f"{timestamp_str}_{base_name}"
        
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_path)
        
        # Since uniform bucket-level access is enabled, we cannot set ACLs on individual blobs.
        # Ensure the bucket itself has "Storage Object Viewer" role for "allUsers" if you want it to be public.
        # blob.make_public() # Removed to prevent legacy ACL errors
        public_url = blob.public_url
        
        if logger: logger(f"Upload successful. Public URL: {public_url}")
        
        # Optional: Delete local file safely after it enters GCS
        # To allow local previews, we will keep the file around instead of deleting it.
        # try:
        #     os.remove(local_path)
        #     if logger: logger(f"Deleted local file: {local_path}")
        # except Exception as cleanup_err:
        #     if logger: logger(f"Warning: Failed to delete local file {local_path}: {cleanup_err}")
            
        return public_url
    except Exception as e:
        if logger: logger(f"Failed to upload to GCS: {e}")
        print(f"Failed to upload to GCS: {e}")
        return None

def calculate_jittered_time(generation_index):
    """
    Given a generation index, calculate when it should be posted.
    Index 0: Today Morning
    Index 1: Today Evening
    Index 2: Tomorrow Morning
    ...
    Morning = 9:00 AM, Evening = 5:00 PM.
    Jitter = -30 to +45 mins.
    If the calculated time is already in the past, push it to tomorrow.
    """
    day_offset = generation_index // 2
    is_evening = (generation_index % 2) != 0
    
    now = datetime.now()
    target_date = now + timedelta(days=day_offset)
    
    if is_evening:
        target_time = target_date.replace(hour=17, minute=0, second=0, microsecond=0)
    else:
        target_time = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
        
    # Jitter: -30 to +45 minutes
    jitter_mins = random.randint(-30, 45)
    target_time = target_time + timedelta(minutes=jitter_mins)
    
    # If the time has already passed today, shift by 24h
    if target_time < now:
        target_time = target_time + timedelta(days=1)
        
    return target_time

def dispatch_youtube_upload(video_path, caption):
    """
    Triggered by the scheduler to fire the YouTube upload.
    """
    print(f"[{datetime.now()}] Firing YouTube Upload for {video_path}")
    import youtube_uploader
    try:
        youtube_uploader.upload_video_to_youtube(video_path, caption)
        print(f"YouTube Upload Triggered Successfully!")
    except Exception as e:
        print(f"YouTube Dispatch Failed: {e}")

def schedule_youtube_post(video_path, caption, generation_index, logger=None):
    """
    Main entry point for placing a generated video onto the queue for YouTube upload.
    """
    target_time = calculate_jittered_time(generation_index)
    
    if logger: logger(f"Scheduling YouTube post for {target_time.strftime('%Y-%m-%d %H:%M:%S')} (Index {generation_index})")
    
    scheduler = get_scheduler()
    scheduler.add_job(
        func=dispatch_youtube_upload,
        trigger='date',
        run_date=target_time,
        args=[video_path, caption]
    )
    if logger: logger("Job successfully queued in background scheduler.")
