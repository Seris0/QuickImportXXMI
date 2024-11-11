
import bpy #type: ignore
import os
from .. import_xxmi_tools import Import3DMigotoFrameAnalysis, Import3DMigotoRaw
from .texturehandling import TextureHandler, TextureHandler42
from .preferences import *
import re

class QuickImportBase:
    def post_import_processing(self, context, folder):

        xxmi = context.scene.quick_import_settings
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

        if xxmi.import_face:
            self.import_face(context)

        if xxmi.import_armature:
            self.import_armature(context)
            
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

        selected_objects = [obj for obj in bpy.context.selected_objects]
        for obj in selected_objects:
            # Skip if object is an armature or in Face collection
            if obj.type == 'ARMATURE' or (obj.users_collection and 'Face' in [c.name for c in obj.users_collection]):
                print(f"Skipping {obj.name} as it is an armature or face mesh")
                continue

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
                    if obj.type == 'MESH':
                        bm = bmesh.new()
                        bm.from_mesh(obj.data)
                        [bm.verts.remove(v) for v in bm.verts]
                        bm.to_mesh(obj.data)
                        obj.data.update()
                        bm.free()
                        print(f"Moved {obj.name} to collection {name} as {ob.name}.")
                        obj.name = obj.name.rsplit("-", 1)[0] + "-KeepEmpty"
                        print(f"{obj.name} maintains custom properties, don't delete.")

                        # Move any existing armature modifiers from the empty to the new mesh
                        for mod in obj.modifiers:
                            if mod.type == 'ARMATURE':
                                new_mod = ob.modifiers.new(name="Armature", type='ARMATURE')
                                new_mod.object = mod.object
                                obj.modifiers.remove(mod)
                    else:
                        print(f"Skipping vertex removal for non-mesh object {obj.name}")

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
        
        # if bpy.app.version >= (4, 2, 0):
        #     bpy.data.scenes["Scene"].view_settings.view_transform = 'Khronos PBR Neutral'

    def import_armature(self, context):
        try:
            # Step 1: Track the original selection
            previously_selected = set(bpy.context.selected_objects)

            # Step 2: Filter out objects in "Face" collection or those with '-KeepEmpty' in their name
            body_objects = [
                obj for obj in previously_selected 
                if obj.type == 'MESH' and not any(col.name == 'Face' for col in obj.users_collection) and '-KeepEmpty' not in obj.name
            ]
            
            # If no valid body objects, raise an error
            if not body_objects:
                raise Exception("No valid body objects selected for armature import")
            
            # Step 3: Select the first body object to use as reference for armature import
            obj = body_objects[0]  
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            
            # Step 4: Import the armature file
            original_selection = set(bpy.context.selected_objects)
            bpy.ops.import_scene.armature_file()
            newly_imported = set(bpy.context.selected_objects) - original_selection
            
            # Step 5: Identify the armature among the imported objects
            armature = next((obj for obj in newly_imported if obj.type == 'ARMATURE'), None)
            if not armature:
                raise Exception("No armature found in imported objects")
            
            # Step 6: Add the armature modifier only to valid meshes
            for obj in previously_selected:
                # Apply armature modifier only if not in Face collection and not '-KeepEmpty'
                if obj.type == 'MESH' and not any(col.name == 'Face' for col in obj.users_collection) and '-KeepEmpty' not in obj.name:
                    # Get base name without file extension and hash
                    obj_base_name = obj.name.split('-')[0].split('=')[0]
                    
                    # Find matching armature by name similarity
                    matching_armature = None
                    for imported_obj in newly_imported:
                        if imported_obj.type == 'ARMATURE':
                            # Convert armature name to match mesh naming pattern
                            armature_base = imported_obj.name.replace('_', '')
                            # Remove any of the special keywords from mesh name
                            mesh_base = obj_base_name
                            for keyword in ['Body', 'Head', 'Extra', 'Dress']:
                                mesh_base = mesh_base.replace(keyword, '')
                            
                            if armature_base.lower().startswith(mesh_base.lower()):
                                matching_armature = imported_obj
                                break
                    
                    if matching_armature:
                        mod = obj.modifiers.new(name="Armature", type='ARMATURE')
                        mod.object = matching_armature

            # Step 7: Restore the selection to include newly imported objects and previously selected objects
            for obj in newly_imported:
                obj.select_set(True)
            for obj in previously_selected:
                if obj not in newly_imported:  
                    obj.select_set(True)
                    
        except Exception as e:
            self.report({'ERROR'}, f"Armature import failed: {str(e)}")
            for obj in previously_selected:
                obj.select_set(True)

                
    def import_face(self, context):
        try:
            previously_selected = set(bpy.context.selected_objects)
            
            if previously_selected:
                obj = list(previously_selected)[0]
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
            
            bpy.ops.import_scene.face_file()
            newly_imported = set(bpy.context.selected_objects) - previously_selected
            
            if not newly_imported:
                raise Exception("No face mesh was found to import")
                
            face_collection = bpy.data.collections.new("Face")
            bpy.context.scene.collection.children.link(face_collection)
            
            # Move all imported meshes to Face collection
            for obj in newly_imported:
                # Remove from current collections
                for col in obj.users_collection:
                    col.objects.unlink(obj)   
                face_collection.objects.link(obj)
                obj.select_set(True)

            # Reselect original objects
            for obj in previously_selected:
                obj.select_set(True)
                
        except Exception as e:
            self.report({'ERROR'}, f"Face import failed: {str(e)}")
            for obj in previously_selected:
                obj.select_set(True)


# Common name mappings and parts used across operators
CHARACTER_NAME_MAPPING = {
    "AratakiItto": "Itto",
    "Arataki": "Itto", 
    "TravelerBoy": "Aether",
    "TravelerMale": "Aether",
    "KamisatoAyaka": "Ayaka",
    "KamisatoAyato": "Ayato",
    "Raiden": "RaidenShogun",
    "Shogun": "RaidenShogun",
    "TravelerGirl": "Lumine",
    "TravelerFemale": "Lumine",
    "SangonomiyaKokomi": "Kokomi",
    "KaedeharaKazuha": "Kazuha",
    "Kaedehara": "Kazuha",
    "Yae": "YaeMiko",
    "FischlSkin": "FischlHighness",
    "NingguangSkin": "NingguangOrchid",
    "MonaGlobal": "Mona",
    "Tartaglia": "Childe",
    "BarbaraSkin": "BarbaraSummertime",
    "DilucSkin": "DilucFlamme",
    "DilucFlames": "DilucFlamme",
    "KiraraSkin": "KiraraBoots",
    "Kujou": "KujouSara",
    "Sara": "KujouSara",
    "Kuki": "Shinobu",
    "KukiShinobu": "Shinobu",
    
    # "FurinaPonytail": "Furina"
}

COMMON_PARTS = ['PonyTail', 'Body', 'Head', 'Arm', 'Leg', 'Dress', 'Extra', 'Extras', 'Hair', 'Mask', 'Idle', 'Eyes', 'Coat', 'JacketHead', 'JacketBody', 'Jacket']


class QuickImportArmature(bpy.types.Operator):
    bl_idname = "import_scene.armature_file"
    bl_label = "Import Armature" 
    bl_description = "Import matching armature file"
    
    def execute(self, context):
        try:
            self.post_import_processing(context)
        except FileNotFoundError as e:
            self.report({'ERROR'}, f"File not found: {str(e)}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}
    
    def post_import_processing(self, context):
        script_dir = os.path.dirname(os.path.realpath(__file__))
        print(f"Script directory: {script_dir}")
        armatures_dir = os.path.join(script_dir, "resources", "armatures")
        print(f"Armatures directory: {armatures_dir}")
        
        if not os.path.exists(armatures_dir):
            raise FileNotFoundError(f"Armatures directory not found at: {armatures_dir}")
        
        selected_objects = context.selected_objects
        if not selected_objects:
            raise Exception("No object selected")
        
        obj_name = selected_objects[0].name.split('-')[0].split('=')[0]
        if not obj_name:
            raise Exception("Invalid object name")
        
        # Sort COMMON_PARTS by length in descending order to match longest parts first
        sorted_parts = sorted(COMMON_PARTS, key=len, reverse=True)
        
        # First try to find any common parts in the name
        base_name = obj_name
        for part in sorted_parts:
            if part.lower() in obj_name.lower():
                # Get everything before the part
                base_name = re.split(part, obj_name, flags=re.IGNORECASE)[0]
                break
        
        # Handle special character name cases
        base_name = CHARACTER_NAME_MAPPING.get(base_name, base_name)
        
        # Don't try to import armature for Face collection
        if base_name == "Face":
            return {'FINISHED'}
        
        if not base_name:
            raise Exception("Could not determine base name")
        
        # Find files that match the base name up until "Armature" and end with .blend
        matching_files = [
            f for f in os.listdir(armatures_dir)
            if f.endswith('.blend') 
            and (armature_idx := f.lower().find('armature')) != -1
            and f[:armature_idx].lower() == base_name.lower()
        ]
        
        if not matching_files:
            raise FileNotFoundError(f"No matching armature file found for {base_name} in {armatures_dir}")
            
        armature_path = os.path.join(armatures_dir, matching_files[0])
            
        with bpy.data.libraries.load(armature_path) as (data_from, data_to):
            armature_objects = [name for name in data_from.objects if 'Armature' in name]
            if not armature_objects:
                raise FileNotFoundError(f"No armature found in file: {armature_path}")
            data_to.objects = armature_objects
      
        for obj in data_to.objects:
            if obj is not None:
                context.scene.collection.objects.link(obj)
                obj.select_set(True)
                
class QuickImportFace(bpy.types.Operator):
    bl_idname = "import_scene.face_file"
    bl_label = "Import Face"
    bl_description = "Import matching face file"
    
    # Special face-specific name mappings
    FACE_NAME_MAPPING = {
        "JeanCN": "Jean",
        "JeanSea": "Jean", 
        "JeanSkin": "Jean",
        "KaeyaSailwind": "Kaeya",
        "KeQingSkin": "Keqing",
        "KeQingOpulent": "Keqing",
        "KeQingOpulentSplendor": "Keqing",
        "ShenheFrostFlower": "Shenhe",
        "ShenheFlower": "Shenhe",
        "NilouBreeze": "Nilou",
        "NilouSkin": "Nilou",
    }
    
    def execute(self, context):
        try:
            self.post_import_processing(context)
        except FileNotFoundError as e:
            self.report({'ERROR'}, f"File not found: {str(e)}")
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}
    
    def post_import_processing(self, context):
        script_dir = os.path.dirname(os.path.realpath(__file__))
        faces_dir = os.path.join(script_dir, "resources", "faces")
        
        if not os.path.exists(faces_dir):
            raise FileNotFoundError(f"Faces directory not found at: {faces_dir}")
        
        selected_objects = context.selected_objects
        if not selected_objects:
            raise Exception("No object selected")
        
        obj_name = selected_objects[0].name.split('-')[0].split('=')[0]
        if not obj_name:
            raise Exception("Invalid object name")
        
        # Sort COMMON_PARTS by length in descending order to match longest parts first
        sorted_parts = sorted(COMMON_PARTS, key=len, reverse=True)
        
        # First try to find any common parts in the name
        base_name = obj_name
        for part in sorted_parts:
            if part.lower() in obj_name.lower():
                # Get everything before the part
                base_name = re.split(part, obj_name, flags=re.IGNORECASE)[0]
                break
        
        # First check face-specific mappings, then fall back to general mappings
        base_name = self.FACE_NAME_MAPPING.get(base_name, CHARACTER_NAME_MAPPING.get(base_name, base_name))
        
        if not base_name:
            raise Exception("Could not determine base name")
        
        matching_files = [f for f in os.listdir(faces_dir) 
                          if base_name.lower() in f.lower() and f.endswith('.blend')]
        
        if not matching_files:
            raise FileNotFoundError(f"No matching face file found for {base_name} in {faces_dir}")
        
        face_path = os.path.join(faces_dir, matching_files[0])
        if not os.path.isfile(face_path):
            raise FileNotFoundError(f"Face file not found at: {face_path}")
            
        with bpy.data.libraries.load(face_path) as (data_from, data_to):
            data_to.objects = [name for name in data_from.objects]
      
        for obj in data_to.objects:
            if obj is not None:
                context.scene.collection.objects.link(obj)
                obj.select_set(True)


class BaseAnalysis(Import3DMigotoFrameAnalysis):
    pass    

class QuickImport(Import3DMigotoFrameAnalysis, QuickImportBase):
    """Setup Character .txt file"""
    bl_idname = "import_scene.3dmigoto_frame_analysis"
    bl_label = "Quick Import for XXMI"
    bl_options = {"UNDO"}

    def execute(self, context):
        cfg = context.scene.quick_import_settings
        super().execute(context)

        folder = os.path.dirname(self.properties.filepath)
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
            importedmeshes = TextureHandler42.create_material(context, texture_files, folder)

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


