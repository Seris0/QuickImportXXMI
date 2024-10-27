
import bpy #type: ignore
import os
from .. import_xxmi_tools import Import3DMigotoFrameAnalysis, Import3DMigotoRaw
from .texturehandling import TextureHandler, TextureHandler42
from .preferences import *

class QuickImportBase:
    def post_import_processing(self, context, folder):

        xxmi = context.window_manager.quick_import_settings
        imported_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if xxmi.reset_rotation:
            self.reset_rotation(context)

        if xxmi.tri_to_quads:
            self.convert_to_quads()

        if xxmi.merge_by_distance:
            self.merge_by_distance()

        if xxmi.import_textures:
            self.setup_textures(context)

        if xxmi.create_collection:
            self.create_collection(context, folder)

        new_meshes = [obj for obj in imported_objects if obj.type == 'MESH']
        
        print(f"New meshes detected: {[obj.name for obj in new_meshes]}")

        if xxmi.import_textures:
            self.assign_existing_materials(new_meshes)

        if xxmi.create_mesh_collection:
            self.create_mesh_collection(context, folder)
        
        bpy.ops.object.select_all(action='DESELECT')
        
    def assign_existing_materials(self, new_meshes):
        for obj in new_meshes:
            if not obj.material_slots:
                combined_name, letter = self.extract_combined_name(obj.name)
                print(f"Combined name extracted for {obj.name}: '{combined_name}', letter: '{letter}'")

                if combined_name:
                    matching_material = self.find_matching_material(combined_name, letter)
                
                    if matching_material:
                        obj.data.materials.append(matching_material)
                        print(f"Assigned material {matching_material.name} to {obj.name}")
                    else:
                        print(f"No matching material found for {obj.name} with combined name '{combined_name}'")
                else:
                    print(f"No valid combined name found in {obj.name} to match materials")

    def extract_combined_name(self, name):
        keywords = ['Body', 'Head', 'Arm', 'Leg', 'Dress', 'Extra', 'Extras', 'Hair', 'Mask', 'Idle']
        for keyword in keywords:
            if keyword in name:
                parts = name.split(keyword)
                prefix = parts[0]
                letter = parts[1][0] if len(parts) > 1 and parts[1] else ''
                combined_name = prefix + keyword
                print(f"Combined name '{combined_name}' created from '{prefix}' and '{keyword}' for {name}, letter: '{letter}'")
                return combined_name, letter
        print(f"No keywords matched in {name}")
        return "", ""

    def find_matching_material(self, combined_name, letter):
        # F4ck you Asta 
        if combined_name == "AstaBody":
            asta_material_mapping = {
                'C': 'BodyB',
                'D': 'BodyA',
                'E': 'BodyB'
            }
            target_material_suffix = asta_material_mapping.get(letter)
            if target_material_suffix:
                for material in bpy.data.materials:
                    if material.name.startswith("mat_") and target_material_suffix in material.name:
                        print(f"Found material {material.name} for Asta rule with letter '{letter}'")
                        return material
                print(f"No Asta rule material found for letter '{letter}'")
            else:
                print(f"Letter '{letter}' does not match Asta rule requirements")
            return None

        # Standard matching logic for other prefixes, SCYLL WHY THE ENTIRE ALPHABET
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        start_index = letters.index(letter) if letter in letters else -1

        for i in range(start_index, -1, -1):
            current_letter = letters[i] if i >= 0 else ''
            for material in bpy.data.materials:
                print(f"Checking material {material.name} for match with combined name '{combined_name}{current_letter}'")
                if material.name.startswith("mat_") and f"{combined_name}{current_letter}" in material.name:
                    return material

        return None
           
    def create_collection(self, context, folder):
        collection_name = os.path.basename(folder)
        new_collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(new_collection)

        for obj in bpy.context.selected_objects:
            if obj.users_collection:  
                for coll in obj.users_collection:
                    coll.objects.unlink(obj)
            new_collection.objects.link(obj)
            print(f"Moved {obj.name} to collection {collection_name}")

    def create_mesh_collection(self, context, folder):
        #Sins logic for collections with custom properties, 
        # I will probably change this to don't use bmesh in future
        import bmesh #type: ignore
        collection_name = os.path.basename(folder)
        new_collection = bpy.data.collections.new(collection_name+"_CustomProperties")
        bpy.context.scene.collection.children.link(new_collection)
        new_collection.color_tag = "COLOR_08"

        for obj in bpy.context.selected_objects:
            if obj.name.startswith(collection_name):
                bpy.ops.object.mode_set(mode='OBJECT')
                bpy.context.scene.collection.objects.unlink(obj)
                new_collection.objects.link(obj)
                new_collection.hide_select = True

                try:
                    #duplicate data to new containers in collections
                    name = obj.name.split(collection_name)[1].rsplit("-", 1)[0]
                    new_sub_collection = bpy.data.collections.new(obj.name.rsplit("-", 1)[0])
                    bpy.context.scene.collection.children.link(new_sub_collection)
                    ob = bpy.data.objects.new(name = name, object_data = obj.data.copy())
                    ob.location = obj.location
                    ob.rotation_euler = obj.rotation_euler
                    ob.scale = obj.scale
                    new_sub_collection.objects.link(ob)

                    #Del verts of imported containers
                    bm = bmesh.new()
                    bm.from_mesh(obj.data)
                    [bm.verts.remove(v) for v in bm.verts]
                    bm.to_mesh(obj.data)
                    obj.data.update()
                    bm.free()
                    print(f"Moved {obj.name} to collection {name} as {ob.name}.")
                    obj.name = obj.name.rsplit("-", 1)[0] + "-KeepEmpty"
                    print(f"{obj.name} maintains custom properties, don't delete.")

                except IndexError:
                    print(f"Failed on {obj.name} as it does not contain collection name")
            else:
                print(f"Ignored {obj.name} as it does not match the collection name")

    def reset_rotation(self, context):
        for obj in context.selected_objects:
            if obj.name in [o.name for o in bpy.context.selected_objects]:
                obj.rotation_euler = (0, 0, 0)

    def convert_to_quads(self):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.tris_convert_to_quads(uvs=True, vcols=True, seam=True, sharp=True, materials=True)
        bpy.ops.mesh.delete_loose()

    def merge_by_distance(self):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(use_sharp_edge_from_normals=True)
        bpy.ops.mesh.delete_loose()

    def setup_textures(self, context):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.delete_loose()
        bpy.ops.object.mode_set(mode='OBJECT')
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.shading.type = 'MATERIAL'

class QuickImport(Import3DMigotoFrameAnalysis, QuickImportBase):
    """Setup Character .txt file"""
    bl_idname = "import_scene.3dmigoto_frame_analysis"
    bl_label = "Quick Import for XXMI"
    bl_options = {"UNDO"}

    def execute(self, context):
        cfg = context.window_manager.quick_import_settings
        super().execute(context)
        folder = os.path.dirname(self.properties.filepath)
        print("------------------------")

        print(f"Found Folder: {folder}")
        files = os.listdir(folder)
        print (f"Files: {files}")
        texture_files = []
        if cfg.import_textures:
            texture_map = {
                "Diffuse": cfg.import_diffuse,
                "DiffuseUlt" : cfg.import_diffuse,
                "NormalMap": cfg.import_normalmap,
                "LightMap": cfg.import_lightmap,
                "StockingMap": cfg.import_stockingmap,
                "MaterialMap": cfg.import_materialmap
                # if cfg.game == 'HSR' else False,
            }

            for texture_type, should_import in texture_map.items():
                if should_import:
                    texture_files.extend([f for f in files if f.lower().endswith(f"{texture_type.lower()}.dds")])
            print(f"Texture files: {texture_files}")
        if bpy.app.version < (4, 2, 0):
            importedmeshes = TextureHandler.create_material(context, texture_files, folder)
        else:
            importedmeshes = TextureHandler42.create_material(context, files, folder)

        print(f"Imported meshes: {[obj.name for obj in importedmeshes]}")

        self.post_import_processing(context, folder)

        return {"FINISHED"}

class QuickImportRaw(Import3DMigotoRaw, QuickImportBase):
    """Setup Character file with raw data .IB + .VB"""
    bl_idname = "import_scene.3dmigoto_raw"
    bl_label = "Quick Import Raw for XXMI"
    bl_options = {"UNDO"}

    def execute(self, context):
        result = super().execute(context)
        if result != {"FINISHED"}:
            return result
        
        folder = os.path.dirname(self.properties.filepath)
        print("------------------------")

        print(f"Found Folder: {folder}")
        files = os.listdir(folder)
        files = [f for f in files if f.endswith("Diffuse.dds")]
        print(f"List of files: {files}")

        if bpy.app.version < (4, 2, 0):
            importedmeshes = TextureHandler.create_material(context, files, folder)
        else:
            importedmeshes = TextureHandler42.create_material(context, files, folder)

        print(f"Imported meshes: {[obj.name for obj in importedmeshes]}")

        self.post_import_processing(context, folder)

        return {"FINISHED"}

class SavePreferencesOperator(bpy.types.Operator):
    bl_idname = "quickimport.save_preferences"
    bl_label = "Save Import Settings"
    bl_description = "Save current QuickImport settings as default preferences"
    
    def execute(self, context):
        save_preferences(context)
        self.report({'INFO'}, "Preferences saved successfully!")
        return {'FINISHED'}
       
def menu_func_import(self, context):
    self.layout.operator(QuickImport.bl_idname, text="Quick Import for XXMI")   
    self.layout.operator(QuickImportRaw.bl_idname, text="Quick Import Raw for XXMI")
