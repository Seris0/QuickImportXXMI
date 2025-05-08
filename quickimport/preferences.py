import json
import os
import bpy #type: ignore

def get_preferences_path():
    settings_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "user_settings")
    os.makedirs(settings_dir, exist_ok=True)
    return os.path.join(settings_dir, "quickimport_preferences.json")

def save_preferences(context):
    prefs = context.scene.quick_import_settings
    preferences = {
        "tri_to_quads": prefs.tri_to_quads,
        "merge_by_distance": prefs.merge_by_distance,
        "reset_rotation": prefs.reset_rotation,
        "import_textures": prefs.import_textures,
        "create_collection": prefs.create_collection,
        "create_mesh_collection": prefs.create_mesh_collection,
        "hide_textures": prefs.hide_textures,
        "import_diffuse": prefs.import_diffuse,
        "import_lightmap": prefs.import_lightmap,
        "import_normalmap": prefs.import_normalmap,
        "import_materialmap": prefs.import_materialmap,
        "import_stockingmap": prefs.import_stockingmap,
        "import_face": prefs.import_face,
        "import_armature": prefs.import_armature,
        "flip_mesh": prefs.flip_mesh
    }
    
    with open(get_preferences_path(), 'w') as f:
        json.dump(preferences, f, indent=4)

def load_preferences():
    prefs_path = get_preferences_path()
    if os.path.exists(prefs_path):
        with open(prefs_path, 'r') as f:
            preferences = json.load(f)
            
        # Store preferences to be loaded after Blender fully starts
        return preferences
    
    return None

def apply_preferences(preferences, context):         
        if preferences and hasattr(bpy.context.scene, 'quick_import_settings'):
            prefs = context.scene.quick_import_settings
            prefs.tri_to_quads = preferences.get("tri_to_quads", False)
            prefs.merge_by_distance = preferences.get("merge_by_distance", False) 
            prefs.reset_rotation = preferences.get("reset_rotation", False)
            prefs.import_textures = preferences.get("import_textures", True)
            prefs.create_collection = preferences.get("create_collection", True)
            prefs.create_mesh_collection = preferences.get("create_mesh_collection", True)
            prefs.hide_textures = preferences.get("hide_textures", False)
            prefs.import_diffuse = preferences.get("import_diffuse", True)
            prefs.import_lightmap = preferences.get("import_lightmap", False)
            prefs.import_normalmap = preferences.get("import_normalmap", False)
            prefs.import_materialmap = preferences.get("import_materialmap", False)
            prefs.import_stockingmap = preferences.get("import_stockingmap", False)
            prefs.import_face = preferences.get("import_face", False)
            prefs.import_armature = preferences.get("import_armature", False)
            prefs.flip_mesh = preferences.get("flip_mesh", False)

