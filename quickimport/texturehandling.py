
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
        importedmeshes = []
        for file in files:
            mesh_name = bpy.path.display_name_from_filepath(os.path.join(path, file))
            mesh_name = mesh_name[:-7]

            if context.scene.quick_import_settings.import_textures:
                TextureHandler.convert_dds(context, file=os.path.join(path, file))

                material_name = "mat_" + mesh_name
                mat = TextureHandler.setup_texture(material_name, file)

             
                for obj in bpy.data.objects:
                    print(f"Checking {obj.name} against {mesh_name}")
                    if obj.name.startswith(mesh_name):
              
                        print(f"FOUND! Assigning material {mat} to {obj.name}")
                        obj.data.materials.append(bpy.data.materials.get(mat))
                        importedmeshes.append(obj)
            else:
                print(f"Skipping texture import for {file} as import_textures is disabled.")

        return importedmeshes
    
    @staticmethod
    def setup_texture(name, texture_name):
        """Creates a new material using that texture as base color, also sets alpha to none"""
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        bsdf = material.node_tree.nodes["Principled BSDF"]
        bsdf.inputs[0].default_value = (1, 1, 1, 1)
        if bpy.app.version < (4, 0):
            bsdf.inputs[5].default_value = 0.0
        else:
            bsdf.inputs[5].default_value = (0.5, 0.5, 0.5)
        texImage = material.node_tree.nodes.new("ShaderNodeTexImage")
        texture_name = texture_name[:-4]
        texImage.image = bpy.data.images.get(texture_name)
        if texImage.image:
            texImage.image.alpha_mode = "NONE"
            texImage.image.colorspace_settings.name = 'sRGB'
        material.node_tree.links.new(texImage.outputs[0], bsdf.inputs[0])
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