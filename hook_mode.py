import os
import random
import traceback
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip, concatenate_videoclips

def resize_to_9_16(clip, target_w=1080, target_h=1920):
    """
    Resizes and crops a clip to fill 9:16 frame (1080x1920)
    """
    ratio = clip.w / clip.h
    target_ratio = target_w / target_h
    
    if ratio > target_ratio:
        # Too wide, fit height and crop width
        new_h = target_h
        new_w = int(new_h * ratio)
        clip = clip.resized(height=new_h)
        x_center = new_w / 2
        clip = clip.cropped(x1=x_center - target_w/2, width=target_w, height=target_h)
    else:
        # Too tall/narrow, fit width and crop height
        new_w = target_w
        new_h = int(new_w / ratio)
        clip = clip.resized(width=new_w)
        y_center = new_h / 2
        clip = clip.cropped(y1=y_center - target_h/2, width=target_w, height=target_h)
        
    return clip

def process_hook_batch(viral_dir, gameplay_dir, output_dir, hook_duration=5.0, logger=None):
    """
    Processes viral videos into hook segments and appends full gameplay.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    viral_files = [f for f in os.listdir(viral_dir) if f.lower().endswith('.mp4')]
    gameplay_files = [f for f in os.listdir(gameplay_dir) if f.lower().endswith('.mp4')]

    if not viral_files or not gameplay_files:
        if logger: logger("Error: Missing MP4 files in one of the source directories.")
        return

    total_viral = len(viral_files)
    
    for i, viral_file in enumerate(viral_files):
        viral_path = os.path.join(viral_dir, viral_file)
        
        try:
            if logger: logger(f"Processing Viral Clip ({i+1}/{total_viral}): {viral_file}")
            
            # Read viral duration
            with VideoFileClip(viral_path) as viral_clip_ref:
                v_dur = viral_clip_ref.duration
            
            # Calculate segments
            current_time = 0.0
            part_idx = 1
            
            while current_time + 1.0 < v_dur: # Ensure at least 1s remains
                end_time = min(current_time + hook_duration, v_dur)
                
                # Check if segment is substantial enough
                if end_time - current_time < 0.5:
                    break
                
                if logger: logger(f"  Segment {part_idx}: {current_time:.1f}s - {end_time:.1f}s")
                
                # Select random gameplay
                gp_file = random.choice(gameplay_files)
                gp_path = os.path.join(gameplay_dir, gp_file)
                
                output_filename = f"hook_{i}_{part_idx}_{viral_file}"
                output_path = os.path.join(output_dir, output_filename)
                
                try:
                    # Create Clips
                    viral_clip = VideoFileClip(viral_path)
                    gameplay_clip = VideoFileClip(gp_path)
                    
                    # Cut Hook
                    hook_clip = viral_clip.subclipped(current_time, end_time)
                    
                    # Resize both to target
                    hook_processed = resize_to_9_16(hook_clip)
                    gameplay_processed = resize_to_9_16(gameplay_clip)
                    
                    # Concatenate [Hook] + [Gameplay]
                    final_video = concatenate_videoclips([hook_processed, gameplay_processed], method="compose")
                    
                    # Export
                    if logger: logger(f"    Exporting: {output_filename}...")
                    final_video.write_videofile(
                        output_path,
                        codec="libx264",
                        audio_codec="aac",
                        threads=1,
                        logger=None,
                        fps=24,
                        preset='ultrafast',
                        temp_audiofile=f"temp_audio_hook_{i}_{part_idx}.m4a",
                        remove_temp=True
                    )
                    
                    # Cleanup
                    final_video.close()
                    hook_processed.close()
                    gameplay_processed.close()
                    hook_clip.close()
                    viral_clip.close()
                    gameplay_clip.close()
                    
                except Exception as e:
                    if logger: logger(f"    Error on segment {part_idx}: {e}")
                    traceback.print_exc()
                
                current_time += hook_duration
                part_idx += 1
                
        except Exception as e:
            if logger: logger(f"Error processing file {viral_file}: {e}")
            traceback.print_exc()
            continue

    if logger: logger("Hook Batch Complete.")
