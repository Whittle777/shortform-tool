import os
import random
import traceback
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import clips_array

def process_batch(source_a, source_b, output_dir, split_ratio=50, max_duration=None, logger=None):
    """
    Process videos from source vectors.
    Refactored to open fresh file handles for every segment to avoid reader corruption/black screens.
    """
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    files_a = [f for f in os.listdir(source_a) if f.lower().endswith('.mp4')]
    files_b = [f for f in os.listdir(source_b) if f.lower().endswith('.mp4')]

    if not files_a or not files_b:
        if logger: logger("Error: One of the source folders is empty or contains no MP4s.")
        return
    
    total = len(files_a)
    
    for i, file_a in enumerate(files_a):
        path_a = os.path.join(source_a, file_a)
        
        # Pick random B
        file_b = random.choice(files_b)
        path_b = os.path.join(source_b, file_b)

        try:
            if logger: logger(f"Processing ({i+1}/{total}): {file_a} + {file_b}")
            
            # 1. READ DURATIONS ONLY (Fast open/close)
            # We need durations to calculate segments.
            # We don't keep these open.
            with VideoFileClip(path_a) as clip_a_temp:
                 duration_a = clip_a_temp.duration
            
            with VideoFileClip(path_b) as clip_b_temp:
                 duration_b = clip_b_temp.duration
            
            if logger: logger(f"  Durations: A={duration_a}s, B={duration_b}s")

            # 2. CALCULATE SEGMENT METADATA
            # Store tuple: (start_a, end_a, start_b, end_b, suffix)
            segment_metadata = []
            
            chunk_duration = None
            if max_duration and max_duration != 'shortest':
                try:
                    chunk_duration = float(max_duration)
                except ValueError:
                    chunk_duration = None
            
            if chunk_duration is not None:
                # Multi-cut mode
                if logger: logger(f"  Multi-cut Mode: Chunk duration {chunk_duration}s")
                
                current_time = 0
                part_idx = 1
                
                while current_time < duration_a:
                    end_time = current_time + chunk_duration
                    real_end_time = min(end_time, duration_a)
                    segment_len = real_end_time - current_time
                    
                    if logger: logger(f"  Part {part_idx} calc: Start={current_time:.2f}, End={real_end_time:.2f}, Len={segment_len:.2f}")

                    if segment_len <= 0.1: 
                        if logger: logger("    Skipping: Segment too short.")
                        break

                    # Handle Gameplay (B) Segment Selection
                    start_b = 0
                    if duration_b > segment_len:
                         max_start = duration_b - segment_len
                         start_b = random.uniform(0, max_start)
                         if logger: logger(f"    Gameplay Reuse: Duration={duration_b}, Random Start={start_b:.2f}, End={start_b+segment_len:.2f}")
                    else:
                         if logger: logger(f"    Warning: Gameplay ({duration_b}s) < Segment ({segment_len}s). Using full clip.")
                         start_b = 0

                    end_b = min(start_b + segment_len, duration_b)
                    
                    segment_metadata.append({
                        "start_a": current_time,
                        "end_a": real_end_time,
                        "start_b": start_b,
                        "end_b": end_b,
                        "len": segment_len,
                        "suffix": f"_part_{part_idx}"
                    })
                    
                    current_time += chunk_duration
                    part_idx += 1
            else:
                # "Shortest" Mode (Single Clip)
                if logger: logger("  Mode: Shortest/Single Clip")
                target_duration = min(duration_a, duration_b)
                segment_metadata.append({
                    "start_a": 0,
                    "end_a": target_duration,
                    "start_b": 0,
                    "end_b": target_duration,
                    "len": target_duration,
                    "suffix": ""
                })

            # 3. PROCESS SEGMENTS INDEPENDENTLY
            for meta in segment_metadata:
                output_filename = f"split_{i}_{file_a}{meta['suffix']}.mp4"
                output_path = os.path.join(output_dir, output_filename)
                
                if logger: logger(f"  Exporting: {output_filename} (Length: {meta['len']:.2f}s)")
                
                # OPEN FRESH INSTANCES
                # Using context managers ensures they close immediately after use
                try:
                    clip_a = VideoFileClip(path_a)
                    clip_b = VideoFileClip(path_b)
                    
                    sub_a = clip_a.subclipped(meta["start_a"], meta["end_a"]).with_duration(meta["len"])
                    # Mute gameplay audio to prevent mixing deadlocks
                    sub_b = clip_b.subclipped(meta["start_b"], meta["end_b"]).with_duration(meta["len"]).without_audio()
                    
                    # Target dimensions
                    target_width = 1080
                    target_height = 1920
                    
                    # Calculate heights
                    height_a = int(target_height * (split_ratio / 100))
                    height_b = target_height - height_a
                    
                    # Resize/Crop
                    def fit_to_size(clip, w, h):
                        clip_r = clip.w / clip.h
                        target_r = w / h
                        if clip_r > target_r:
                            new_h = h
                            new_w = int(h * clip_r)
                            clip_resized = clip.resized(height=new_h)
                            x_center = new_w / 2
                            x1 = x_center - (w / 2)
                            x2 = x_center + (w / 2)
                            return clip_resized.cropped(x1=x1, y1=0, x2=x2, y2=h)
                        else:
                            new_w = w
                            new_h = int(w / clip_r)
                            clip_resized = clip.resized(width=new_w)
                            y_center = new_h / 2
                            y1 = y_center - (h / 2)
                            y2 = y_center + (h / 2)
                            return clip_resized.cropped(x1=0, y1=y1, x2=w, y2=y2)


                    final_a = fit_to_size(sub_a, target_width, height_a)
                    final_b = fit_to_size(sub_b, target_width, height_b)
                    
                    final_video = clips_array([[final_a], [final_b]])
                    
                    if logger: logger(f"  Starting ffmpeg export (threads=1, temp_audiofile)...")
                    final_video.write_videofile(
                        output_path, 
                        codec="libx264", 
                        audio_codec="aac", 
                        threads=1, 
                        logger=None, # Keep logger=None for GUI
                        preset='ultrafast',
                        temp_audiofile="temp-audio.m4a", 
                        remove_temp=True
                    )
                    
                    if logger: logger(f"  Finished ffmpeg export.")
                    
                    # Explicit cleanup for this iteration
                    final_video.close()
                    final_a.close()
                    final_b.close()
                    clip_a.close()
                    clip_b.close()
                    
                    if logger: logger(f"  Success: {output_filename}")

                except Exception as e:
                    if logger: logger(f"  Failed segment {output_filename}: {e}")
                    traceback.print_exc()
                    # Try to clean up if failed
                    try: 
                        clip_a.close()
                        clip_b.close()
                    except: pass
                    continue
            
        except Exception as e:
            if logger: logger(f"Error processing batch item {file_a}: {e}")
            traceback.print_exc()
            continue

    if logger: logger("Batch processing complete.")
