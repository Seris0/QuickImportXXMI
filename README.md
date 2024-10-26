# XXMI Tool Quick Import

## Overview
The script `QuickImport` is a tool for Blender that facilitates quick importing of models and textures, adjusts vertices and vertex groups, and organizes objects into collections. This script includes specific functionalities for handling DDS files and organizing materials in Blender.

## Classes

### `QuickImportSettings`
This class defines configurable properties for quick import, including:

- `tri_to_quads`: Convert triangles to quads.
- `merge_by_distance`: Merge vertices by distance.
- `reset_rotation`: Reset object rotation after import.
- `apply_textures`: Apply materials and textures.
- `create_collection`: Create a new collection based on the folder name.
- `create_mesh_collection`: Setup for toggles 

### `TextureHandler`
This class handles creating materials and importing textures:

- `new_material(name, texture_name)`: Creates a new material using a texture as a base.
- `import_dafile(context, file)`: Imports a DDS file as TGA.
- `import_files(context, files, path)`: handle the textures files and applies the corresponding materials to objects in Blender.

### `GIMI_TOOLS_PT_quick_import_panel`
A panel in the Blender UI to access quick import settings.

### `QuickImport`
This class extends `Import3DMigotoFrameAnalysis` to perform quick import and organize imported objects into collections.

### `QuickImportSettings`

This class holds the import settings for different types of textures.

#### Attributes
- `import_diffuse`: BooleanProperty for importing Diffuse textures.
- `import_lightmap`: BooleanProperty for importing LightMap textures.
- `import_normalmap`: BooleanProperty for importing NormalMap textures.
- `import_stockingmap`: BooleanProperty for importing StockingMap textures.

#### Methods
- `import_textures(self, context)`: Main method to import textures based on the settings.
- `create_material(self, mesh_name, texture_type, texture_path)`: Creates and assigns a new material with the imported texture to a mesh.
- `process_diffuse(self, mesh_name, texture_path)`: Processes and assigns a Diffuse texture.
- `process_lightmap(self, mesh_name, texture_path)`: Processes and assigns a LightMap texture.
- `process_normalmap(self, mesh_name, texture_path)`: Processes and assigns a NormalMap texture.

## How to Use
1. Enable the addon through Blender preferences.
2. Use the `Quick Import` panel in the `XXMI Scripts` tab to configure and execute the quick import.

## Authors
- Gustav0
- LeoTorreZ

## Acknowledgements
Special thanks to Silent for providing various scripts and 3D frame analyses, and LeoTools for QuickImport.

---

**Note:** This README.md file is a basic summary of the functionalities and classes found in the script. It is recommended to explore the code for a more detailed understanding of each function and class.

