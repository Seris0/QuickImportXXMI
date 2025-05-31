from glob import glob
import re
import itertools
import os
import time
import bpy #type: ignore
from bpy_extras.io_utils import  ImportHelper, ExportHelper, orientation_helper #type: ignore
from bpy.props import BoolProperty, StringProperty, CollectionProperty, IntProperty #type: ignore
from .datahandling import load_3dmigoto_mesh, open_frame_analysis_log_file, find_stream_output_vertex_buffers, VBSOMapEntry, ImportPaths, Fatal, import_3dmigoto, import_3dmigoto_raw_buffers

IOOBJOrientationHelper = type('DummyIOOBJOrientationHelper', (object,), {})

class ClearSemanticRemapList(bpy.types.Operator):
    """Clear the semantic remap list"""
    bl_idname = "import_mesh.migoto_semantic_remap_clear"
    bl_label = "Clear list"

    def execute(self, context):
        import_operator = context.space_data.active_operator
        import_operator.properties.semantic_remap.clear()
        return {'FINISHED'}

class PrefillSemanticRemapList(bpy.types.Operator):
    """Add semantics from the selected files to the semantic remap list"""
    bl_idname = "import_mesh.migoto_semantic_remap_prefill"
    bl_label = "Prefill from selected files"

    def execute(self, context):
        import_operator = context.space_data.active_operator
        semantic_remap_list = import_operator.properties.semantic_remap
        semantics_in_list = { x.semantic_from for x in semantic_remap_list }

        paths = import_operator.get_vb_ib_paths(load_related=False)

        for p in paths:
            vb, ib, name, pose_path = load_3dmigoto_mesh(import_operator, [p])
            valid_semantics = vb.get_valid_semantics()
            for semantic in vb.layout:
                if semantic.name not in semantics_in_list:
                    remap = semantic_remap_list.add()
                    remap.semantic_from = semantic.name
                    # Store some extra information that can be helpful to guess the likely semantic:
                    remap.Format = semantic.Format
                    remap.InputSlot = semantic.InputSlot
                    remap.InputSlotClass = semantic.InputSlotClass
                    remap.AlignedByteOffset = semantic.AlignedByteOffset
                    remap.valid = semantic.name in valid_semantics
                    remap.update_tooltip()
                    semantics_in_list.add(semantic.name)

        return {'FINISHED'}

@orientation_helper(axis_forward='-Z', axis_up='Y')
class QuickImportXXMIFrameAnalysis(bpy.types.Operator, ImportHelper, IOOBJOrientationHelper):
    """Import a mesh dumped with 3DMigoto's frame analysis"""
    bl_idname = "import_mesh.quickimportxxmi_frame_analysis"
    bl_label = "Import 3DMigoto Frame Analysis Dump"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = '.txt'
    filter_glob: StringProperty(
            default='*.txt',
            options={'HIDDEN'},
            ) #type: ignore

    files: CollectionProperty(
            name="File Path",
            type=bpy.types.OperatorFileListElement,
            ) #type: ignore

    flip_texcoord_v: BoolProperty(
            name="Flip TEXCOORD V",
            description="Flip TEXCOORD V asix during importing",
            default=True,
            ) #type: ignore

    flip_winding: BoolProperty(
            name="Flip Winding Order",
            description="Flip winding order (face orientation) during importing. Try if the model doesn't seem to be shading as expected in Blender and enabling the 'Face Orientation' overlay shows **RED** (if it shows BLUE, try 'Flip Normal' instead). Not quite the same as flipping normals within Blender as this only reverses the winding order without flipping the normals. Recommended for Unreal Engine",
            default=False,
            ) #type: ignore
    
    flip_mesh: BoolProperty(
            name="Flip Mesh",
            description="Mirrors mesh over the X Axis on import, and invert the winding order.",
            default=False,
            ) #type: ignore

    flip_normal: BoolProperty(
            name="Flip Normal",
            description="Flip Normals during importing. Try if the model doesn't seem to be shading as expected in Blender and enabling 'Face Orientation' overlay shows **BLUE** (if it shows RED, try 'Flip Winding Order' instead). Not quite the same as flipping normals within Blender as this won't reverse the winding order",
            default=False,
            ) #type: ignore

    load_related: BoolProperty(
            name="Auto-load related meshes",
            description="Automatically load related meshes found in the frame analysis dump",
            default=True,
            ) #type: ignore

    load_related_so_vb: BoolProperty(
            name="Load pre-SO buffers (EXPERIMENTAL)",
            description="Scans the frame analysis log file to find GPU pre-skinning Stream Output techniques in prior draw calls, and loads the unposed vertex buffers from those calls that are suitable for editing. Recommended for Unity games to load neutral poses",
            default=False,
            ) #type: ignore

    merge_meshes: BoolProperty(
            name="Merge meshes together",
            description="Merge all selected meshes together into one object. Meshes must be related",
            default=False,
            ) #type: ignore

    pose_cb: StringProperty(
            name="Bone CB",
            description='Indicate a constant buffer slot (e.g. "vs-cb2") containing the bone matrices',
            default="",
            ) #type: ignore

    pose_cb_off: bpy.props.IntVectorProperty(
            name="Bone CB range",
            description='Indicate start and end offsets (in multiples of 4 component values) to find the matrices in the Bone CB',
            default=[0,0],
            size=2,
            min=0,
            ) #type: ignore

    pose_cb_step: bpy.props.IntProperty(
            name="Vertex group step",
            description='If used vertex groups are 0,1,2,3,etc specify 1. If they are 0,3,6,9,12,etc specify 3',
            default=1,
            min=1,
            ) #type: ignore
    

    def get_vb_ib_paths(self, load_related=None):
        buffer_pattern = re.compile(r'''-(?:ib|vb[0-9]+)(?P<hash>=[0-9a-f]+)?(?=[^0-9a-f=])''')
        vb_regex = re.compile(r'''^(?P<draw_call>[0-9]+)-vb(?P<slot>[0-9]+)=''') # TODO: Combine with above? (careful not to break hold type frame analysis)

        dirname = os.path.dirname(self.filepath)
        ret = set()
        if load_related is None:
            load_related = self.load_related

        vb_so_map = {}
        if self.load_related_so_vb:
            try:
                fa_log = open_frame_analysis_log_file(dirname)
            except FileNotFoundError:
                self.report({'WARNING'}, 'Frame Analysis Log File not found, loading unposed meshes from GPU Stream Output pre-skinning passes will be unavailable')
            else:
                vb_so_map = find_stream_output_vertex_buffers(fa_log)

        files = set()
        if load_related:
            for filename in self.files:
                match = buffer_pattern.search(filename.name)
                if match is None or not match.group('hash'):
                    continue
                paths = glob(os.path.join(dirname, '*%s*.txt' % filename.name[match.start():match.end()]))
                files.update([os.path.basename(x) for x in paths])
        if not files:
            files = [x.name for x in self.files]
            if files == ['']:
                raise Fatal('No files selected')

        done = set()
        for filename in files:
            if filename in done:
                continue
            match = buffer_pattern.search(filename)
            if match is None:
                if filename.lower().startswith('log') or filename.lower() == 'shaderusage.txt':
                    # User probably just selected all files including the log
                    continue
                self.report({'ERROR'}, 'Unable to find corresponding buffers from "{}" - filename did not match vertex/index buffer pattern'.format(filename))
                continue

            if not match.group('hash'):
                self.report({'INFO'}, 'Filename did not contain hash - if Frame Analysis dumped a custom resource the .txt file may be incomplete, Using .buf files instead')

            ib_pattern = filename[:match.start()] + '-ib*' + filename[match.end():]
            vb_pattern = filename[:match.start()] + '-vb*' + filename[match.end():]
            ib_paths = glob(os.path.join(dirname, ib_pattern))
            vb_paths = glob(os.path.join(dirname, vb_pattern))
            done.update(map(os.path.basename, itertools.chain(vb_paths, ib_paths)))

            if vb_so_map:
                vb_so_paths = set()
                for vb_path in vb_paths:
                    vb_match = vb_regex.match(os.path.basename(vb_path))
                    if vb_match:
                        draw_call, slot = map(int, vb_match.group('draw_call', 'slot'))
                        so = vb_so_map.get(VBSOMapEntry(draw_call, slot))
                        if so:
                            vb_so_pattern = f'{so.draw_call:06}-vb*.txt'
                            glob_result = glob(os.path.join(dirname, vb_so_pattern))
                            if not glob_result:
                                self.report({'WARNING'}, f'{vb_so_pattern} not found, loading unposed meshes from GPU Stream Output pre-skinning passes will be unavailable')
                            vb_so_paths.update(glob_result)
                vb_paths.extend(sorted(vb_so_paths))

            pose_path = None
            if self.pose_cb:
                pose_pattern = filename[:match.start()] + '*-' + self.pose_cb + '=*.txt'
                try:
                    pose_path = glob(os.path.join(dirname, pose_pattern))[0]
                except IndexError:
                    pass

            if len(ib_paths) > 1:
                raise Fatal('Error: excess index buffers in dump?')
            elif len(ib_paths) == 0:
                name = os.path.basename(vb_paths[0])
                ib_paths = [None]
                self.report({'WARNING'}, '{}: No index buffer present, support for this case is highly experimental'.format(name))
            ret.add(ImportPaths(tuple(vb_paths), ib_paths[0], False, pose_path))
        return ret

    def execute(self, context):
        if self.merge_meshes or self.load_related:
            self.report({'INFO'}, 'Loading .buf files selected: Disabled incompatible options')
        self.merge_meshes = False
        self.load_related = False

        try:
            keywords = self.as_keywords(ignore=('filepath', 'files',
                'filter_glob', 'load_related', 'load_related_so_vb',
                'pose_cb', 'semantic_remap', 'semantic_remap_idx'))
            paths = self.get_vb_ib_paths()

            import_3dmigoto(self, context, paths, **keywords)
            # Check if 'xxmi' attribute exists in the scene before accessing it
            xxmi = getattr(context.scene, "xxmi", None)
            if xxmi is not None:
                if not getattr(xxmi, "dump_path", None):
                    if os.path.exists(os.path.join(os.path.dirname(self.filepath), 'hash.json')):
                        xxmi.dump_path = os.path.dirname(self.filepath)
        except Fatal as e:
            self.report({'ERROR'}, str(e))
        return {'FINISHED'}

    def draw(self, context):
        pass

@orientation_helper(axis_forward='-Z', axis_up='Y')
class QuickImport3DMigotoRaw(bpy.types.Operator, ImportHelper, IOOBJOrientationHelper):
    """Import raw 3DMigoto vertex and index buffers"""
    bl_idname = "import_mesh.quickimportxxmi_raw_buffers"
    bl_label = "Import 3DMigoto Raw Buffers"
    #bl_options = {'PRESET', 'UNDO'}
    bl_options = {'UNDO'}

    filename_ext = '.vb;.ib'
    filter_glob: StringProperty(
            default='*.vb*;*.ib',
            options={'HIDDEN'},
            ) #type: ignore

    files: CollectionProperty(
            name="File Path",
            type=bpy.types.OperatorFileListElement,
            ) #type: ignore

    flip_texcoord_v: BoolProperty(
            name="Flip TEXCOORD V",
            description="Flip TEXCOORD V axis during importing",
            default=True,
            ) #type: ignore

    flip_winding: BoolProperty(
            name="Flip Winding Order",
            description="Flip winding order (face orientation) during importing. Try if the model doesn't seem to be shading as expected in Blender and enabling the 'Face Orientation' overlay shows **RED** (if it shows BLUE, try 'Flip Normal' instead). Not quite the same as flipping normals within Blender as this only reverses the winding order without flipping the normals. Recommended for Unreal Engine",
            default=False,
            ) #type: ignore

    flip_normal: BoolProperty(
            name="Flip Normal",
            description="Flip Normals during importing. Try if the model doesn't seem to be shading as expected in Blender and enabling 'Face Orientation' overlay shows **BLUE** (if it shows RED, try 'Flip Winding Order' instead). Not quite the same as flipping normals within Blender as this won't reverse the winding order",
            default=False,
            ) #type: ignore

    def get_vb_ib_paths(self, filename):
        vb_bin_path = glob(os.path.splitext(filename)[0] + '.vb*')
        ib_bin_path = os.path.splitext(filename)[0] + '.ib'
        fmt_path = os.path.splitext(filename)[0] + '.fmt'
        vgmap_path = os.path.splitext(filename)[0] + '.vgmap'
        if len(vb_bin_path) < 1:
            raise Fatal('Unable to find matching .vb* file(s) for %s' % filename)
        if not os.path.exists(ib_bin_path):
            ib_bin_path = None
        if not os.path.exists(fmt_path):
            fmt_path = None
        if not os.path.exists(vgmap_path):
            vgmap_path = None
        return (vb_bin_path, ib_bin_path, fmt_path, vgmap_path)

    def execute(self, context):
        # I'm not sure how to find the Import3DMigotoReferenceInputFormat
        # instance that Blender instantiated to pass the values from one
        # import dialog to another, but since everything is modal we can
        # just use globals:
        global migoto_raw_import_options
        migoto_raw_import_options = self.as_keywords(ignore=('filepath', 'files', 'filter_glob'))

        done = set()
        dirname = os.path.dirname(self.filepath)
        for filename in self.files:
            try:
                (vb_path, ib_path, fmt_path, vgmap_path) = self.get_vb_ib_paths(os.path.join(dirname, filename.name))
                vb_path_norm = set(map(os.path.normcase, vb_path))
                if vb_path_norm.intersection(done) != set():
                    continue
                done.update(vb_path_norm)

                if fmt_path is not None:
                    import_3dmigoto_raw_buffers(self, context, fmt_path, fmt_path, vb_path=vb_path, ib_path=ib_path, vgmap_path=vgmap_path, **migoto_raw_import_options)
                else:
                    migoto_raw_import_options['vb_path'] = vb_path
                    migoto_raw_import_options['ib_path'] = ib_path
                    bpy.ops.import_mesh.migoto_input_format('INVOKE_DEFAULT')
            except Fatal as e:
                self.report({'ERROR'}, str(e))
        return {'FINISHED'}

class Import3DMigotoReferenceInputFormat(bpy.types.Operator, ImportHelper):
    bl_idname = "import_mesh.migoto_input_format"
    bl_label = "Select a .txt file with matching format"
    bl_options = {'UNDO', 'INTERNAL'}

    filename_ext = '.txt;.fmt'
    filter_glob: StringProperty(
            default='*.txt;*.fmt',
            options={'HIDDEN'},
            ) #type: ignore

    def get_vb_ib_paths(self):
        if os.path.splitext(self.filepath)[1].lower() == '.fmt':
            return (self.filepath, self.filepath)

        buffer_pattern = re.compile(r'''-(?:ib|vb[0-9]+)(?P<hash>=[0-9a-f]+)?(?=[^0-9a-f=])''')

        dirname = os.path.dirname(self.filepath)
        filename = os.path.basename(self.filepath)

        match = buffer_pattern.search(filename)
        if match is None:
            raise Fatal('Reference .txt filename does not look like a 3DMigoto timestamped Frame Analysis Dump')
        ib_pattern = filename[:match.start()] + '-ib*' + filename[match.end():]
        vb_pattern = filename[:match.start()] + '-vb*' + filename[match.end():]
        ib_paths = glob(os.path.join(dirname, ib_pattern))
        vb_paths = glob(os.path.join(dirname, vb_pattern))
        if len(ib_paths) < 1 or len(vb_paths) < 1:
            raise Fatal('Unable to locate reference files for both vertex buffer and index buffer format descriptions')
        return (vb_paths[0], ib_paths[0])

    def execute(self, context):
        global migoto_raw_import_options

        try:
            vb_fmt_path, ib_fmt_path = self.get_vb_ib_paths()
            import_3dmigoto_raw_buffers(self, context, vb_fmt_path, ib_fmt_path, **migoto_raw_import_options)
        except Fatal as e:
            self.report({'ERROR'}, str(e))
        return {'FINISHED'}