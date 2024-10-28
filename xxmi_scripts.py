 
import bpy #type: ignore
from . import bl_info
from bpy.props import PointerProperty, StringProperty, EnumProperty, BoolProperty #type: ignore 
from .tools.tools_operators import *

class XXMI_TOOLS_PT_main_panel(bpy.types.Panel):
    bl_label = "ToolsXXMI"
    bl_idname = "XXMI_TOOLS_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XXMI Scripts'
    
    def draw(self, context):
        layout = self.layout
        xxmi = context.scene.xxmi_scripts_settings
        

        # GitHub link button and version info
        box = layout.box()
        github_row = box.row(align=True)
        github_row.label(text=f"XXMI Scripts | Current Version: v{'.'.join(map(str, bl_info['version']))}", icon='INFO')
        github_row.alignment = 'EXPAND'
        github_row.operator("wm.url_open", text="", icon='URL', emboss=False).url = "https://github.com/Seris0/Gustav0/tree/main/Addons/QuickImportXXMI"

        # Main Tools Section
        box = layout.box()
        row = box.row()
        row.prop(xxmi, "show_vertex", icon="TRIA_DOWN" if xxmi.show_vertex else "TRIA_RIGHT", emboss=False, text="Main Tools")
        if xxmi.show_vertex:
            col = box.column(align=True)
            col.label(text="Vertex Groups", icon='GROUP_VERTEX')
            col.prop(xxmi, "Largest_VG", text="Largest VG")
            col.operator("XXMI_TOOLS.fill_vgs", text="Fill Vertex Groups", icon='ADD')
            col.operator("XXMI_TOOLS.remove_unused_vgs", text="Remove Unused VG's", icon='X')
            col.operator("XXMI_TOOLS.remove_all_vgs", text="Remove All VG's", icon='CANCEL')
            col.operator("object.separate_by_material_and_rename", text="Separate by Material", icon='MATERIAL')

            col.separator()
            col.label(text="Merge Vertex Groups", icon='AUTOMERGE_ON')
            col.prop(xxmi, "merge_mode", text="")
            if xxmi.merge_mode == 'MODE1':
                col.prop(xxmi, "vertex_groups", text="Vertex Groups")
            elif xxmi.merge_mode == 'MODE2':
                row = col.row(align=True)
                row.prop(xxmi, "smallest_group_number", text="From")
                row.prop(xxmi, "largest_group_number", text="To")
            col.operator("object.merge_vertex_groups", text="Merge Vertex Groups")

        # Vertex Group REMAP Section
        box = layout.box()
        row = box.row()
        row.prop(xxmi, "show_remap", icon="TRIA_DOWN" if xxmi.show_remap else "TRIA_RIGHT", emboss=False, text="Vertex Group REMAP")
        if xxmi.show_remap:
            col = box.column(align=True)
            col.prop_search(xxmi, "vgm_source_object", bpy.data, "objects", text="Source")
            col.separator()
            col.prop_search(xxmi, "vgm_destination_object", bpy.data, "objects", text="Target")
            col.separator()
            col.operator("object.vertex_group_remap", text="Run Remap", icon='FILE_REFRESH')

        # Transfer Properties Section
        box = layout.box()
        box.prop(xxmi, "show_transfer", icon="TRIA_DOWN" if xxmi.show_transfer else "TRIA_RIGHT", emboss=False, text="Transfer Properties")
        if xxmi.show_transfer:
            box.label(text="Transfer Properties", icon='OUTLINER_OB_GROUP_INSTANCE')  
            row = box.row()
            row.prop(xxmi, "transfer_mode", text="Transfer Mode")
            if xxmi.transfer_mode == 'COLLECTION':
                row = box.row()
                row.prop_search(xxmi, "base_collection", bpy.data, "collections", text="Original Properties:")
                row = box.row()
                row.prop_search(xxmi, "target_collection", bpy.data, "collections", text="Missing Properties:")
            else:
                row = box.row()
                row.prop_search(xxmi, "base_objectproperties", bpy.data, "objects", text="Original Mesh:")
                row = box.row()
                row.prop_search(xxmi, "target_objectproperties", bpy.data, "objects", text="Modded Mesh:")
            row = box.row()
            row.operator("object.transfer_properties", text="Transfer Properties", icon='OUTLINER_OB_GROUP_INSTANCE')

class XXMI_Scripts_Settings(bpy.types.PropertyGroup):
    show_vertex: bpy.props.BoolProperty(name="Show Vertex", default=False) #type: ignore        
    show_remap: bpy.props.BoolProperty(name="Show Remap", default=False) #type: ignore
    show_transfer: bpy.props.BoolProperty(name="Show Transfer", default=False) #type: ignore
    base_collection: bpy.props.PointerProperty(type=bpy.types.Collection, description="Base Collection") #type: ignore
    target_collection: bpy.props.PointerProperty(type=bpy.types.Collection, description="Target Collection") #type: ignore
    base_objectproperties: bpy.props.PointerProperty(type=bpy.types.Object, description="Base Object") #type: ignore
    target_objectproperties: bpy.props.PointerProperty(type=bpy.types.Object, description="Target Object") #type: ignore    
    transfer_mode: bpy.props.EnumProperty(
        items=[
            ('COLLECTION', 'Collection Transfer', 'Transfer properties between collections'),
            ('MESH', 'Mesh Transfer', 'Transfer properties between meshes')
        ],
        default='MESH',
        description="Mode of Transfer"
    ) #type: ignore
    Largest_VG: bpy.props.IntProperty(description="Value for Largest Vertex Group") #type: ignore
    vgm_source_object: bpy.props.PointerProperty(type=bpy.types.Object, description="Source Object for Vertex Group Mapping") #type: ignore
    vgm_destination_object: bpy.props.PointerProperty(type=bpy.types.Object, description="Destination Object for Vertex Group Mapping") #type: ignore   
    merge_mode: bpy.props.EnumProperty(items=[
        ('MODE1', 'Mode 1: Single VG', 'Merge based on specific vertex groups'),
        ('MODE2', 'Mode 2: By Range ', 'Merge based on a range of vertex groups'),
        ('MODE3', 'Mode 3: All VG', 'Merge all vertex groups')], #type: ignore
        default='MODE3')
    vertex_groups: bpy.props.StringProperty(name="Vertex Groups", default="") #type: ignore
    smallest_group_number: bpy.props.IntProperty(name="Smallest Group", default=0) #type: ignore
    largest_group_number: bpy.props.IntProperty(name="Largest Group", default=999) #type: ignore

class QuickImportSettings(bpy.types.PropertyGroup):
    tri_to_quads: BoolProperty(
        name="Tri to Quads",
        default=False,
        description="Enable Tri to Quads"
    )#type: ignore 
    merge_by_distance: BoolProperty(
        name="Merge by Distance",
        default=False,
        description="Enable Merge by Distance"
    )#type: ignore 
    reset_rotation: BoolProperty(
        name="Reset Rotation (ZZZ)",
        default=False,
        description="Reset the rotation of the object upon import"
    ) #type: ignore 
    import_textures: BoolProperty(
        name="Import Textures",
        default=True,
        description="Apply Materials and Textures"
    ) #type: ignore
    hide_textures: BoolProperty(
        name="Hide Textures",
        default=False,
        description="Hide Textures"
    ) #type: ignore
    
    def update_collection_settings(self, context):
        if self.create_mesh_collection:
            self.create_collection = False
        elif self.create_collection:
            self.create_mesh_collection = False
        
    def update_create_collection(self, context):
        if self.create_collection:
            self.create_mesh_collection = False

    def update_create_mesh_collection(self, context):
        if self.create_mesh_collection:
            self.create_collection = False

    create_collection: BoolProperty(
        name="Create Collection",
        default=True,
        description="Create a new collection based on the folder name",
        update=update_create_collection
    ) #type: ignore
    create_mesh_collection: BoolProperty(
        name="Create Mesh Collection",
        default=False,
        description="Create a new collection for mesh data and custom properties",
        update=update_create_mesh_collection
    ) #type: ignore
    import_diffuse: BoolProperty(
        name="Diffuse",
        default=True,
        description="Import Diffuse Maps"
    ) #type: ignore 
    import_lightmap: BoolProperty(
        name="LightMap",
        default=False,
        description="Import LightMaps"
    ) #type: ignore 
    import_normalmap: BoolProperty(
        name="NormalMap",
        default=False,
        description="Import NormalMaps"
    ) #type: ignore 
    import_materialmap: BoolProperty(
        name="MaterialMap",
        default=False,
        description="Import MaterialMaps"
    ) #type: ignore 
    import_stockingmap: BoolProperty(
        name="StockingMap",
        default=False,
        description="Import StockingMaps"
    )  # type: ignore
    # game: EnumProperty(
    #     name="Game",
    #     items=[
    #         ('GI', 'Genshin Impact', 'Genshin Impact'),
    #         ('HSR', 'Honkai Star Rail', 'Honkai Star Rail'),
    #         ('ZZZ', 'Zenless Zone Zero', 'Zenless Zone Zero')
    #     ],
    #     description="Select the game type"

class XXMI_TOOLS_PT_quick_import_panel(bpy.types.Panel):
    bl_label = "QuickImportXXMI"
    bl_idname = "XXMI_TOOLS_PT_QuickImportPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'XXMI Scripts'
 
    def draw(self, context):
        layout = self.layout
        cfg = context.scene.quick_import_settings

        box = layout.box()
        col = box.column(align=True)
        
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator("import_scene.3dmigoto_frame_analysis", text="Setup Character", icon='IMPORT')
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator("import_scene.3dmigoto_raw", text="Setup Character Raw (ib + vb)", icon='IMPORT')
        
        col.separator()
        col.label(text="Import Options:", icon='SETTINGS')
        row = col.row(align=True)
        row.prop(cfg, "import_textures", toggle=True)
        row.prop(cfg, "merge_by_distance", toggle=True)
        
        row = col.row(align=True)
        row.prop(cfg, "reset_rotation", toggle=True)
        row.prop(cfg, "tri_to_quads", toggle=True)
        
        col.prop(cfg, "create_collection", toggle=True)
        col.prop(cfg, "create_mesh_collection", toggle=True)

        if cfg.import_textures:
            col.separator()
            row = col.row(align=True)
            row.label(text="Texture Import:", icon='TEXTURE')
            row.prop(cfg, "hide_textures", text="Show Texture Options" if cfg.hide_textures else "Hide Texture Options", icon='HIDE_OFF' if cfg.hide_textures else 'HIDE_ON', toggle=True)

            if cfg.hide_textures:
                row = col.row(align=True)
                row.prop(cfg, "import_diffuse", toggle=True)
                row = col.row(align=True)
                row.prop(cfg, "import_lightmap", toggle=True)
                row.prop(cfg, "import_normalmap", toggle=True)
                row = col.row(align=True)
                row.prop(cfg, "import_materialmap", toggle=True)
                # if cfg.game == 'HSR':
                row.prop(cfg, "import_stockingmap", toggle=True)
                col.separator()

        col.separator()
        row = col.row(align=True)
        row.scale_y = 1.2
        row.operator("quickimport.save_preferences", icon='FILE_TICK')
        # col.separator()
        # col.prop(cfg, "game")