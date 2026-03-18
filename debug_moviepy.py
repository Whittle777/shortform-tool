import importlib
import pkgutil
import moviepy.video.compositing

print("Contents of moviepy.video.compositing:")
for loader, module_name, is_pkg in pkgutil.walk_packages(moviepy.video.compositing.__path__):
    print(module_name)

try:
    from moviepy.video.compositing.concatenate import concatenate_videoclips
    print("SUCCESS: moviepy.video.compositing.concatenate import worked (weirdly)")
except ImportError as e:
    print(f"FAILED: {e}")
