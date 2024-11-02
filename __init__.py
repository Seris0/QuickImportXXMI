# __init__.py

from pathlib import Path
import importlib

bl_info = {
    "name": "XXMI Scripts & Quick Import",
    "author": "Gustav0, LeoTorreZ", 
    "version": (3, 0, 0),
    "blender": (3, 6, 2),
    "description": "Script Compilation",
    "category": "Object",
    "tracker_url": "https://github.com/Seris0/Gustav0/tree/main/Addons/QuickImportXXMI",
}

def reload_package(module_dict_main):
    def reload_package_recursive(current_dir, module_dict):
        for path in current_dir.iterdir():
            if "__init__" in str(path) or path.stem not in module_dict:
                continue
            if path.is_file() and path.suffix == ".py":
                importlib.reload(module_dict[path.stem])
            elif path.is_dir():
                reload_package_recursive(path, module_dict[path.stem].__dict__)
    reload_package_recursive(Path(__file__).parent, module_dict_main)

if "bpy" in locals(): 
    import bpy  #type: ignore
    reload_package(locals())

from . import registration 

def register():
    registration.register()

def unregister():
    registration.unregister()

if __name__ == '__main__':
    register()
