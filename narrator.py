import os
import random
import traceback
import numpy as np
import colorsys
import textwrap
import asyncio
import edge_tts
import openai
from gtts import gTTS
# MoviePy v2.0 Imports
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import VideoClip, TextClip, ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip, concatenate_videoclips
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.audio.AudioClip import CompositeAudioClip, concatenate_audioclips

async def run_edge_tts(text, output_path, speed_factor=1.0):
    """
    Async helper for Edge TTS
    """
    # Calculate rate string: e.g. +50% for 1.5, -50% for 0.5
    rate_str = f"{int((speed_factor - 1) * 100):+d}%"
    communicate = edge_tts.Communicate(text, "en-US-JennyNeural", rate=rate_str) 
    await communicate.save(output_path)

def generate_tts_audio(text, output_path, use_openai=False, api_key=None, speed_factor=1.0):
    """
    Generates TTS audio from text.
    Priority: OpenAI -> Edge TTS -> gTTS
    """
    try:
        # 1. OpenAI TTS (If config provided)
        if use_openai and api_key:
            try:
                client = openai.OpenAI(api_key=api_key)
                response = client.audio.speech.create(
                    model="tts-1",
                    voice="alloy",
                    input=text,
                    speed=speed_factor
                )
                response.stream_to_file(output_path)
                return True
            except Exception as e:
                print(f"OpenAI TTS Failed: {e}. Falling back...")
        
        # 2. Edge TTS (High Quality Free)
        try:
            asyncio.run(run_edge_tts(text, output_path, speed_factor))
            return True
        except Exception as e:
             print(f"Edge TTS Failed: {e}. Falling back to gTTS...")

        # 3. gTTS (Fallback)
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(output_path)
        return True
        
    except Exception as e:
        print(f"All TTS Engines Failed: {e}")
        traceback.print_exc()
        return False

def make_rainbow_clip(size, duration):
    """
    Creates a VideoClip of 'size' that cycles through rainbow colors over 'duration'.
    """
    w, h = size
    
    def make_frame(t):
        # Cycle hue based on time
        # speed: 1 full cycle every 2 seconds?
        hue = (t * 0.2) % 1.0 
        rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        # Convert to 0-255 numpy array
        color_array = np.array([int(c*255) for c in rgb], dtype=np.uint8)
        # Create full frame (efficiently)
        return np.tile(color_array, (h, w, 1))

    return VideoClip(make_frame, duration=duration)

def trim_silence(audio_clip, threshold=0.01, padding=0.2):
    """
    Trims silence from the beginning and end of an audio clip.
    threshold: Volume threshold to consider as "sound" (0.0 to 1.0).
    padding: Seconds of silence to keep around the sound.
    """
    try:
        # Get raw audio data as numpy array
        # Use a fixed FPS for analysis, doesn't change actual audio
        analyze_fps = 44100 
        array = audio_clip.to_soundarray(fps=analyze_fps)
        
        # Calculate max volume across channels for each sample
        if array.ndim == 2:
            max_volume = np.max(np.abs(array), axis=1)
        else:
            max_volume = np.abs(array)
            
        # Find indices where volume > threshold
        indices = np.where(max_volume > threshold)[0]
        
        if len(indices) == 0:
            # If strictly silent, return original to be safe
            return audio_clip
            
        start_index = indices[0]
        end_index = indices[-1]
        
        # Convert indices to seconds
        start_time = start_index / analyze_fps
        end_time = end_index / analyze_fps
        
        # Apply padding and clamp
        start_time = max(0, start_time - padding)
        end_time = min(audio_clip.duration, end_time + padding)
        
        # Return subclip
        return audio_clip.subclipped(start_time, end_time)
        
    except Exception as e:
        print(f"Error trimming silence: {e}")
        return audio_clip

def process_narrator_batch(scripts, gameplay_dir, output_dir, use_openai=False, api_key=None, speed_factor=1.0, logger=None):
    """
    Proceses a batch of scripts into narrated videos.
    Refactored for Line-by-Line Sync + Rainbow Borders.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    gameplay_files = [f for f in os.listdir(gameplay_dir) if f.lower().endswith('.mp4')]
    if not gameplay_files:
        if logger: logger("Error: No MP4 files found in gameplay directory.")
        return

    total = len(scripts)
    
    for i, script_text in enumerate(scripts):
        if not script_text.strip():
            continue
            
        try:
            if logger: logger(f"Processing Narrated Video ({i+1}/{total})...")
            
            # Split script into lines and strip quotes
            lines = [l.strip().strip('"').strip("'") for l in script_text.split('\n') if l.strip()]
            
            if not lines:
                continue

            # Generate Audio/Text Components per line
            line_audio_clips = []
            line_video_clips = [] # Subtitle chunks (Composite of Text + Rainbow)
            temp_files_to_clean = []
            
            if logger: logger(f"  Generating components for {len(lines)} lines...")
            
            for line_idx, line in enumerate(lines):
                # 1. TTS for Line
                line_filename = f"temp_tts_{i}_{line_idx}.mp3"
                line_path = os.path.join(output_dir, line_filename)
                
                success = generate_tts_audio(line, line_path, use_openai, api_key, speed_factor)
                if not success:
                    if logger: logger(f"    Failed TTS for line: {line[:20]}...")
                    continue
                
                temp_files_to_clean.append(line_path)
                
                audio_clip = AudioFileClip(line_path)
                
                # Trim silence
                audio_clip = trim_silence(audio_clip, threshold=0.01, padding=0.2)
                
                dur = audio_clip.duration
                line_audio_clips.append(audio_clip)
                
                # 2. Visuals for Line (The Complex Part)
                # Goal: White Text, Rainbow Border.
                
                # Reduced font size to prevent word splitting
                font_size = 75 
                # box_width = 800 # Removing fixed box width strictness in favor of manual wrapping
                
                # Wrap text manually to prevent mid-word splitting (approx 20 chars for font size 75, fits ~1080px)
                wrapped_line = textwrap.fill(line, width=20)
                
                # Add vertical padding to prevent ImageMagick from cropping descenders
                wrapped_line = f"\n{wrapped_line}\n"

                # A. The "Stroke Mask" (Defines the border area)
                # Note: 'color' is fill color. 'stroke_color' is border.
                # To make a mask for the border, we need an opaque stroke.
                # Trick: Create Text with transparent fill, white stroke. 
                # Mask = The Alpha channel of this clip.
                
                # v2 TextClip parameters
                # We need TWO text clips:
                # 1. Border Reference (For mask)
                # 2. White Fill (For overlay)
                
                # IMPORTANT: TextClip creates an ImageClip.
                # Border Ref
                border_txt = TextClip(
                    text=wrapped_line,
                    font_size=font_size,
                    color=(0,0,0,0), # Transparent fill tuple
                    stroke_color='white',
                    stroke_width=3, # Thinner border
                    font='Arial',
                    method='label', # Changed to label to respect manual newlines
                    text_align='center'
                ).with_duration(dur)
                
                # Fill Ref (Clean white text)
                # NOTE: We add a transparent stroke to match the layout/padding of the border clip perfectly.
                fill_txt = TextClip(
                    text=wrapped_line,
                    font_size=font_size,
                    color='white',
                    stroke_color=(0,0,0,0), # Transparent stroke
                    stroke_width=3, # Same width to match metrics
                    font='Arial',
                    method='label',
                    text_align='center'
                ).with_duration(dur)
                
                # B. The Rainbow Background
                # Size matches the text clip
                txt_w, txt_h = border_txt.size
                rainbow_bg = make_rainbow_clip((txt_w, txt_h), dur)
                
                # C. Masking
                # Set rainbow_bg's mask to be the Alpha of border_txt
                # This makes the rainbow only visible where the 'stroke' was.
                # v2.0: .with_mask()
                # We need to extract the mask from border_txt.
                # border_txt is an ImageClip (VideoClip). It has a .mask attribute.
                rainbow_border = rainbow_bg.with_mask(border_txt.mask)
                
                # D. Composite
                # Stack: Rainbow Border (Bottom) -> White Fill (Top)
                # Ensure positions align.
                
                # Position logic involves creating a composite of these two, 
                # AND THEN positioning that composite on the screen.
                
                combined_text_chunk = CompositeVideoClip(
                    [rainbow_border.with_position('center'), fill_txt.with_position('center')], 
                    size=(txt_w, txt_h)
                ).with_duration(dur).with_position('center')
                
                line_video_clips.append(combined_text_chunk)

            if not line_audio_clips:
                if logger: logger("  No audio generated. Skipping.")
                continue
                
            # Concatenate Components
            full_narration_audio = concatenate_audioclips(line_audio_clips)
            
            # Concatenate visual chunks
            # Note: We must ensure they play sequentially. concatenate_videoclips does this.
            full_subtitle_track = concatenate_videoclips(line_video_clips, method="compose")
            full_subtitle_track = full_subtitle_track.with_position('center')
            
            total_duration = full_narration_audio.duration
            target_duration = total_duration + 2.0 
            
            # Video Background
            gameplay_file = random.choice(gameplay_files)
            gameplay_path = os.path.join(gameplay_dir, gameplay_file)
            if logger: logger(f"  Selected Gameplay: {gameplay_file}")
            
            video_clip = VideoFileClip(gameplay_path)
            
            # Loop/Trim Logic
            if video_clip.duration < target_duration:
                loops = int(target_duration // video_clip.duration) + 1
                video_clip = video_clip.loop(n=loops)
            
            if video_clip.duration > target_duration:
                max_start = video_clip.duration - target_duration
                start_t = random.uniform(0, max_start)
                video_clip = video_clip.subclipped(start_t, start_t + target_duration)
            else:
                 video_clip = video_clip.subclipped(0, target_duration)
            
            # Resize
            target_w, target_h = 1080, 1920
            ratio = video_clip.w / video_clip.h
            target_ratio = target_w / target_h
            if ratio > target_ratio:
                 new_h = target_h
                 new_w = int(new_h * ratio)
                 video_clip = video_clip.resized(height=new_h)
                 x_center = new_w / 2
                 video_clip = video_clip.cropped(x1=x_center - target_w/2, width=target_w, height=target_h)
            else:
                 new_w = target_w
                 new_h = int(new_w / ratio)
                 video_clip = video_clip.resized(width=new_w)
                 y_center = new_h / 2
                 video_clip = video_clip.cropped(y1=y_center - target_h/2, width=target_w, height=target_h)

            # Audio Ducking
            gameplay_audio = video_clip.audio
            if gameplay_audio:
                 duck_duration = total_duration
                 bg_ducked = gameplay_audio.subclipped(0, duck_duration).with_volume_scaled(0.2)
                 bg_rest = gameplay_audio.subclipped(duck_duration, target_duration).with_volume_scaled(1.0)
                 
                 final_bg = concatenate_audioclips([bg_ducked, bg_rest])
                 final_audio = CompositeAudioClip([final_bg, full_narration_audio.with_start(0)])
            else:
                 final_audio = full_narration_audio
            
            video_clip.audio = final_audio
            
            # Composite
            final_video = CompositeVideoClip([video_clip, full_subtitle_track])

            # Export
            out_name = f"narrated_{i}_{os.path.basename(gameplay_file)}"
            out_path = os.path.join(output_dir, out_name)
            
            if logger: logger(f"  Exporting: {out_name}")
            
            final_video.write_videofile(
                out_path, 
                codec="libx264", 
                audio_codec="aac", 
                threads=1, 
                fps=24,
                logger=None, 
                temp_audiofile="temp_narrator_audio.m4a", 
                remove_temp=True,
                preset='ultrafast'
            )
            
            # Cleanup
            final_video.close()
            full_narration_audio.close()
            for clip in line_audio_clips: clip.close()
            for path in temp_files_to_clean:
                if os.path.exists(path): os.remove(path)
                
            if logger: logger("  Finished.")

        except Exception as e:
            if logger: logger(f"Error processing script {i}: {e}")
            traceback.print_exc()
            continue

    if logger: logger("Narrator Batch Complete.")
