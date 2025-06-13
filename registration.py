import bpy  # type: ignore
from .tools.tools_operators import classes as quick_import_classes, menu_func
from .ui import *
from .quickimport.operators import *
from .quickimport.preferences import *

addon_keymaps = []


#This part is the biggest headache, blender RNA is really confuse imo
#I add one comment in each step so as not to get lost in the future when editing or adding something, as the slightest change generates conflict with XXMI

# Updated order for classes, settings registered first
xxmi_classes = [
    QuickImportSettings,          # Settings classes first
    XXMI_Scripts_Settings,
    QuickImport,                  # Then main panels and operators
    XXMI_TOOLS_PT_main_panel,
    XXMI_TOOLS_PT_quick_import_panel,
    DemoUpdaterPanel,
    QuickImportFace,
    UpdaterPreferences,
    QuickImportRaw,
    QuickImportArmature, 
    SavePreferencesOperator, 
]

# Consolidate all classes
classes = quick_import_classes + xxmi_classes

# Function to set up keymaps separately
def setup_keymaps():
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    for cls in classes:
        if cls.__name__ == "OBJECT_OT_separate_by_material_and_rename":
            kmi = km.keymap_items.new(cls.bl_idname, 'P', 'PRESS')
            addon_keymaps.append((km, kmi))
            break

# Main register function with improved ordering
def register():
    # Register each class in order, ensuring dependencies are met
    addon_updater_ops.register(bl_info)
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add properties to the scene only after classes are registered
    bpy.types.Scene.xxmi_scripts_settings = bpy.props.PointerProperty(type=XXMI_Scripts_Settings)
    bpy.types.Scene.quick_import_settings = bpy.props.PointerProperty(type=QuickImportSettings)
    
    # Append menus and set up keymaps
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.VIEW3D_MT_object.append(menu_func)
    setup_keymaps()

    # Load preferences if any
    preferences = load_preferences()
    if preferences:
        bpy.app.timers.register(lambda: apply_preferences(preferences, bpy.context), first_interval=0.4)

# Unregister function with improved cleanup
def unregister():
    addon_updater_ops.unregister()
    # Unregister each class if registered
    for cls in classes:
        if hasattr(cls, "bl_rna"):  # Only unregister if registered
            bpy.utils.unregister_class(cls)
    
    # Remove keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Remove menus
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.VIEW3D_MT_object.remove(menu_func)
    
    # Remove properties from scene, with check to prevent errors
    if hasattr(bpy.types.Scene, "xxmi_scripts_settings"):
        del bpy.types.Scene.xxmi_scripts_settings
    if hasattr(bpy.types.Scene, "quick_import_settings"):
        del bpy.types.Scene.quick_import_settings
