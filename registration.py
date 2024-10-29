# registration.py

import bpy  # type: ignore
from .tools.tools_operators import classes as quick_import_classes, menu_func
from .xxmi_scripts import *
from .quickimport.operators import *
from .quickimport.preferences import *

addon_keymaps = []
xxmi_classes = [
    QuickImport,
    QuickImportSettings,
    XXMI_Scripts_Settings,
    XXMI_TOOLS_PT_main_panel,
    XXMI_TOOLS_PT_quick_import_panel,
    QuickImportFace,
    QuickImportRaw,
    QuickImportArmature, 
    SavePreferencesOperator,
    BaseAnalysis,  
]
classes = quick_import_classes + xxmi_classes

def delayed_register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.xxmi_scripts_settings = bpy.props.PointerProperty(type=XXMI_Scripts_Settings)
    bpy.types.Scene.quick_import_settings = bpy.props.PointerProperty(type=QuickImportSettings)
    preferences = load_preferences()
    if preferences:
        bpy.app.timers.register(lambda: apply_preferences(preferences, bpy.context), first_interval=0.4)
    
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.VIEW3D_MT_object.append(menu_func)

    # Keymap setup
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    for cls in classes:
        if cls.__name__ == "OBJECT_OT_separate_by_material_and_rename":
            kmi = km.keymap_items.new(cls.bl_idname, 'P', 'PRESS')
            addon_keymaps.append((km, kmi))
            break

def register():
    bpy.app.timers.register(delayed_register, first_interval=0.3)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
        
    del bpy.types.Scene.xxmi_scripts_settings
    del bpy.types.Scene.quick_import_settings
    
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.VIEW3D_MT_object.remove(menu_func)
