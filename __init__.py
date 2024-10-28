
from pathlib import Path
import importlib


bl_info = {
    "name": "XXMI Scripts & Quick Import",
    "author": "Gustav0, LeoTorreZ", 
    "version": (2, 9, 8),
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


import bpy #type: ignore
if "bpy" in locals(): 
    import importlib
    reload_package(locals())


from .tools.tools_operators import classes as quick_import_classes, menu_func
from .xxmi_scripts import * 
from .quickimport.operators import *
from .quickimport.preferences import *

addon_keymaps = []
xxmi_classes = [
    QuickImportSettings,
    XXMI_Scripts_Settings,
    XXMI_TOOLS_PT_main_panel,
    XXMI_TOOLS_PT_quick_import_panel,
    QuickImportRaw,
    QuickImport,
    SavePreferencesOperator
]
classes = quick_import_classes + xxmi_classes


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.xxmi_scripts_settings = bpy.props.PointerProperty(type=XXMI_Scripts_Settings)
    bpy.types.Scene.quick_import_settings = bpy.props.PointerProperty(type=QuickImportSettings)
    preferences = load_preferences()
    if preferences:
        bpy.app.timers.register(lambda: apply_preferences(preferences, bpy.context), first_interval=1.0)
    
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.VIEW3D_MT_object.append(menu_func)


    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    for cls in classes:
        if cls.__name__ == "OBJECT_OT_separate_by_material_and_rename":
            kmi = km.keymap_items.new(cls.bl_idname, 'P', 'PRESS')
            addon_keymaps.append((km, kmi))
            break

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    for cls in classes:
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.xxmi_scripts_settings
    del bpy.types.Scene.quick_import_settings
    
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.VIEW3D_MT_object.remove(menu_func)

if __name__ == '__main__':
    register()
