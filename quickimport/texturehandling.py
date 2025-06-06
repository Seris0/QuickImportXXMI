
import bpy #type: ignore
import os
if bpy.app.version < (4, 2, 0):
    try:
        from blender_dds_addon import import_dds #type: ignore
    except ImportError:
        raise ImportError("The Blender DDS Addon is required for Blender 3.6. Please install it from: https://github.com/matyalatte/Blender-DDS-Addon")


class TextureHandler:
    @staticmethod
    def convert_dds(context, file):
        """Import a file."""
        dds_options = context.scene.dds_options
        tex = import_dds.load_dds(
            file,
            invert_normals=dds_options.invert_normals,
            cubemap_layout=dds_options.cubemap_layout,
        )
        return tex

    @staticmethod
    def create_material(context, files, path):
        importedmeshes = set()
        texture_types = ["Diffuse", "LightMap", "NormalMap", "StockingMap", "MaterialMap", "Skill", "idle", "Back"]
        materials_cache = {}
        
        # Sort files to ensure Diffuse > LightMap > NormalMap order
        sorted_files = sorted(files, key=lambda f: (
            "Diffuse" not in f,
            "LightMap" not in f,
            "NormalMap" not in f,
            "StockingMap" not in f,
            "MaterialMap" not in f,
            "Skill" not in f,
            "DiffuseUlt" not in f,
            "idle" not in f,
            "Back" not in f
        ))
        
        for file in sorted_files:
            file_name, ext = os.path.splitext(file)
            texture_type = next((t for t in texture_types if t in file_name), None)
            
            if texture_type is None:
                print(f"Skipping {file} as it does not match known texture types.")
                continue
            
            mesh_name = file_name[:-len(texture_type)]
            
            if context.scene.quick_import_settings.import_textures:
                TextureHandler.convert_dds(context, file=os.path.join(path, file))
                
                material_name = f"mat_{mesh_name}_{texture_type}"
                if material_name not in materials_cache:
                    materials_cache[material_name] = TextureHandler.setup_texture(material_name, file, texture_type)
                
                for obj in bpy.data.objects:
                    if obj.name.startswith(mesh_name):
                        mat = bpy.data.materials.get(materials_cache[material_name])
                        if mat and mat.name not in [m.name for m in obj.data.materials]:
                            obj.data.materials.append(mat)
                            importedmeshes.add(obj)
                            print(f"Assigned material {mat.name} to {obj.name}")
            else:
                print(f"Skipping texture import for {file} as import_textures is disabled.")

        return list(importedmeshes)

    @staticmethod
    def setup_texture(name, texture_name, texture_type):
        """Creates a new material using that texture as base color, also sets alpha to none."""
        material = bpy.data.materials.new(name)
        material.use_nodes = True

        # Remove default nodes
        material.node_tree.nodes.clear()

        # Add Image Texture node
        texImage = material.node_tree.nodes.new("ShaderNodeTexImage")
        texture_name = texture_name[:-4]  # Remove file extension
        texImage.image = bpy.data.images.get(texture_name)
        if texImage.image:
            texImage.image.alpha_mode = "NONE"
            texImage.image.colorspace_settings.name = 'sRGB'

        # For Diffuse textures, set up BSDF
        if texture_type == "Diffuse":
            bsdf = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            material_output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")

            # Set up BSDF properties
            bsdf.inputs[0].default_value = (1, 1, 1, 1)
            bsdf.inputs[5].default_value = 0.0
            #Well Sins like Roughness 1.0, so why not teriderp
            bsdf.inputs[9].default_value = 1.0
            # Position nodes
            texImage.location = (-300, 0)
            bsdf.location = (0, 0) 
            material_output.location = (300, 0)

            # Link nodes
            material.node_tree.links.new(texImage.outputs[0], bsdf.inputs[0])
            material.node_tree.links.new(bsdf.outputs[0], material_output.inputs[0])
        else:
            # For LightMap, NormalMap, StockingMap, and MaterialMap, just add a Material Output node
            material_output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")

        return material.name


#TODO: MERGE BOTH CLASSES INTO ONE, AND KEEP THE DDS CONVERSION ONLY FOR 3.6
class TextureHandler42:
    @staticmethod
    def create_material(context, files, path):
        importedmeshes = set()
        texture_types = ["Diffuse", "LightMap", "NormalMap", "StockingMap", "MaterialMap", "Skill", "idle", "Back"]
        materials_cache = {}
        
        # Sort files to ensure Diffuse > LightMap > NormalMap order
        sorted_files = sorted(files, key=lambda f: (
            "Diffuse" not in f,
            "LightMap" not in f,
            "NormalMap" not in f,
            "StockingMap" not in f,
            "MaterialMap" not in f,
            "Skill" not in f,
            "DiffuseUlt" not in f,
            "idle" not in f,
            "Back" not in f
        ))
        
        for file in sorted_files:
            file_name, ext = os.path.splitext(file)
            texture_type = next((t for t in texture_types if t in file_name), None)
            
            if texture_type is None:
                print(f"Skipping {file} as it does not match known texture types.")
                continue
            
            mesh_name = file_name[:-len(texture_type)]
            material_name = f"mat_{mesh_name}_{texture_type}"
            
            if material_name not in materials_cache:
                materials_cache[material_name] = TextureHandler42.setup_texture(material_name, os.path.join(path, file), texture_type)
            
                for obj in bpy.data.objects:
                    if obj.name.startswith(mesh_name):
                        mat = bpy.data.materials.get(materials_cache[material_name])
                        if mat and mat.name not in [m.name for m in obj.data.materials]:
                            obj.data.materials.append(mat)
                            importedmeshes.add(obj)
                            print(f"Assigned material {mat.name} to {obj.name}")

        return list(importedmeshes)
    
    @staticmethod
    def setup_texture(name, texture_path, texture_type):
        """Creates a new material using that texture as base color, also sets alpha to none"""
        material = bpy.data.materials.new(name)
        material.use_nodes = True

        # Remove default nodes
        material.node_tree.nodes.clear()

        # Add Image Texture node
        texImage = material.node_tree.nodes.new("ShaderNodeTexImage")
        texImage.image = bpy.data.images.load(texture_path)
        if texImage.image:
            texImage.image.alpha_mode = "NONE"
            texImage.image.colorspace_settings.name = 'sRGB'

        # For Diffuse textures, set up BSDF
        if texture_type == "Diffuse":
            bsdf = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            material_output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
            bsdf.inputs[0].default_value = (1, 1, 1, 1)
            bsdf.inputs[5].default_value = (0.5, 0.5, 0.5)

            bsdf.inputs[2].default_value = (1.0)
            bsdf.inputs[3].default_value = (1.0)
            
                        # Position nodes
            texImage.location = (-300, 0)
            bsdf.location = (0, 0) 
            material_output.location = (300, 0)

            # Link nodes
            material.node_tree.links.new(texImage.outputs[0], bsdf.inputs[0])
            material.node_tree.links.new(bsdf.outputs[0], material_output.inputs[0])
        else:
            # For LightMap, NormalMap, StockingMap, and MaterialMap, just add a Material Output node
            material_output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")

        return material.name