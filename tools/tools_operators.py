import bpy  #type: ignore
from bpy.props import PointerProperty, StringProperty, EnumProperty, BoolProperty #type: ignore
from bpy.types import Object, Operator, Panel, PropertyGroup #type: ignore
import numpy as np
# from .quickimport.operators import *



class OBJECT_OT_transfer_properties(bpy.types.Operator):
    bl_idname = "object.transfer_properties"
    bl_label = "Transfer Properties"
    bl_description = "Transfer custom properties and transformation data (location, rotation, scale) from one object to another or between collections."

    def execute(self, context):
        xxmi = context.scene.xxmi_scripts_settings
        mode = xxmi.transfer_mode

        if mode == 'COLLECTION':
            base_collection = xxmi.base_collection
            target_collection = xxmi.target_collection

            if not base_collection or not target_collection:
                self.report({'ERROR'}, 
                    "Invalid Collection(s) selected.\n"
                    "Please make sure you have selected valid collections for both 'Original Properties' and 'Missing Properties' in the panel.")
                return {'CANCELLED'}

            base_prefix_dict = {}
            for base_obj in base_collection.objects:
                prefix = base_obj.name.rsplit("-", 1)[0].rsplit(".", 1)[0]  
                base_prefix_dict[prefix] = base_obj

            for target_obj in target_collection.objects:
                target_prefix = target_obj.name.rsplit("-", 1)[0].rsplit(".", 1)[0]  
                if target_prefix in base_prefix_dict:
                    base_obj = base_prefix_dict[target_prefix]

                    for key in list(target_obj.keys()):
                        if key not in '_RNA_UI':  
                            del target_obj[key]

                    for key in base_obj.keys():
                        target_obj[key] = base_obj[key]
                    target_obj.location = base_obj.location
                    target_obj.rotation_euler = base_obj.rotation_euler
                    target_obj.scale = base_obj.scale  

                    log_message = (
                        f"Transferred properties from '{base_obj.name}' to '{target_obj.name}':\n"
                        f"  Location: {target_obj.location}\n"
                        f"  Rotation: {target_obj.rotation_euler}\n"
                        f"  Scale: {target_obj.scale}"
                    )
                    print(log_message)
                    self.report({'INFO'}, log_message)

            self.report({'INFO'}, "Transfer completed for matching objects in the collections.")

        else:
            base_obj = xxmi.base_objectproperties    
            target_obj = xxmi.target_objectproperties

            if not base_obj or not target_obj:
                self.report({'ERROR'}, 
                    "Invalid Mesh(es) selected.\n"
                    "Please ensure you have selected valid objects for both 'Original Mesh' and 'Modded Mesh' in the panel.")
                return {'CANCELLED'}

            for key in list(target_obj.keys()):
                if key not in '_RNA_UI': 
                    del target_obj[key]

            for key in base_obj.keys():
                target_obj[key] = base_obj[key]

            target_obj.location = base_obj.location
            target_obj.rotation_euler = base_obj.rotation_euler
            target_obj.scale = base_obj.scale  

            log_message = (
                f"Transferred properties from '{base_obj.name}' to '{target_obj.name}':\n"
                f"  Location: {target_obj.location}\n"
                f"  Rotation: {target_obj.rotation_euler}\n"
                f"  Scale: {target_obj.scale}"
            )
            print(log_message)
            self.report({'INFO'}, log_message)

        return {'FINISHED'}
             
# MARK: MERGE VGS
class OBJECT_OT_merge_vertex_groups(bpy.types.Operator):
    bl_idname = "object.merge_vertex_groups"
    bl_label = "Merge Vertex Groups"
    bl_description = "Merge the VG's based on the selected mode"

    def execute(self, context):
        xxmi = context.scene.xxmi_scripts_settings
        mode = xxmi.merge_mode
        vertex_groups = xxmi.vertex_groups
        smallest_group_number = xxmi.smallest_group_number
        largest_group_number = xxmi.largest_group_number

        selected_obj = [obj for obj in bpy.context.selected_objects]
        vgroup_names = []

        if mode == 'MODE1':
            vgroup_names = [vg.strip() for vg in vertex_groups.split(",")]
        elif mode == 'MODE2':
            vgroup_names = [str(i) for i in range(smallest_group_number, largest_group_number + 1)]
        elif mode == 'MODE3':
            vgroup_names = list(set(x.name.rsplit('.',1)[0] for y in selected_obj for x in y.vertex_groups))
        else:
            self.report({'ERROR'}, "Mode not recognized, exiting")
            return {'CANCELLED'}

        if not vgroup_names:
            self.report({'ERROR'}, "No vertex groups found, please double check an object is selected and required data has been entered")
            return {'CANCELLED'}

        for cur_obj in selected_obj:
            for vname in vgroup_names:
                relevant = [x.name for x in cur_obj.vertex_groups if x.name.rsplit('.',1)[0] == vname]

                if relevant:
                    vgroup = cur_obj.vertex_groups.new(name=f"x{vname}")

                    for vert_id, vert in enumerate(cur_obj.data.vertices):
                        available_groups = [v_group_elem.group for v_group_elem in vert.groups]

                        combined = 0
                        for vg_name in relevant:
                            vg_index = cur_obj.vertex_groups[vg_name].index
                            if vg_index in available_groups:
                                combined += cur_obj.vertex_groups[vg_name].weight(vert_id)

                        if combined > 0:
                            vgroup.add([vert_id], combined, 'ADD')

                    for vg_name in relevant:
                        cur_obj.vertex_groups.remove(cur_obj.vertex_groups[vg_name])
                    vgroup.name = vname

            bpy.context.view_layer.objects.active = cur_obj
            bpy.ops.object.vertex_group_sort()

        return {'FINISHED'}

class XXMI_TOOLS_OT_remove_all_vgs(bpy.types.Operator):
    bl_label = "Remove All VG's"
    bl_idname = "xxmi_tools.remove_all_vgs"
   

    def execute(self, context):
        selected_object = bpy.context.active_object

        if selected_object and selected_object.type == 'MESH':
            for group in selected_object.vertex_groups:
                selected_object.vertex_groups.remove(group)

        return {'FINISHED'}

class XXMI_TOOLS_OT_fill_vgs(bpy.types.Operator):
    bl_label = "Fill Vertex Groups"
    bl_idname = "xxmi_tools.fill_vgs"
    bl_description = "Fill the VG's based on Largest input and sort the VG's for all selected mesh objects"

    def execute(self, context):
        largest = context.scene.xxmi_scripts_settings.Largest_VG
        selected_objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']

        if not selected_objects:
            self.report({'ERROR'}, "No mesh objects selected")
            return {'CANCELLED'}

        for ob in selected_objects:
            ob.update_from_editmode()

            for vg in ob.vertex_groups:
                try:
                    if int(vg.name.rsplit(".",1)[0]) > largest:
                        largest = int(vg.name.rsplit(".",1)[0])
                except ValueError:
                    print(f"Vertex group '{vg.name}' not named as integer, skipping")

            missing = set([f"{i}" for i in range(largest + 1)]) - set([x.name.split(".")[0] for x in ob.vertex_groups])
            for number in missing:
                ob.vertex_groups.new(name=f"{number}")

            bpy.context.view_layer.objects.active = ob
            bpy.ops.object.vertex_group_sort()

        self.report({'INFO'}, f"Filled and sorted vertex groups for {len(selected_objects)} objects")
        return {'FINISHED'}

class XXMI_TOOLS_OT_remove_unused_vgs(bpy.types.Operator):
    bl_label = "Remove Unused VG's"
    bl_idname = "xxmi_tools.remove_unused_vgs"
    bl_description = "Remove all Empty VG's"

    def execute(self, context):
        if bpy.context.active_object:
            ob = bpy.context.active_object
            ob.update_from_editmode()

            vgroup_used = {i: False for i, k in enumerate(ob.vertex_groups)}

            for v in ob.data.vertices:
                for g in v.groups:
                    if g.weight > 0.0:
                        vgroup_used[g.group] = True

            for i, used in sorted(vgroup_used.items(), reverse=True):
                if not used:
                    ob.vertex_groups.remove(ob.vertex_groups[i])

            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "No objects selected")
            return {'CANCELLED'}
        
class OBJECT_OT_vertex_group_remap(bpy.types.Operator):
    bl_idname = "object.vertex_group_remap"
    bl_label = "Vertex Group Remap"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Remap the vertex groups between two selected objects"

    def execute(self, context):
        xxmi = context.scene.xxmi_scripts_settings
        source = xxmi.vgm_source_object
        destination = xxmi.vgm_destination_object

        if not source or not destination:
            self.report({'ERROR'}, "Please, Select Source and Target object")
            return {'CANCELLED'}

        source_object = bpy.data.objects.get(source.name)
        destination_object = bpy.data.objects.get(destination.name)

        if not source_object or not destination_object:
            self.report({'ERROR'}, "Please, Select Source and Target object")
            return {'CANCELLED'}

   
        match_vertex_groups(source_object, destination_object)
        self.report({'INFO'}, "Vertex groups matched.")
        

        if destination_object and destination_object.type == 'MESH' and destination_object.vertex_groups:
            vertex_group_names = [vg.name for vg in destination_object.vertex_groups]
            print("Remapped VG's:", ", ".join(vertex_group_names))
        else:
            print("No vertex groups found in the target object.")

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.objects.active = destination_object
        destination_object.select_set(True)

        return {'FINISHED'}

def calculate_vertex_influence_area(obj):
    vertex_area = np.zeros(len(obj.data.vertices))

    for face in obj.data.polygons:
        area_per_vertex = face.area / len(face.vertices)
        for vert_idx in face.vertices:
            vertex_area[vert_idx] += area_per_vertex

    return vertex_area

def get_all_weighted_centers(obj):
    vertex_influence_area = calculate_vertex_influence_area(obj)
    matrix_world = np.array(obj.matrix_world)

    def to_homogeneous(coord):
        return (coord.x, coord.y, coord.z, 1.0)

    vertex_coords = np.array([matrix_world @ to_homogeneous(vertex.co) for vertex in obj.data.vertices])[:, :3]
    num_vertices = len(obj.data.vertices)
    num_groups = len(obj.vertex_groups)

    weights = np.zeros((num_vertices, num_groups))
    for vertex in obj.data.vertices:
        for group in vertex.groups:
            weights[vertex.index, group.group] = group.weight

    weighted_areas = weights * vertex_influence_area[:, np.newaxis]
    total_weight_areas = weighted_areas.sum(axis=0)

    centers = {}
    for i, vgroup in enumerate(obj.vertex_groups):
        total_weight_area = total_weight_areas[i]
        if total_weight_area > 0:
            weighted_position_sum = (weighted_areas[:, i][:, np.newaxis] * vertex_coords).sum(axis=0)
            center = weighted_position_sum / total_weight_area
            centers[vgroup.name] = tuple(center)
            print(f"Center for {vgroup.name}: {center}")
        else:
            centers[vgroup.name] = None
            print(f"No weighted center for {vgroup.name}")

    return centers

def find_nearest_center(base_centers, target_center):
    best_match = None
    best_distance = float('inf')
    target_center = np.array(target_center)
    for base_group_name, base_center in base_centers.items():
        if base_center is None:
            continue
        base_center = np.array(base_center)
        distance = np.linalg.norm(target_center - base_center)
        if distance < best_distance:
            best_distance = distance
            best_match = base_group_name
    return best_match

def match_vertex_groups(source_obj, target_obj):
    for target_group in target_obj.vertex_groups:
        target_group.name = "unknown"
    source_centers = get_all_weighted_centers(source_obj)
    target_centers = get_all_weighted_centers(target_obj)

    for target_group in target_obj.vertex_groups:
        target_center = target_centers.get(target_group.name)
        if target_center is None:
            continue

        best_match = find_nearest_center(source_centers, target_center)

        if best_match:
            target_group.name = best_match
            print(f"Target group {target_group.index} renamed to {best_match}")
    
    
class OBJECT_OT_separate_by_material_and_rename(bpy.types.Operator):
    """Separate by Material and Rename"""
    bl_idname = "object.separate_by_material_and_rename"
    bl_label = "Separate by Material and Rename"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='MATERIAL')
        bpy.ops.object.mode_set(mode='OBJECT')


        for o in bpy.context.selected_objects:
            material_name = o.active_material.name.replace("mat_", "")
            material_name = material_name.replace("Diffuse", "").strip()
            o.name = material_name

        return {'FINISHED'}
    
    def invoke(self, context, event):
        if event.type == 'P':
            return context.window_manager.invoke_props_dialog(self)
        else:
            return self.execute(context)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Want to proceed?")

def menu_func(self, context):
    self.layout.operator(OBJECT_OT_separate_by_material_and_rename.bl_idname)
    
classes = [
    XXMI_TOOLS_OT_fill_vgs,
    XXMI_TOOLS_OT_remove_unused_vgs,
    XXMI_TOOLS_OT_remove_all_vgs,
    OBJECT_OT_transfer_properties,
    OBJECT_OT_vertex_group_remap,
    OBJECT_OT_merge_vertex_groups,
    OBJECT_OT_separate_by_material_and_rename,
]