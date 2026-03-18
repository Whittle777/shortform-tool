import importlib
import pkgutil
import moviepy
import inspect

def find_function(package, func_name):
    # Walk through all modules
    for loader, module_name, is_pkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, func_name):
                print(f"FOUND: {func_name} in {module_name}")
                return
        except Exception:
            pass

print("Searching for concatenate_videoclips...")
find_function(moviepy, 'concatenate_videoclips')
