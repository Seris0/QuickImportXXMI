
import bpy #type: ignore
import os
if bpy.app.version < (4, 2, 0):
    from blender_dds_addon import import_dds #type: ignore


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
            
            if context.window_manager.quick_import_settings.import_textures:
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
            if bpy.app.version < (4, 0):
                bsdf.inputs[5].default_value = 0.0
            else:
                bsdf.inputs[5].default_value = (0.5, 0.5, 0.5)

            # Link nodes
            material.node_tree.links.new(texImage.outputs[0], bsdf.inputs[0])
            material.node_tree.links.new(bsdf.outputs[0], material_output.inputs[0])
        else:
            # For LightMap, NormalMap, StockingMap, and MaterialMap, just add a Material Output node
            material_output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")

        return material.name

class TextureHandler42:
    @staticmethod
    def create_material(context, files, path):
        importedmeshes = []
        for file in files:
            mesh_name = bpy.path.display_name_from_filepath(os.path.join(path, file))
            mesh_name = mesh_name[:-7]

            material_name = "mat_" + mesh_name
            mat = TextureHandler42.setup_texture(material_name, os.path.join(path, file))

            for obj in bpy.data.objects:
                if obj.name.startswith(mesh_name):
                    obj.data.materials.append(bpy.data.materials.get(mat))
                    importedmeshes.append(obj)

        return importedmeshes
    
    @staticmethod
    def setup_texture(name, texture_path):
        """Creates a new material using that texture as base color, also sets alpha to none"""
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        bsdf = material.node_tree.nodes["Principled BSDF"]
        bsdf.inputs[0].default_value = (1, 1, 1, 1)
        bsdf.inputs[5].default_value = (0.5, 0.5, 0.5)
        texImage = material.node_tree.nodes.new("ShaderNodeTexImage")

        try:
            image = bpy.data.images.load(texture_path)
            texImage.image = image
            if image:
                texImage.image.alpha_mode = "NONE"
                texImage.image.colorspace_settings.name = 'sRGB'
                material.node_tree.links.new(texImage.outputs[0], bsdf.inputs[0])
        except Exception as e:
            print(f"Error loading image {texture_path}: {e}")
        
        return material.name