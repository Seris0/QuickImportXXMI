import bpy #type: ignore
import bmesh #type: ignore
import os
import io
import re
import itertools
from array import array
import struct
import numpy
import collections
import json
import textwrap 
from bpy_extras.io_utils import unpack_list, axis_conversion #type: ignore
import time
############## Begin (deprecated) Blender 2.7/2.8 compatibility wrappers (2.7 options removed) ##############

vertex_color_layer_channels = 4

def select_get(object):
    return object.select_get()

def select_set(object, state):
    object.select_set(state)

def hide_get(object):
    return object.hide_get()

def hide_set(object, state):
    object.hide_set(state)

def set_active_object(context, obj):
    context.view_layer.objects.active = obj # the 2.8 way

def get_active_object(context):
    return context.view_layer.objects.active

def link_object_to_scene(context, obj):
    context.scene.collection.objects.link(obj)

def unlink_object(context, obj):
    context.scene.collection.objects.unlink(obj)

def matmul(a, b):
    import operator # to get function names for operators like @, +, -
    return operator.matmul(a, b) # the same as writing a @ b

############## End (deprecated) Blender 2.7/2.8 compatibility wrappers (2.7 options removed) ##############

semantic_remap_enum = [
        ('None', 'No change', 'Do not remap this semantic. If the semantic name is recognised the script will try to interpret it, otherwise it will preserve the existing data in a vertex layer'),
        ('POSITION', 'POSITION', 'This data will be used as the vertex positions. There should generally be exactly one POSITION semantic for hopefully obvious reasons'),
        ('NORMAL', 'NORMAL', 'This data will be used as split (custom) normals in Blender.'),
        ('TANGENT', 'TANGENT (CAUTION: Discards data!)', 'Data in the TANGENT semantics are discarded on import, and recalculated on export'),
        #('BINORMAL', 'BINORMAL', "Don't encourage anyone to choose this since the data will be entirely discarded"),
        ('BLENDINDICES', 'BLENDINDICES', 'This semantic holds the vertex group indices, and should be paired with a BLENDWEIGHT semantic that has the corresponding weights for these groups'),
        ('BLENDWEIGHT', 'BLENDWEIGHT', 'This semantic holds the vertex group weights, and should be paired with a BLENDINDICES semantic that has the corresponding vertex group indices that these weights apply to'),
        ('TEXCOORD', 'TEXCOORD', 'Typically holds UV coordinates, though can also be custom data. Choosing this will import the data as a UV layer (or two) in Blender'),
        ('COLOR', 'COLOR', 'Typically used for vertex colors, though can also be custom data. Choosing this option will import the data as a vertex color layer in Blender'),
        ('Preserve', 'Unknown / Preserve', "Don't try to interpret the data. Choosing this option will simply store the data in a vertex layer in Blender so that it can later be exported unmodified"),
    ]

supported_topologies = ('trianglelist', 'pointlist', 'trianglestrip')

ImportPaths = collections.namedtuple('ImportPaths', ('vb_paths', 'ib_paths', 'use_bin', 'pose_path'))

def keys_to_ints(d):
    return {k.isdecimal() and int(k) or k:v for k,v in d.items()}
def keys_to_strings(d):
    return {str(k):v for k,v in d.items()}

class Fatal(Exception): pass

# TODO: Support more DXGI formats:
f32_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]32)+_FLOAT''')
f16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_FLOAT''')
u32_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]32)+_UINT''')
u16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_UINT''')
u8_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]8)+_UINT''')
s32_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]32)+_SINT''')
s16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_SINT''')
s8_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]8)+_SINT''')
unorm16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_UNORM''')
unorm8_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]8)+_UNORM''')
snorm16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_SNORM''')
snorm8_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]8)+_SNORM''')

misc_float_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD][0-9]+)+_(?:FLOAT|UNORM|SNORM)''')
misc_int_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD][0-9]+)+_[SU]INT''')

def EncoderDecoder(fmt):
    if f32_pattern.match(fmt):
        return (lambda data: b''.join(struct.pack('<f', x) for x in data),
                lambda data: numpy.frombuffer(data, numpy.float32).tolist())
    if f16_pattern.match(fmt):
        return (lambda data: numpy.fromiter(data, numpy.float16).tobytes(),
                lambda data: numpy.frombuffer(data, numpy.float16).tolist())
    if u32_pattern.match(fmt):
        return (lambda data: numpy.fromiter(data, numpy.uint32).tobytes(),
                lambda data: numpy.frombuffer(data, numpy.uint32).tolist())
    if u16_pattern.match(fmt):
        return (lambda data: numpy.fromiter(data, numpy.uint16).tobytes(),
                lambda data: numpy.frombuffer(data, numpy.uint16).tolist())
    if u8_pattern.match(fmt):
        return (lambda data: numpy.fromiter(data, numpy.uint8).tobytes(),
                lambda data: numpy.frombuffer(data, numpy.uint8).tolist())
    if s32_pattern.match(fmt):
        return (lambda data: numpy.fromiter(data, numpy.int32).tobytes(),
                lambda data: numpy.frombuffer(data, numpy.int32).tolist())
    if s16_pattern.match(fmt):
        return (lambda data: numpy.fromiter(data, numpy.int16).tobytes(),
                lambda data: numpy.frombuffer(data, numpy.int16).tolist())
    if s8_pattern.match(fmt):
        return (lambda data: numpy.fromiter(data, numpy.int8).tobytes(),
                lambda data: numpy.frombuffer(data, numpy.int8).tolist())

    if unorm16_pattern.match(fmt):
        return (lambda data: numpy.around((numpy.fromiter(data, numpy.float32) * 65535.0)).astype(numpy.uint16).tobytes(),
                lambda data: (numpy.frombuffer(data, numpy.uint16) / 65535.0).tolist())
    if unorm8_pattern.match(fmt):
        return (lambda data: numpy.around((numpy.fromiter(data, numpy.float32) * 255.0)).astype(numpy.uint8).tobytes(),
                lambda data: (numpy.frombuffer(data, numpy.uint8) / 255.0).tolist())
    if snorm16_pattern.match(fmt):
        return (lambda data: numpy.around((numpy.fromiter(data, numpy.float32) * 32767.0)).astype(numpy.int16).tobytes(),
                lambda data: (numpy.frombuffer(data, numpy.int16) / 32767.0).tolist())
    if snorm8_pattern.match(fmt):
        return (lambda data: numpy.around((numpy.fromiter(data, numpy.float32) * 127.0)).astype(numpy.int8).tobytes(),
                lambda data: (numpy.frombuffer(data, numpy.int8) / 127.0).tolist())

    raise Fatal('File uses an unsupported DXGI Format: %s' % fmt)

components_pattern = re.compile(r'''(?<![0-9])[0-9]+(?![0-9])''')
def format_components(fmt):
    return len(components_pattern.findall(fmt))

def format_size(fmt):
    matches = components_pattern.findall(fmt)
    return sum(map(int, matches)) // 8

class InputLayoutElement(object):
    def __init__(self, arg):
        self.RemappedSemanticName = None
        self.RemappedSemanticIndex = None
        if isinstance(arg, io.IOBase):
            self.from_file(arg)
        else:
            self.from_dict(arg)

        self.encoder, self.decoder = EncoderDecoder(self.Format)

    def from_file(self, f):
        self.SemanticName = self.next_validate(f, 'SemanticName')
        self.SemanticIndex = int(self.next_validate(f, 'SemanticIndex'))
        (self.RemappedSemanticName, line) = self.next_optional(f, 'RemappedSemanticName')
        if line is None:
            self.RemappedSemanticIndex = int(self.next_validate(f, 'RemappedSemanticIndex'))
        self.Format = self.next_validate(f, 'Format', line)
        self.InputSlot = int(self.next_validate(f, 'InputSlot'))
        self.AlignedByteOffset = self.next_validate(f, 'AlignedByteOffset')
        if self.AlignedByteOffset == 'append':
            raise Fatal('Input layouts using "AlignedByteOffset=append" are not yet supported')
        self.AlignedByteOffset = int(self.AlignedByteOffset)
        self.InputSlotClass = self.next_validate(f, 'InputSlotClass')
        self.InstanceDataStepRate = int(self.next_validate(f, 'InstanceDataStepRate'))
        self.format_len = format_components(self.Format)

    def to_dict(self):
        d = {}
        d['SemanticName'] = self.SemanticName
        d['SemanticIndex'] = self.SemanticIndex
        if self.RemappedSemanticName is not None:
            d['RemappedSemanticName'] = self.RemappedSemanticName
            d['RemappedSemanticIndex'] = self.RemappedSemanticIndex
        d['Format'] = self.Format
        d['InputSlot'] = self.InputSlot
        d['AlignedByteOffset'] = self.AlignedByteOffset
        d['InputSlotClass'] = self.InputSlotClass
        d['InstanceDataStepRate'] = self.InstanceDataStepRate
        return d

    def to_string(self, indent=2):
        ret = textwrap.dedent('''
            SemanticName: %s
            SemanticIndex: %i
        ''').lstrip() % (
            self.SemanticName,
            self.SemanticIndex,
        )
        if self.RemappedSemanticName is not None:
            ret += textwrap.dedent('''
                RemappedSemanticName: %s
                RemappedSemanticIndex: %i
            ''').lstrip() % (
                self.RemappedSemanticName,
                self.RemappedSemanticIndex,
            )
        ret += textwrap.dedent('''
            Format: %s
            InputSlot: %i
            AlignedByteOffset: %i
            InputSlotClass: %s
            InstanceDataStepRate: %i
        ''').lstrip() % (
            self.Format,
            self.InputSlot,
            self.AlignedByteOffset,
            self.InputSlotClass,
            self.InstanceDataStepRate,
        )
        return textwrap.indent(ret, ' '*indent)

    def from_dict(self, d):
        self.SemanticName = d['SemanticName']
        self.SemanticIndex = d['SemanticIndex']
        try:
            self.RemappedSemanticName = d['RemappedSemanticName']
            self.RemappedSemanticIndex = d['RemappedSemanticIndex']
        except KeyError: pass
        self.Format = d['Format']
        self.InputSlot = d['InputSlot']
        self.AlignedByteOffset = d['AlignedByteOffset']
        self.InputSlotClass = d['InputSlotClass']
        self.InstanceDataStepRate = d['InstanceDataStepRate']
        self.format_len = format_components(self.Format)

    @staticmethod
    def next_validate(f, field, line=None):
        if line is None:
            line = next(f).strip()
        assert(line.startswith(field + ': '))
        return line[len(field) + 2:]

    @staticmethod
    def next_optional(f, field, line=None):
        if line is None:
            line = next(f).strip()
        if line.startswith(field + ': '):
            return (line[len(field) + 2:], None)
        return (None, line)

    @property
    def name(self):
        if self.SemanticIndex:
            return '%s%i' % (self.SemanticName, self.SemanticIndex)
        return self.SemanticName

    @property
    def remapped_name(self):
        if self.RemappedSemanticName is None:
            return self.name
        if self.RemappedSemanticIndex:
            return '%s%i' % (self.RemappedSemanticName, self.RemappedSemanticIndex)
        return self.RemappedSemanticName

    def pad(self, data, val):
        padding = self.format_len - len(data)
        assert(padding >= 0)
        data.extend([val]*padding)
        return data

    def clip(self, data):
        return data[:format_components(self.Format)]

    def size(self):
        return format_size(self.Format)

    def is_float(self):
        return misc_float_pattern.match(self.Format)

    def is_int(self):
        return misc_int_pattern.match(self.Format)

    def encode(self, data):
        # print(self.Format, data)
        return self.encoder(data)

    def decode(self, data):
        return self.decoder(data)

    def __eq__(self, other):
        return \
            self.SemanticName == other.SemanticName and \
            self.SemanticIndex == other.SemanticIndex and \
            self.Format == other.Format and \
            self.InputSlot == other.InputSlot and \
            self.AlignedByteOffset == other.AlignedByteOffset and \
            self.InputSlotClass == other.InputSlotClass and \
            self.InstanceDataStepRate == other.InstanceDataStepRate

class InputLayout(object):
    def __init__(self, custom_prop=[]):
        self.semantic_translations_cache = None
        self.elems = collections.OrderedDict()
        for item in custom_prop:
            elem = InputLayoutElement(item)
            self.elems[elem.name] = elem

    def serialise(self):
        return [x.to_dict() for x in self.elems.values()]

    def to_string(self):
        ret = ''
        for i, elem in enumerate(self.elems.values()):
            ret += 'element[%i]:\n' % i
            ret += elem.to_string()
        return ret

    def parse_element(self, f):
        elem = InputLayoutElement(f)
        self.elems[elem.name] = elem

    def __iter__(self):
        return iter(self.elems.values())

    def __getitem__(self, semantic):
        return self.elems[semantic]

    def untranslate_semantic(self, translated_semantic_name, translated_semantic_index=0):
        semantic_translations = self.get_semantic_remap()
        reverse_semantic_translations = {v: k for k,v in semantic_translations.items()}
        semantic = reverse_semantic_translations[(translated_semantic_name, translated_semantic_index)]
        return self[semantic]

    def encode(self, vertex, vbuf_idx, stride):
        buf = bytearray(stride)

        for semantic, data in vertex.items():
            if semantic.startswith('~'):
                continue
            elem = self.elems[semantic]
            if vbuf_idx.isnumeric() and elem.InputSlot != int(vbuf_idx):
                # Belongs to a different vertex buffer
                continue
            data = elem.encode(data)
            buf[elem.AlignedByteOffset:elem.AlignedByteOffset + len(data)] = data

        assert(len(buf) == stride)
        return buf

    def decode(self, buf, vbuf_idx):
        vertex = {}
        for elem in self.elems.values():
            if elem.InputSlot != vbuf_idx:
                # Belongs to a different vertex buffer
                continue
            data = buf[elem.AlignedByteOffset:elem.AlignedByteOffset + elem.size()]
            vertex[elem.name] = elem.decode(data)
        return vertex

    def __eq__(self, other):
        return self.elems == other.elems

    def apply_semantic_remap(self, operator):
        semantic_translations = {}
        semantic_highest_indices = {}

        for elem in self.elems.values():
            semantic_highest_indices[elem.SemanticName.upper()] = max(semantic_highest_indices.get(elem.SemanticName.upper(), 0), elem.SemanticIndex)

        def find_free_elem_index(semantic):
            idx = semantic_highest_indices.get(semantic, -1) + 1
            semantic_highest_indices[semantic] = idx
            return idx

        for remap in operator.properties.semantic_remap:
            if remap.semantic_to == 'None':
                continue
            if remap.semantic_from in semantic_translations:
                operator.report({'ERROR'}, 'semantic remap for {} specified multiple times, only the first will be used'.format(remap.semantic_from))
                continue
            if remap.semantic_from not in self.elems:
                operator.report({'WARNING'}, 'semantic "{}" not found in imported file, double check your semantic remaps'.format(remap.semantic_from))
                continue

            remapped_semantic_idx = find_free_elem_index(remap.semantic_to)

            operator.report({'INFO'}, 'Remapping semantic {} -> {}{}'.format(remap.semantic_from, remap.semantic_to,
                remapped_semantic_idx or ''))

            self.elems[remap.semantic_from].RemappedSemanticName = remap.semantic_to
            self.elems[remap.semantic_from].RemappedSemanticIndex = remapped_semantic_idx
            semantic_translations[remap.semantic_from] = (remap.semantic_to, remapped_semantic_idx)

        self.semantic_translations_cache = semantic_translations
        return semantic_translations

    def get_semantic_remap(self):
        if self.semantic_translations_cache:
            return self.semantic_translations_cache
        semantic_translations = {}
        for elem in self.elems.values():
            if elem.RemappedSemanticName is not None:
                semantic_translations[elem.name] = \
                    (elem.RemappedSemanticName, elem.RemappedSemanticIndex)
        self.semantic_translations_cache = semantic_translations
        return semantic_translations

class HashableVertex(dict):
    def __hash__(self):
        # Convert keys and values into immutable types that can be hashed
        immutable = tuple((k, tuple(v)) for k,v in sorted(self.items()))
        return hash(immutable)

class IndividualVertexBuffer(object):
    '''
    One individual vertex buffer. Multiple vertex buffers may contain
    individual semantics which when combined together make up a vertex buffer
    group.
    '''

    vb_elem_pattern = re.compile(r'''vb\d+\[\d*\]\+\d+ (?P<semantic>[^:]+): (?P<data>.*)$''')

    def __init__(self, idx, f=None, layout=None, load_vertices=True):
        self.vertices = []
        self.layout = layout and layout or InputLayout()
        self.first = 0
        self.vertex_count = 0
        self.offset = 0
        self.topology = 'trianglelist'
        self.stride = 0
        self.idx = idx

        if f is not None:
            self.parse_vb_txt(f, load_vertices)

    def parse_vb_txt(self, f, load_vertices):
        split_vb_stride = 'vb%i stride:' % self.idx
        for line in map(str.strip, f):
            # print(line)
            if line.startswith('byte offset:'):
                self.offset = int(line[13:])
            if line.startswith('first vertex:'):
                self.first = int(line[14:])
            if line.startswith('vertex count:'):
                self.vertex_count = int(line[14:])
            if line.startswith('stride:'):
                self.stride = int(line[7:])
            if line.startswith(split_vb_stride):
                self.stride = int(line[len(split_vb_stride):])
            if line.startswith('element['):
                self.layout.parse_element(f)
            if line.startswith('topology:'):
                self.topology = line[10:]
                if self.topology not in supported_topologies:
                    raise Fatal('"%s" is not yet supported' % line)
            if line.startswith('vertex-data:'):
                if not load_vertices:
                    return
                self.parse_vertex_data(f)
        # If the buffer is only per-instance elements there won't be any
        # vertices. If the buffer has any per-vertex elements than we should
        # have the number of vertices declared in the header.
        if self.vertices:
            assert(len(self.vertices) == self.vertex_count)

    def parse_vb_bin(self, f, use_drawcall_range=False):
        f.seek(self.offset)
        if use_drawcall_range:
            f.seek(self.first * self.stride, 1)
        else:
            self.first = 0
        for i in itertools.count():
            if use_drawcall_range and i == self.vertex_count:
                break
            vertex = f.read(self.stride)
            if not vertex:
                break
            self.vertices.append(self.layout.decode(vertex, self.idx))
        # We intentionally disregard the vertex count when loading from a
        # binary file, as we assume frame analysis might have only dumped a
        # partial buffer to the .txt files (e.g. if this was from a dump where
        # the draw call index count was overridden it may be cut short, or
        # where the .txt files contain only sub-meshes from each draw call and
        # we are loading the .buf file because it contains the entire mesh):
        self.vertex_count = len(self.vertices)

    def append(self, vertex):
        self.vertices.append(vertex)
        self.vertex_count += 1

    def parse_vertex_data(self, f):
        vertex = {}
        for line in map(str.strip, f):
            #print(line)
            if line.startswith('instance-data:'):
                break

            match = self.vb_elem_pattern.match(line)
            if match:
                vertex[match.group('semantic')] = self.parse_vertex_element(match)
            elif line == '' and vertex:
                self.vertices.append(vertex)
                vertex = {}
        if vertex:
            self.vertices.append(vertex)

    @staticmethod
    def ms_float(val):
        x = val.split('.#')
        s = float(x[0])
        if len(x) == 1:
            return s
        if x[1].startswith('INF'):
            return s * numpy.inf # Will preserve sign
        # TODO: Differentiate between SNAN / QNAN / IND
        if s == -1: # Multiplying -1 * nan doesn't preserve sign
            return -numpy.nan # so must use unary - operator
        return numpy.nan

    def parse_vertex_element(self, match):
        fields = match.group('data').split(',')

        if self.layout[match.group('semantic')].Format.endswith('INT'):
            return tuple(map(int, fields))

        return tuple(map(self.ms_float, fields))

class VertexBufferGroup(object):
    '''
    All the per-vertex data, which may be loaded/saved from potentially
    multiple individual vertex buffers with different semantics in each.
    '''
    vb_idx_pattern = re.compile(r'''[-\.]vb([0-9]+)''')

    # Python gotcha - do not set layout=InputLayout() in the default function
    # parameters, as they would all share the *same* InputLayout since the
    # default values are only evaluated once on file load
    def __init__(self, files=None, layout=None, load_vertices=True, topology=None):
        self.vertices = []
        self.layout = layout and layout or InputLayout()
        self.first = 0
        self.vertex_count = 0
        self.topology = topology or 'trianglelist'
        self.vbs = []
        self.slots = {}

        if files is not None:
            self.parse_vb_txt(files, load_vertices)

    def parse_vb_txt(self, files, load_vertices):
        for f in files:
            match = self.vb_idx_pattern.search(f)
            if match is None:
                raise Fatal('Cannot determine vertex buffer index from filename %s' % f)
            idx = int(match.group(1))
            vb = IndividualVertexBuffer(idx, open(f, 'r'), self.layout, load_vertices)
            if vb.vertices:
                self.vbs.append(vb)
                self.slots[idx] = vb

        self.flag_invalid_semantics()

        # Non buffer specific info:
        self.first = self.vbs[0].first
        self.vertex_count = self.vbs[0].vertex_count
        self.topology = self.vbs[0].topology

        if load_vertices:
            self.merge_vbs(self.vbs)
            assert(len(self.vertices) == self.vertex_count)

    def parse_vb_bin(self, files, use_drawcall_range=False):
        for (bin_f, fmt_f) in files:
            match = self.vb_idx_pattern.search(bin_f)
            if match is not None:
                idx = int(match.group(1))
            else:
                print('Cannot determine vertex buffer index from filename %s, assuming 0 for backwards compatibility' % bin_f)
                idx = 0
            vb = IndividualVertexBuffer(idx, open(fmt_f, 'r'), self.layout, False)
            vb.parse_vb_bin(open(bin_f, 'rb'), use_drawcall_range)
            if vb.vertices:
                self.vbs.append(vb)
                self.slots[idx] = vb

        self.flag_invalid_semantics()

        # Non buffer specific info:
        self.first = self.vbs[0].first
        self.vertex_count = self.vbs[0].vertex_count
        self.topology = self.vbs[0].topology

        self.merge_vbs(self.vbs)
        assert(len(self.vertices) == self.vertex_count)

    def append(self, vertex):
        self.vertices.append(vertex)
        self.vertex_count += 1

    def remap_blendindices(self, obj, mapping):
        def lookup_vgmap(x):
            vgname = obj.vertex_groups[x].name
            return mapping.get(vgname, mapping.get(x, x))

        for vertex in self.vertices:
            for semantic in list(vertex):
                if semantic.startswith('BLENDINDICES'):
                    vertex['~' + semantic] = vertex[semantic]
                    vertex[semantic] = tuple(lookup_vgmap(x) for x in vertex[semantic])

    def revert_blendindices_remap(self):
        # Significantly faster than doing a deep copy
        for vertex in self.vertices:
            for semantic in list(vertex):
                if semantic.startswith('BLENDINDICES'):
                    vertex[semantic] = vertex['~' + semantic]
                    del vertex['~' + semantic]

    def disable_blendweights(self):
        for vertex in self.vertices:
            for semantic in list(vertex):
                if semantic.startswith('BLENDINDICES'):
                    vertex[semantic] = (0, 0, 0, 0)

    def write(self, output_prefix, strides, operator=None):
        for vbuf_idx, stride in strides.items():
            with open(output_prefix + vbuf_idx, 'wb') as output:
                for vertex in self.vertices:
                    output.write(self.layout.encode(vertex, vbuf_idx, stride))

                msg = 'Wrote %i vertices to %s' % (len(self), output.name)
                if operator:
                    operator.report({'INFO'}, msg)
                else:
                    print(msg)

    def __len__(self):
        return len(self.vertices)

    def merge_vbs(self, vbs):
        self.vertices = self.vbs[0].vertices
        del self.vbs[0].vertices
        assert(len(self.vertices) == self.vertex_count)
        for vb in self.vbs[1:]:
            assert(len(vb.vertices) == self.vertex_count)
            [ self.vertices[i].update(vertex) for i,vertex in enumerate(vb.vertices) ]
            del vb.vertices

    def merge(self, other):
        if self.layout != other.layout:
            raise Fatal('Vertex buffers have different input layouts - ensure you are only trying to merge the same vertex buffer split across multiple draw calls')
        if self.first != other.first:
            # FIXME: Future 3DMigoto might automatically set first from the
            # index buffer and chop off unreferenced vertices to save space
            raise Fatal('Cannot merge multiple vertex buffers - please check for updates of the 3DMigoto import script, or import each buffer separately')
        self.vertices.extend(other.vertices[self.vertex_count:])
        self.vertex_count = max(self.vertex_count, other.vertex_count)
        assert(len(self.vertices) == self.vertex_count)

    def wipe_semantic_for_testing(self, semantic, val=0):
        print('WARNING: WIPING %s FOR TESTING PURPOSES!!!' % semantic)
        semantic, _, components = semantic.partition('.')
        if components:
            components = [{'x':0, 'y':1, 'z':2, 'w':3}[c] for c in components]
        else:
            components = range(4)
        for vertex in self.vertices:
            for s in list(vertex):
                if s == semantic:
                    v = list(vertex[semantic])
                    for component in components:
                        if component < len(v):
                            v[component] = val
                    vertex[semantic] = v

    def flag_invalid_semantics(self):
        # This refactors some of the logic that used to be in import_vertices()
        # and get_valid_semantics() - Any semantics that re-use the same offset
        # of an earlier semantic is considered invalid and will be ignored when
        # importing the vertices. These are usually a quirk of how certain
        # engines handle unused semantics and at best will be repeating data we
        # already imported in another semantic and at worst may be
        # misinterpreting the data as a completely different type.
        #
        # Is is theoretically possible for the earlier semantic to be the
        # invalid one - if we ever encounter that we might want to allow the
        # user to choose which of the semantics sharing the same offset should
        # be considerd the valid one.
        #
        # This also makes sure the corresponding vertex buffer is present and
        # can fit the semantic.
        seen_offsets = set()
        for elem in self.layout:
            if elem.InputSlotClass != 'per-vertex':
                # Instance data isn't invalid, we just don't import it yet
                continue
            if (elem.InputSlot, elem.AlignedByteOffset) in seen_offsets:
                # Setting two flags to avoid changing behaviour in the refactor
                # - might be able to simplify this to one flag, but want to
                # test semantics that [partially] overflow the stride first,
                # and make sure that export flow (stride won't be set) works.
                elem.reused_offset = True
                elem.invalid_semantic = True
                continue
            seen_offsets.add((elem.InputSlot, elem.AlignedByteOffset))
            elem.reused_offset = False

            try:
                stride = self.slots[elem.InputSlot].stride
            except KeyError:
                # UE4 claiming it uses vertex buffers that it doesn't bind.
                elem.invalid_semantic = True
                continue

            if elem.AlignedByteOffset + format_size(elem.Format) > stride:
                elem.invalid_semantic = True
                continue

            elem.invalid_semantic = False

    def get_valid_semantics(self):
        self.flag_invalid_semantics()
        return set([elem.name for elem in self.layout
            if elem.InputSlotClass == 'per-vertex' and not elem.invalid_semantic])

class IndexBuffer(object):
    def __init__(self, *args, load_indices=True):
        self.faces = []
        self.first = 0
        self.index_count = 0
        self.format = 'DXGI_FORMAT_UNKNOWN'
        self.offset = 0
        self.topology = 'trianglelist'
        self.used_in_drawcall = None

        if isinstance(args[0], io.IOBase):
            assert(len(args) == 1)
            self.parse_ib_txt(args[0], load_indices)
        else:
            self.format, = args

        self.encoder, self.decoder = EncoderDecoder(self.format)

    def append(self, face):
        self.faces.append(face)
        self.index_count += len(face)

    def parse_ib_txt(self, f, load_indices):
        for line in map(str.strip, f):
            if line.startswith('byte offset:'):
                self.offset = int(line[13:])
                # If we see this line we are looking at a 3DMigoto frame
                # analysis dump, not a .fmt file exported by this script.
                # If it was an indexed draw call it will be followed by "first
                # index" and "index count", while if it was not an indexed draw
                # call they will be absent. So by the end of parsing:
                # used_in_drawcall = None signifies loading a .fmt file from a previous export
                # used_in_drawcall = False signifies draw call did not use the bound IB
                # used_in_drawcall = True signifies an indexed draw call
                self.used_in_drawcall = False
            if line.startswith('first index:'):
                self.first = int(line[13:])
                self.used_in_drawcall = True
            elif line.startswith('index count:'):
                self.index_count = int(line[13:])
                self.used_in_drawcall = True
            elif line.startswith('topology:'):
                self.topology = line[10:]
                if self.topology not in supported_topologies:
                    raise Fatal('"%s" is not yet supported' % line)
            elif line.startswith('format:'):
                self.format = line[8:]
            elif line == '':
                if not load_indices:
                    return
                self.parse_index_data(f)
        if self.used_in_drawcall != False:
            assert(len(self.faces) * self.indices_per_face + self.extra_indices == self.index_count)

    def parse_ib_bin(self, f, use_drawcall_range=False):
        f.seek(self.offset)
        stride = format_size(self.format)
        if use_drawcall_range:
            f.seek(self.first * stride, 1)
        else:
            self.first = 0

        face = []
        for i in itertools.count():
            if use_drawcall_range and i == self.index_count:
                break
            index = f.read(stride)
            if not index:
                break
            face.append(*self.decoder(index))
            if len(face) == self.indices_per_face:
                self.faces.append(tuple(face))
                face = []
        assert(len(face) == 0)
        self.expand_strips()

        if use_drawcall_range:
            assert(len(self.faces) * self.indices_per_face + self.extra_indices == self.index_count)
        else:
            # We intentionally disregard the index count when loading from a
            # binary file, as we assume frame analysis might have only dumped a
            # partial buffer to the .txt files (e.g. if this was from a dump where
            # the draw call index count was overridden it may be cut short, or
            # where the .txt files contain only sub-meshes from each draw call and
            # we are loading the .buf file because it contains the entire mesh):
            self.index_count = len(self.faces) * self.indices_per_face + self.extra_indices

    def parse_index_data(self, f):
        for line in map(str.strip, f):
            face = tuple(map(int, line.split()))
            assert(len(face) == self.indices_per_face)
            self.faces.append(face)
        self.expand_strips()

    def expand_strips(self):
        if self.topology == 'trianglestrip':
            # Every 2nd face has the vertices out of order to keep all faces in the same orientation:
            # https://learn.microsoft.com/en-us/windows/win32/direct3d9/triangle-strips
            self.faces = [(self.faces    [i-2][0],
                self.faces[i%2 and i   or i-1][0],
                self.faces[i%2 and i-1 or i  ][0],
            ) for i in range(2, len(self.faces)) ]
        elif self.topology == 'linestrip':
            raise Fatal('linestrip topology conversion is untested')
            self.faces = [(self.faces[i-1][0], self.faces[i][0])
                    for i in range(1, len(self.faces)) ]

    def merge(self, other):
        if self.format != other.format:
            raise Fatal('Index buffers have different formats - ensure you are only trying to merge the same index buffer split across multiple draw calls')
        self.first = min(self.first, other.first)
        self.index_count += other.index_count
        self.faces.extend(other.faces)

    def write(self, output, operator=None):
        for face in self.faces:
            output.write(self.encoder(face))

        msg = 'Wrote %i indices to %s' % (len(self), output.name)
        if operator:
            operator.report({'INFO'}, msg)
        else:
            print(msg)

    @property
    def indices_per_face(self):
        return {
            'trianglelist': 3,
            'pointlist': 1,
            'trianglestrip': 1, # + self.extra_indices for 1st tri
            'linelist': 2,
            'linestrip': 1, # + self.extra_indices for 1st line
        }[self.topology]

    @property
    def extra_indices(self):
        if len(self.faces) >= 1:
            if self.topology == 'trianglestrip':
                return 2
            if self.topology == 'linestrip':
                return 1
        return 0

    def __len__(self):
        return len(self.faces) * self.indices_per_face + self.extra_indices

def load_3dmigoto_mesh_bin(operator, vb_paths, ib_paths, pose_path):
    if len(vb_paths) != 1 or len(ib_paths) > 1:
        raise Fatal('Cannot merge meshes loaded from binary files')

    # Loading from binary files, but still need to use the .txt files as a
    # reference for the format:
    ib_bin_path, ib_txt_path = ib_paths[0]

    use_drawcall_range = False
    if hasattr(operator, 'load_buf_limit_range'): # Frame analysis import only
        use_drawcall_range = operator.load_buf_limit_range

    vb = VertexBufferGroup()
    vb.parse_vb_bin(vb_paths[0], use_drawcall_range)

    ib = None
    if ib_bin_path:
        ib = IndexBuffer(open(ib_txt_path, 'r'), load_indices=False)
        if ib.used_in_drawcall == False:
            operator.report({'WARNING'}, '{}: Discarding index buffer not used in draw call'.format(os.path.basename(ib_bin_path)))
            ib = None
        else:
            ib.parse_ib_bin(open(ib_bin_path, 'rb'), use_drawcall_range)

    return vb, ib, os.path.basename(vb_paths[0][0][0]), pose_path

def load_3dmigoto_mesh(operator, paths):
    vb_paths, ib_paths, use_bin, pose_path = zip(*paths)
    pose_path = pose_path[0]

    if use_bin[0]:
        return load_3dmigoto_mesh_bin(operator, vb_paths, ib_paths, pose_path)

    vb = VertexBufferGroup(vb_paths[0])
    # Merge additional vertex buffers for meshes split over multiple draw calls:
    for vb_path in vb_paths[1:]:
        tmp = VertexBufferGroup(vb_path)
        vb.merge(tmp)

    # For quickly testing how importent any unsupported semantics may be:
    #vb.wipe_semantic_for_testing('POSITION.w', 1.0)
    #vb.wipe_semantic_for_testing('TEXCOORD.w', 0.0)
    #vb.wipe_semantic_for_testing('TEXCOORD5', 0)
    #vb.wipe_semantic_for_testing('BINORMAL')
    #vb.wipe_semantic_for_testing('TANGENT')
    #vb.write(open(os.path.join(os.path.dirname(vb_paths[0]), 'TEST.vb'), 'wb'), operator=operator)

    ib = None
    if ib_paths and ib_paths != (None,):
        ib = IndexBuffer(open(ib_paths[0], 'r'))
        # Merge additional vertex buffers for meshes split over multiple draw calls:
        for ib_path in ib_paths[1:]:
            tmp = IndexBuffer(open(ib_path, 'r'))
            ib.merge(tmp)
        if ib.used_in_drawcall == False:
            operator.report({'WARNING'}, '{}: Discarding index buffer not used in draw call'.format(os.path.basename(ib_paths[0])))
            ib = None

    return vb, ib, os.path.basename(vb_paths[0][0]), pose_path

def normal_import_translation(elem, flip):
    unorm = elem.Format.endswith('_UNORM')
    if unorm:
        # Scale UNORM range 0:+1 to normal range -1:+1
        if flip:
            return lambda x: -(x*2.0 - 1.0)
        else:
            return lambda x: x*2.0 - 1.0
    if flip:
        return lambda x: -x
    else:
        return lambda x: x

def normal_export_translation(layout, semantic, flip):
    try:
        unorm = layout.untranslate_semantic(semantic).Format.endswith('_UNORM')
    except KeyError:
        unorm = False
    if unorm:
        # Scale normal range -1:+1 to UNORM range 0:+1
        if flip:
            return lambda x: -x/2.0 + 0.5
        else:
            return lambda x: x/2.0 + 0.5
    if flip:
        return lambda x: -x
    else:
        return lambda x: x

def import_normals_step1(mesh, data, vertex_layers, operator, translate_normal, flip_mesh):
    # Ensure normals are 3-dimensional:
    # XXX: Assertion triggers in DOA6
    if len(data[0]) == 4:
        if [x[3] for x in data] != [0.0]*len(data):
            #raise Fatal('Normals are 4D')
            operator.report({'WARNING'}, 'Normals are 4D, storing W coordinate in NORMAL.w vertex layer. Beware that some types of edits on this mesh may be problematic.')
            vertex_layers['NORMAL.w'] = [[x[3]] for x in data]
    normals = [tuple(map(translate_normal, (-(2*flip_mesh-1)*x[0], x[1], x[2]))) for x in data]

    # To make sure the normals don't get lost by Blender's edit mode,
    # or mesh.update() we need to set custom normals in the loops, not
    # vertices.
    #
    # For testing, to make sure our normals are preserved let's use
    # garbage ones:
    #import random
    #normals = [(random.random() * 2 - 1,random.random() * 2 - 1,random.random() * 2 - 1) for x in normals]
    #
    # Comment from other import scripts:
    # Note: we store 'temp' normals in loops, since validate() may alter final mesh,
    #       we can only set custom lnors *after* calling it.
    if bpy.app.version >= (4, 1):
        return normals
    mesh.create_normals_split()
    for l in mesh.loops:
        l.normal[:] = normals[l.vertex_index]
    return []

def import_normals_step2(mesh):
    # Taken from import_obj/import_fbx
    clnors = array('f', [0.0] * (len(mesh.loops) * 3))
    mesh.loops.foreach_get("normal", clnors)

    # Not sure this is still required with use_auto_smooth, but the other
    # importers do it, and at the very least it shouldn't hurt...
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))

    mesh.normals_split_custom_set(tuple(zip(*(iter(clnors),) * 3)))
    mesh.use_auto_smooth = True # This has a double meaning, one of which is to use the custom normals
    # XXX CHECKME: show_edge_sharp moved in 2.80, but I can't actually
    # recall what it does and have a feeling it was unimportant:
    #mesh.show_edge_sharp = True

def import_vertex_groups(mesh, obj, blend_indices, blend_weights):
    assert(len(blend_indices) == len(blend_weights))
    if blend_indices:
        # We will need to make sure we re-export the same blend indices later -
        # that they haven't been renumbered. Not positive whether it is better
        # to use the vertex group index, vertex group name or attach some extra
        # data. Make sure the indices and names match:
        num_vertex_groups = max(itertools.chain(*itertools.chain(*blend_indices.values()))) + 1
        for i in range(num_vertex_groups):
            obj.vertex_groups.new(name=str(i))
        for vertex in mesh.vertices:
            for semantic_index in sorted(blend_indices.keys()):
                for i, w in zip(blend_indices[semantic_index][vertex.index], blend_weights[semantic_index][vertex.index]):
                    if w == 0.0:
                        continue
                    obj.vertex_groups[i].add((vertex.index,), w, 'REPLACE')
def import_uv_layers(mesh, obj, texcoords, flip_texcoord_v):
    for (texcoord, data) in sorted(texcoords.items()):
        # TEXCOORDS can have up to four components, but UVs can only have two
        # dimensions. Not positive of the best way to handle this in general,
        # but for now I'm thinking that splitting the TEXCOORD into two sets of
        # UV coordinates might work:
        dim = len(data[0])
        if dim == 4:
            components_list = ('xy', 'zw')
        elif dim == 3:
            components_list = ('xy', 'z')
        elif dim == 2:
            components_list = ('xy',)
        elif dim == 1:
            components_list = ('x',)
        else:
            raise Fatal('Unhandled TEXCOORD%s dimension: %i' % (texcoord, dim))
        cmap = {'x': 0, 'y': 1, 'z': 2, 'w': 3}

        for components in components_list:
            uv_name = 'TEXCOORD%s.%s' % (texcoord and texcoord or '', components)
            if hasattr(mesh, 'uv_textures'): # 2.79
                mesh.uv_textures.new(uv_name)
            else: # 2.80
                mesh.uv_layers.new(name=uv_name)
            blender_uvs = mesh.uv_layers[uv_name]

            # This will assign a texture to the UV layer, which works fine but
            # working out which texture maps to which UV layer is guesswork
            # before the import and the artist may as well just assign it
            # themselves in the UV editor pane when they can see the unwrapped
            # mesh to compare it with the dumped textures:
            #
            #path = textures.get(uv_layer, None)
            #if path is not None:
            #    image = load_image(path)
            #    for i in range(len(mesh.polygons)):
            #        mesh.uv_textures[uv_layer].data[i].image = image

            # Can't find an easy way to flip the display of V in Blender, so
            # add an option to flip it on import & export:
            if (len(components) % 2 == 1):
                # 1D or 3D TEXCOORD, save in a UV layer with V=0
                translate_uv = lambda u: (u[0], 0)
            elif flip_texcoord_v:
                translate_uv = lambda uv: (uv[0], 1.0 - uv[1])
                # Record that V was flipped so we know to undo it when exporting:
                obj['3DMigoto:' + uv_name] = {'flip_v': True}
            else:
                translate_uv = lambda uv: uv

            uvs = [[d[cmap[c]] for c in components] for d in data]
            for l in mesh.loops:
                blender_uvs.data[l.index].uv = translate_uv(uvs[l.vertex_index])

def new_custom_attribute_int(mesh, layer_name):
    # vertex_layers were dropped in 4.0. Looks like attributes were added in
    # 3.0 (to confirm), so we could probably start using them or add a
    # migration function on older versions as well
    if bpy.app.version >= (4, 0):
        mesh.attributes.new(name=layer_name, type='INT', domain='POINT')
        return mesh.attributes[layer_name]
    else:
        mesh.vertex_layers_int.new(name=layer_name)
        return mesh.vertex_layers_int[layer_name]

def new_custom_attribute_float(mesh, layer_name):
    if bpy.app.version >= (4, 0):
        # TODO: float2 and float3 could be stored directly as 'FLOAT2' /
        # 'FLOAT_VECTOR' types (in fact, UV layers in 4.0 show up in attributes
        # using FLOAT2) instead of saving each component as a separate layer.
        # float4 is missing though. For now just get it working equivelently to
        # the old vertex layers.
        mesh.attributes.new(name=layer_name, type='FLOAT', domain='POINT')
        return mesh.attributes[layer_name]
    else:
        mesh.vertex_layers_float.new(name=layer_name)
        return mesh.vertex_layers_float[layer_name]

# TODO: Refactor to prefer attributes over vertex layers even on 3.x if they exist
def custom_attributes_int(mesh):
    if bpy.app.version >= (4, 0):
        return { k: v for k,v in mesh.attributes.items()
                if (v.data_type, v.domain) == ('INT', 'POINT') }
    else:
        return mesh.vertex_layers_int

def custom_attributes_float(mesh):
    if bpy.app.version >= (4, 0):
        return { k: v for k,v in mesh.attributes.items()
                if (v.data_type, v.domain) == ('FLOAT', 'POINT') }
    else:
        return mesh.vertex_layers_float

# This loads unknown data from the vertex buffers as vertex layers
def import_vertex_layers(mesh, obj, vertex_layers):
    for (element_name, data) in sorted(vertex_layers.items()):
        dim = len(data[0])
        cmap = {0: 'x', 1: 'y', 2: 'z', 3: 'w'}
        for component in range(dim):

            if dim != 1 or element_name.find('.') == -1:
                layer_name = '%s.%s' % (element_name, cmap[component])
            else:
                layer_name = element_name

            if type(data[0][0]) == int:
                layer = new_custom_attribute_int(mesh, layer_name)
                for v in mesh.vertices:
                    val = data[v.index][component]
                    # Blender integer layers are 32bit signed and will throw an
                    # exception if we are assigning an unsigned value that
                    # can't fit in that range. Reinterpret as signed if necessary:
                    if val < 0x80000000:
                        layer.data[v.index].value = val
                    else:
                        layer.data[v.index].value = struct.unpack('i', struct.pack('I', val))[0]
            elif type(data[0][0]) == float:
                layer = new_custom_attribute_float(mesh, layer_name)
                for v in mesh.vertices:
                    layer.data[v.index].value = data[v.index][component]
            else:
                raise Fatal('BUG: Bad layer type %s' % type(data[0][0]))

def import_faces_from_ib(mesh, ib, flip_winding):
    mesh.loops.add(len(ib.faces) * 3)
    mesh.polygons.add(len(ib.faces))
    if flip_winding:
        mesh.loops.foreach_set('vertex_index', unpack_list(map(reversed, ib.faces)))
    else:
        mesh.loops.foreach_set('vertex_index', unpack_list(ib.faces))
    mesh.polygons.foreach_set('loop_start', [x*3 for x in range(len(ib.faces))])
    mesh.polygons.foreach_set('loop_total', [3] * len(ib.faces))

def import_faces_from_vb_trianglelist(mesh, vb, flip_winding):
    # Only lightly tested
    num_faces = len(vb.vertices) // 3
    mesh.loops.add(num_faces * 3)
    mesh.polygons.add(num_faces)
    if flip_winding:
        raise Fatal('Flipping winding order untested without index buffer') # export in particular needs support
        mesh.loops.foreach_set('vertex_index', [x for x in reversed(range(num_faces * 3))])
    else:
        mesh.loops.foreach_set('vertex_index', [x for x in range(num_faces * 3)])
    mesh.polygons.foreach_set('loop_start', [x*3 for x in range(num_faces)])
    mesh.polygons.foreach_set('loop_total', [3] * num_faces)

def import_faces_from_vb_trianglestrip(mesh, vb, flip_winding):
    # Only lightly tested
    if flip_winding:
        raise Fatal('Flipping winding order with triangle strip topology is not implemented')
    num_faces = len(vb.vertices) - 2
    if num_faces <= 0:
        raise Fatal('Insufficient vertices in trianglestrip')
    mesh.loops.add(num_faces * 3)
    mesh.polygons.add(num_faces)

    # Every 2nd face has the vertices out of order to keep all faces in the same orientation:
    # https://learn.microsoft.com/en-us/windows/win32/direct3d9/triangle-strips
    tristripindex = [( i,
        i%2 and i+2 or i+1,
        i%2 and i+1 or i+2,
    ) for i in range(num_faces) ]

    mesh.loops.foreach_set('vertex_index', unpack_list(tristripindex))
    mesh.polygons.foreach_set('loop_start', [x*3 for x in range(num_faces)])
    mesh.polygons.foreach_set('loop_total', [3] * num_faces)

def import_vertices(mesh, obj, vb, operator, semantic_translations={}, flip_normal=False, flip_mesh=False):
    mesh.vertices.add(len(vb.vertices))

    blend_indices = {}
    blend_weights = {}
    texcoords = {}
    vertex_layers = {}
    use_normals = False
    normals = []

    for elem in vb.layout:
        if elem.InputSlotClass != 'per-vertex' or elem.reused_offset:
            continue

        if elem.InputSlot not in vb.slots:
            # UE4 known to proclaim it has attributes in all the slots in the
            # layout description, but only ends up using two (and one of those
            # is per-instance data)
            print('NOTICE: Vertex semantic %s unavailable due to missing vb%i' % (elem.name, elem.InputSlot))
            continue

        translated_elem_name, translated_elem_index = \
                semantic_translations.get(elem.name, (elem.name, elem.SemanticIndex))

        # Some games don't follow the official DirectX UPPERCASE semantic naming convention:
        translated_elem_name = translated_elem_name.upper()

        data = tuple( x[elem.name] for x in vb.vertices )
        if translated_elem_name == 'POSITION':
            # Ensure positions are 3-dimensional:
            if len(data[0]) == 4:
                if ([x[3] for x in data] != [1.0]*len(data)):
                    # XXX: There is a 4th dimension in the position, which may
                    # be some artibrary custom data, or maybe something weird
                    # is going on like using Homogeneous coordinates in a
                    # vertex buffer. The meshes this triggers on in DOA6
                    # (skirts) lie about almost every semantic and we cannot
                    # import them with this version of the script regardless.
                    # But perhaps in some cases it might still be useful to be
                    # able to import as much as we can and just preserve this
                    # unknown 4th dimension to export it later or have a game
                    # specific script perform some operations on it - so we
                    # store it in a vertex layer and warn the modder.
                    operator.report({'WARNING'}, 'Positions are 4D, storing W coordinate in POSITION.w vertex layer. Beware that some types of edits on this mesh may be problematic.')
                    vertex_layers['POSITION.w'] = [[x[3]] for x in data]
            positions = [(-(2*flip_mesh-1)*x[0], x[1], x[2]) for x in data]
            mesh.vertices.foreach_set('co', unpack_list(positions))
        elif translated_elem_name.startswith('COLOR'):
            if len(data[0]) <= 3 or vertex_color_layer_channels == 4:
                # Either a monochrome/RGB layer, or Blender 2.80 which uses 4
                # channel layers
                mesh.vertex_colors.new(name=elem.name)
                color_layer = mesh.vertex_colors[elem.name].data
                c = vertex_color_layer_channels
                for l in mesh.loops:
                    color_layer[l.index].color = list(data[l.vertex_index]) + [0]*(c-len(data[l.vertex_index]))
            else:
                mesh.vertex_colors.new(name=elem.name + '.RGB')
                mesh.vertex_colors.new(name=elem.name + '.A')
                color_layer = mesh.vertex_colors[elem.name + '.RGB'].data
                alpha_layer = mesh.vertex_colors[elem.name + '.A'].data
                for l in mesh.loops:
                    color_layer[l.index].color = data[l.vertex_index][:3]
                    alpha_layer[l.index].color = [data[l.vertex_index][3], 0, 0]
        elif translated_elem_name == 'NORMAL':
            use_normals = True
            translate_normal = normal_import_translation(elem, flip_normal)
            normals = import_normals_step1(mesh, data, vertex_layers, operator, translate_normal, flip_mesh)     
        elif translated_elem_name in ('TANGENT', 'BINORMAL'):
        #    # XXX: loops.tangent is read only. Not positive how to handle
        #    # this, or if we should just calculate it when re-exporting.
        #    for l in mesh.loops:
        #        FIXME: rescale range if elem.Format.endswith('_UNORM')
        #        assert(data[l.vertex_index][3] in (1.0, -1.0))
        #        l.tangent[:] = data[l.vertex_index][0:3]
            operator.report({'INFO'}, 'Skipping import of %s in favour of recalculating on export' % elem.name)
        elif translated_elem_name.startswith('BLENDINDICES'):
            blend_indices[translated_elem_index] = data
        elif translated_elem_name.startswith('BLENDWEIGHT'):
            blend_weights[translated_elem_index] = data
        elif translated_elem_name.startswith('TEXCOORD') and elem.is_float():
            texcoords[translated_elem_index] = data
        else:
            operator.report({'INFO'}, 'Storing unhandled semantic %s %s as vertex layer' % (elem.name, elem.Format))
            vertex_layers[elem.name] = data

    return (blend_indices, blend_weights, texcoords, vertex_layers, use_normals, normals)

def import_3dmigoto(operator, context, paths, merge_meshes=True, **kwargs):
    if merge_meshes:
        return import_3dmigoto_vb_ib(operator, context, paths, **kwargs)
    else:
        obj = []
        for p in paths:
            try:
                obj.append(import_3dmigoto_vb_ib(operator, context, [p], **kwargs))
            except Fatal as e:
                operator.report({'ERROR'}, str(e) + ': ' + str(p[:2]))
        # FIXME: Group objects together
        return obj

def assert_pointlist_ib_is_pointless(ib, vb):
    # Index Buffers are kind of pointless with point list topologies, because
    # the advantages they offer for triangle list topologies don't really
    # apply and there is little point in them being used at all... But, there
    # is nothing technically stopping an engine from using them regardless, and
    # we do see this in One Piece Burning Blood. For now, just verify that the
    # index buffers are the trivial case that lists every vertex in order, and
    # just ignore them since we already loaded the vertex buffer in that order.
    assert(len(vb) == len(ib)) # FIXME: Properly implement point list index buffers
    assert(all([(i,) == j for i,j in enumerate(ib.faces)])) # FIXME: Properly implement point list index buffers

def import_3dmigoto_vb_ib(operator, context, paths, flip_texcoord_v=True, flip_winding=False, flip_mesh=False, flip_normal=False, axis_forward='-Z', axis_up='Y', pose_cb_off=[0,0], pose_cb_step=1, merge_verts=False, tris_to_quads=False, clean_loose=False):
    vb, ib, name, pose_path = load_3dmigoto_mesh(operator, paths)

    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(mesh.name, mesh)

    global_matrix = axis_conversion(from_forward=axis_forward, from_up=axis_up).to_4x4()
    obj.matrix_world = global_matrix

    if hasattr(operator.properties, 'semantic_remap'):
        semantic_translations = vb.layout.apply_semantic_remap(operator)
    else:
        semantic_translations = vb.layout.get_semantic_remap()

    # Attach the vertex buffer layout to the object for later exporting. Can't
    # seem to retrieve this if attached to the mesh - to_mesh() doesn't copy it:
    obj['3DMigoto:VBLayout'] = vb.layout.serialise()
    obj['3DMigoto:Topology'] = vb.topology
    for raw_vb in vb.vbs:
        obj['3DMigoto:VB%iStride' % raw_vb.idx] = raw_vb.stride
    obj['3DMigoto:FirstVertex'] = vb.first
    # Record these import options so the exporter can set them to match by
    # default. Might also consider adding them to the .fmt file so reimporting
    # a previously exported file can also set them by default?
    obj['3DMigoto:FlipWinding'] = flip_winding
    obj['3DMigoto:FlipNormal'] = flip_normal
    obj['3DMigoto:FlipMesh'] = flip_mesh
    if flip_mesh:
        flip_winding = not flip_winding

    if ib is not None:
        if ib.topology in ('trianglelist', 'trianglestrip'):
            import_faces_from_ib(mesh, ib, flip_winding)
        elif ib.topology == 'pointlist':
            assert_pointlist_ib_is_pointless(ib, vb)
        else:
            raise Fatal('Unsupported topology (IB): {}'.format(ib.topology))
        # Attach the index buffer layout to the object for later exporting.
        obj['3DMigoto:IBFormat'] = ib.format
        obj['3DMigoto:FirstIndex'] = ib.first
    elif vb.topology == 'trianglelist':
        import_faces_from_vb_trianglelist(mesh, vb, flip_winding)
    elif vb.topology == 'trianglestrip':
        import_faces_from_vb_trianglestrip(mesh, vb, flip_winding)
    elif vb.topology != 'pointlist':
        raise Fatal('Unsupported topology (VB): {}'.format(vb.topology))
    if vb.topology == 'pointlist':
        operator.report({'WARNING'}, '{}: uses point list topology, which is highly experimental and may have issues with normals/tangents/lighting. This may not be the mesh you are looking for.'.format(mesh.name))

    (blend_indices, blend_weights, texcoords, vertex_layers, use_normals, normals) = import_vertices(mesh, obj, vb, operator, semantic_translations, flip_normal, flip_mesh)

    import_uv_layers(mesh, obj, texcoords, flip_texcoord_v)
    if not texcoords:
        operator.report({'WARNING'}, '{}: No TEXCOORDs / UV layers imported. This may cause issues with normals/tangents/lighting on export.'.format(mesh.name))

    import_vertex_layers(mesh, obj, vertex_layers)

    import_vertex_groups(mesh, obj, blend_indices, blend_weights)

    # Validate closes the loops so they don't disappear after edit mode and probably other important things:
    mesh.validate(verbose=False, clean_customdata=False)  # *Very* important to not remove lnors here!
    # Not actually sure update is necessary. It seems to update the vertex normals, not sure what else:
    mesh.update()

    # Must be done after validate step:
    if use_normals:
        if bpy.app.version >= (4, 1):
            mesh.normals_split_custom_set_from_vertices(normals)
        else:
            import_normals_step2(mesh)
    elif hasattr(mesh, 'calc_normals'): # Dropped in Blender 4.0
        mesh.calc_normals()

    link_object_to_scene(context, obj)
    select_set(obj, True)
    set_active_object(context, obj)
    
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    if merge_verts:
        bpy.ops.mesh.remove_doubles(use_sharp_edge_from_normals=True)
    if tris_to_quads:
        bpy.ops.mesh.tris_convert_to_quads(uvs=True, vcols=True, seam=True, sharp=True, materials=True)
    if clean_loose:
        bpy.ops.mesh.delete_loose()
    bpy.ops.object.mode_set(mode='OBJECT')

    return obj

# from export_obj:
def mesh_triangulate(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()

def blender_vertex_to_3dmigoto_vertex(mesh, obj, blender_loop_vertex, layout, texcoords, blender_vertex, translate_normal, translate_tangent, export_outline=None):
    if blender_loop_vertex is not None:
        blender_vertex = mesh.vertices[blender_loop_vertex.vertex_index]
    vertex = {}    
    blp_normal = list(blender_loop_vertex.normal)

    # TODO: Warn if vertex is in too many vertex groups for this layout,
    # ignoring groups with weight=0.0
    vertex_groups = sorted(blender_vertex.groups, key=lambda x: x.weight, reverse=True)

    for elem in layout:
        if elem.InputSlotClass != 'per-vertex' or elem.reused_offset:
            continue

        semantic_translations = layout.get_semantic_remap()
        translated_elem_name, translated_elem_index = \
                semantic_translations.get(elem.name, (elem.name, elem.SemanticIndex))

        # Some games don't follow the official DirectX UPPERCASE semantic naming convention:
        translated_elem_name = translated_elem_name.upper()

        if translated_elem_name == 'POSITION':
            if 'POSITION.w' in custom_attributes_float(mesh):
                vertex[elem.name] = list(blender_vertex.undeformed_co) + \
                                        [custom_attributes_float(mesh)['POSITION.w'].data[blender_vertex.index].value]
            else:
                vertex[elem.name] = elem.pad(list(blender_vertex.undeformed_co), 1.0)
        elif translated_elem_name.startswith('COLOR'):
            if elem.name in mesh.vertex_colors:
                vertex[elem.name] = elem.clip(list(mesh.vertex_colors[elem.name].data[blender_loop_vertex.index].color))
            else:
                vertex[elem.name] = list(mesh.vertex_colors[elem.name+'.RGB'].data[blender_loop_vertex.index].color)[:3] + \
                                        [mesh.vertex_colors[elem.name+'.A'].data[blender_loop_vertex.index].color[0]]
        elif translated_elem_name == 'NORMAL':
            if 'NORMAL.w' in custom_attributes_float(mesh):
                vertex[elem.name] = list(map(translate_normal, blender_loop_vertex.normal)) + \
                                        [custom_attributes_float(mesh)['NORMAL.w'].data[blender_vertex.index].value]
            elif blender_loop_vertex:
                vertex[elem.name] = elem.pad(list(map(translate_normal, blender_loop_vertex.normal)), 0.0)
            else:
                # XXX: point list topology, these normals are probably going to be pretty poor, but at least it's something to export
                vertex[elem.name] = elem.pad(list(map(translate_normal, blender_vertex.normal)), 0.0)
        elif translated_elem_name.startswith('TANGENT'):
            if export_outline:
                # Genshin optimized outlines
                vertex[elem.name] = elem.pad(list(map(translate_tangent, export_outline.get(blender_loop_vertex.vertex_index, blp_normal))), blender_loop_vertex.bitangent_sign)
            # DOAXVV has +1/-1 in the 4th component. Not positive what this is,
            # but guessing maybe the bitangent sign? Not even sure it is used...
            # FIXME: Other games
            elif blender_loop_vertex:
                vertex[elem.name] = elem.pad(list(map(translate_tangent, blender_loop_vertex.tangent)), blender_loop_vertex.bitangent_sign)
            else:
                # XXX Blender doesn't save tangents outside of loops, so unless
                # we save these somewhere custom when importing they are
                # effectively lost. We could potentially calculate a tangent
                # from blender_vertex.normal, but there is probably little
                # point given that normal will also likely be garbage since it
                # wasn't imported from the mesh.
                pass
        elif translated_elem_name.startswith('BINORMAL'):
            # Some DOA6 meshes (skirts) use BINORMAL, but I'm not certain it is
            # actually the binormal. These meshes are weird though, since they
            # use 4 dimensional positions and normals, so they aren't something
            # we can really deal with at all. Therefore, the below is untested,
            # FIXME: So find a mesh where this is actually the binormal,
            # uncomment the below code and test.
            # normal = blender_loop_vertex.normal
            # tangent = blender_loop_vertex.tangent
            # binormal = numpy.cross(normal, tangent)
            # XXX: Does the binormal need to be normalised to a unit vector?
            # binormal = binormal / numpy.linalg.norm(binormal)
            # vertex[elem.name] = elem.pad(list(map(translate_binormal, binormal)), 0.0)
            pass
        elif translated_elem_name.startswith('BLENDINDICES'):
            i = translated_elem_index * 4
            vertex[elem.name] = elem.pad([ x.group for x in vertex_groups[i:i+4] ], 0)
        elif translated_elem_name.startswith('BLENDWEIGHT'):
            # TODO: Warn if vertex is in too many vertex groups for this layout
            i = translated_elem_index * 4
            vertex[elem.name] = elem.pad([ x.weight for x in vertex_groups[i:i+4] ], 0.0)
        elif translated_elem_name.startswith('TEXCOORD') and elem.is_float():
            uvs = []
            for uv_name in ('%s.xy' % elem.remapped_name, '%s.zw' % elem.remapped_name):
                if uv_name in texcoords:
                    uvs += list(texcoords[uv_name][blender_loop_vertex.index])
            # Handle 1D + 3D TEXCOORDs. Order is important - 1D TEXCOORDs won't
            # match anything in above loop so only .x below, 3D TEXCOORDS will
            # have processed .xy part above, and .z part below
            for uv_name in ('%s.x' % elem.remapped_name, '%s.z' % elem.remapped_name):
                if uv_name in texcoords:
                    uvs += [texcoords[uv_name][blender_loop_vertex.index].x]
            vertex[elem.name] = uvs
        else:
            # Unhandled semantics are saved in vertex layers
            data = []
            for component in 'xyzw':
                layer_name = '%s.%s' % (elem.name, component)
                if layer_name in custom_attributes_int(mesh):
                    data.append(custom_attributes_int(mesh)[layer_name].data[blender_vertex.index].value)
                elif layer_name in custom_attributes_float(mesh):
                    data.append(custom_attributes_float(mesh)[layer_name].data[blender_vertex.index].value)
            if data:
                #print('Retrieved unhandled semantic %s %s from vertex layer' % (elem.name, elem.Format), data)
                vertex[elem.name] = data

        if elem.name not in vertex:
            print('NOTICE: Unhandled vertex element: %s' % elem.name)
        #else:
        #    print('%s: %s' % (elem.name, repr(vertex[elem.name])))

    return vertex

def write_fmt_file(f, vb, ib, strides):
    for vbuf_idx, stride in strides.items():
        if vbuf_idx.isnumeric():
            f.write('vb%s stride: %i\n' % (vbuf_idx, stride))
        else:
            f.write('stride: %i\n' % stride)
    f.write('topology: %s\n' % vb.topology)
    if ib is not None:
        f.write('format: %s\n' % ib.format)
    f.write(vb.layout.to_string())

class FALogFile(object):
    '''
    Class that is able to parse frame analysis log files, query bound resource
    state at the time of a given draw call, and search for resource usage.

    TODO: Support hold frame analysis log files that include multiple frames
    TODO: Track bound shaders
    TODO: Merge deferred context log files into main log file
    TODO: Track CopyResource / other ways resources can be updated
    '''
    ResourceUse = collections.namedtuple('ResourceUse', ['draw_call', 'slot_type', 'slot'])
    class SparseSlots(dict):
        '''
        Allows the resources bound in each slot to be stored + queried by draw
        call. There can be gaps with draw calls that don't change any of the
        given slot type, in which case it will return the slots in the most
        recent draw call that did change that slot type.

        Requesting a draw call higher than any seen so far will return a *copy*
        of the most recent slots, intended for modification during parsing.
        '''
        def __init__(self):
            dict.__init__(self, {0: {}})
            self.last_draw_call = 0
        def prev_draw_call(self, draw_call):
            return max([ i for i in self.keys() if i < draw_call ])
        #def next_draw_call(self, draw_call):
        #    return min([ i for i in self.keys() if i > draw_call ])
        def subsequent_draw_calls(self, draw_call):
            return [ i for i in sorted(self.keys()) if i >= draw_call ]
        def __getitem__(self, draw_call):
            if draw_call > self.last_draw_call:
                dict.__setitem__(self, draw_call, dict.__getitem__(self, self.last_draw_call).copy())
                self.last_draw_call = draw_call
            elif draw_call not in self.keys():
                return dict.__getitem__(self, self.prev_draw_call(draw_call))
            return dict.__getitem__(self, draw_call)

    class FALogParser(object):
        '''
        Base class implementing some common parsing functions
        '''
        pattern = None
        def parse(self, line, q, state):
            match = self.pattern.match(line)
            if match:
                remain = line[match.end():]
                self.matched(match, remain, q, state)
            return match
        def matched(self, match, remain, q, state):
            raise NotImplementedError()

    class FALogParserDrawcall(FALogParser):
        '''
        Parses a typical line in a frame analysis log file that begins with a
        draw call number. Additional parsers can be registered with this one to
        parse the remainder of such lines.
        '''
        pattern = re.compile(r'''^(?P<drawcall>\d+) ''')
        next_parsers_classes = []
        @classmethod
        def register(cls, parser):
            cls.next_parsers_classes.append(parser)
        def __init__(self, state):
            self.next_parsers = []
            for parser in self.next_parsers_classes:
                self.next_parsers.append(parser(state))
        def matched(self, match, remain, q, state):
            drawcall = int(match.group('drawcall'))
            state.draw_call = drawcall
            for parser in self.next_parsers:
                parser.parse(remain, q, state)

    class FALogParserBindResources(FALogParser):
        '''
        Base class for any parsers that bind resources (and optionally views)
        to the pipeline. Will consume all following lines matching the resource
        pattern and update the log file state and resource lookup index for the
        current draw call.
        '''
        resource_pattern = re.compile(r'''^\s+(?P<slot>[0-9D]+): (?:view=(?P<view>0x[0-9A-F]+) )?resource=(?P<address>0x[0-9A-F]+) hash=(?P<hash>[0-9a-f]+)$''', re.MULTILINE)
        FALogResourceBinding = collections.namedtuple('FALogResourceBinding', ['slot', 'view_address', 'resource_address', 'resource_hash'])
        slot_prefix = None
        bind_clears_all_slots = False
        def __init__(self, state):
            if self.slot_prefix is None:
                raise NotImplementedError()
            self.sparse_slots = FALogFile.SparseSlots()
            state.slot_class[self.slot_prefix] = self.sparse_slots
        def matched(self, api_match, remain, q, state):
            if self.bind_clears_all_slots:
                self.sparse_slots[state.draw_call].clear()
            else:
                start_slot = self.start_slot(api_match)
                for i in range(self.num_bindings(api_match)):
                    self.sparse_slots[state.draw_call].pop(start_slot + i, None)
            bindings = self.sparse_slots[state.draw_call]
            while self.resource_pattern.match(q[0]):
                # FIXME: Inefficiently calling match twice. I hate that Python
                # lacks a do/while and every workaround is ugly in some way.
                resource_match = self.resource_pattern.match(q.popleft())
                slot = resource_match.group('slot')
                if slot.isnumeric(): slot = int(slot)
                view = resource_match.group('view')
                if view: view = int(view, 16)
                address = int(resource_match.group('address'), 16)
                resource_hash = int(resource_match.group('hash'), 16)
                bindings[slot] = self.FALogResourceBinding(slot, view, address, resource_hash)
                state.resource_index[address].add(FALogFile.ResourceUse(state.draw_call, self.slot_prefix, slot))
            #print(sorted(bindings.items()))
        def start_slot(self, match):
            return int(match.group('StartSlot'))
        def num_bindings(self, match):
            return int(match.group('NumBindings'))

    class FALogParserSOSetTargets(FALogParserBindResources):
        pattern = re.compile(r'''SOSetTargets\(.*\)$''')
        slot_prefix = 'so'
        bind_clears_all_slots = True
    FALogParserDrawcall.register(FALogParserSOSetTargets)

    class FALogParserIASetVertexBuffers(FALogParserBindResources):
        pattern = re.compile(r'''IASetVertexBuffers\(StartSlot:(?P<StartSlot>[0-9]+), NumBuffers:(?P<NumBindings>[0-9]+),.*\)$''')
        slot_prefix = 'vb'
    FALogParserDrawcall.register(FALogParserIASetVertexBuffers)



    def __init__(self, f):
        self.draw_call = None
        self.slot_class = {}
        self.resource_index = collections.defaultdict(set)
        draw_call_parser = self.FALogParserDrawcall(self)
        # Using a deque for a concise way to use a pop iterator and be able to
        # peek/consume the following line. Maybe overkill, but shorter code
        q = collections.deque(f)
        q.append(None)
        for line in iter(q.popleft, None):
            #print(line)
            if not draw_call_parser.parse(line, q, self):
                #print(line)
                pass

    def find_resource_uses(self, resource_address, slot_class=None):
        '''
        Find draw calls + slots where this resource is used.
        '''
        #return [ x for x in sorted(self.resource_index[resource_address]) if x.slot_type == slot_class ]
        ret = set()
        for bound in sorted(self.resource_index[resource_address]):
            if slot_class is not None and bound.slot_type != slot_class:
                continue
            # Resource was bound in this draw call, but could potentially have
            # been left bound in subsequent draw calls that we also want to
            # return, so return a range of draw calls if appropriate:
            sparse_slots = self.slot_class[bound.slot_type]
            for sparse_draw_call in sparse_slots.subsequent_draw_calls(bound.draw_call):
                if bound.slot not in sparse_slots[sparse_draw_call] \
                or sparse_slots[sparse_draw_call][bound.slot].resource_address != resource_address:
                    #print('x', sparse_draw_call, sparse_slots[sparse_draw_call][bound.slot])
                    for draw_call in range(bound.draw_call, sparse_draw_call):
                        ret.add(FALogFile.ResourceUse(draw_call, bound.slot_type, bound.slot))
                    break
                #print('y', sparse_draw_call, sparse_slots[sparse_draw_call][bound.slot])
            else:
                # I love Python's for/else clause. Means we didn't hit the
                # above break so the resource was still bound at end of frame
                for draw_call in range(bound.draw_call, self.draw_call):
                    ret.add(FALogFile.ResourceUse(draw_call, bound.slot_type, bound.slot))
        return ret

VBSOMapEntry = collections.namedtuple('VBSOMapEntry', ['draw_call', 'slot'])
def find_stream_output_vertex_buffers(log):
    vb_so_map = {}
    for so_draw_call, bindings in log.slot_class['so'].items():
        for so_slot, so in bindings.items():
            #print(so_draw_call, so_slot, so.resource_address)
            #print(list(sorted(log.find_resource_uses(so.resource_address, 'vb'))))
            for vb_draw_call, slot_type, vb_slot in log.find_resource_uses(so.resource_address, 'vb'):
                # NOTE: Recording the stream output slot here, but that won't
                # directly help determine which VB inputs we need from this
                # draw call (all of them, or just some?), but we might want
                # this slot if we write out an ini file for reinjection
                vb_so_map[VBSOMapEntry(vb_draw_call, vb_slot)] = VBSOMapEntry(so_draw_call, so_slot)
    #print(sorted(vb_so_map.items()))
    return vb_so_map

def open_frame_analysis_log_file(dirname):
    basename = os.path.basename(dirname)
    if basename.lower().startswith('ctx-0x'):
        context = basename[6:]
        path = os.path.join(dirname, '..', f'log-0x{context}.txt')
    else:
        path = os.path.join(dirname, 'log.txt')
    return FALogFile(open(path, 'r'))

def unit_vector(vector):
    a = numpy.linalg.norm(vector, axis=max(len(vector.shape)-1,0), keepdims=True)
    return numpy.divide(vector, a, out=numpy.zeros_like(vector), where= a!=0)

def antiparallel_search(ConnectedFaceNormals):
    a = numpy.einsum('ij,kj->ik', ConnectedFaceNormals, ConnectedFaceNormals)
    return numpy.any((a>-1.000001)&(a<-0.999999))

def precision(x): 
    return -int(numpy.floor(numpy.log10(x)))

def recursive_connections(Over2_connected_points):
    for entry, connectedpointentry in Over2_connected_points.items():
        if len(connectedpointentry & Over2_connected_points.keys()) < 2:
            Over2_connected_points.pop(entry)
            if len(Over2_connected_points) < 3:
                return False
            return recursive_connections(Over2_connected_points)
    return True
    
def checkEnclosedFacesVertex(ConnectedFaces, vg_set, Precalculated_Outline_data):
    
    Main_connected_points = {}
        # connected points non-same vertex
    for face in ConnectedFaces:
        non_vg_points = [p for p in face if p not in vg_set]
        if len(non_vg_points) > 1:
            for point in non_vg_points:
                Main_connected_points.setdefault(point, []).extend([x for x in non_vg_points if x != point])
        # connected points same vertex
    New_Main_connect = {}
    for entry, value in Main_connected_points.items():
        for val in value:
            ivspv = Precalculated_Outline_data.get('Same_Vertex').get(val)-{val}
            intersect_sidevertex = ivspv & Main_connected_points.keys()
            if intersect_sidevertex:
                New_Main_connect.setdefault(entry, []).extend(list(intersect_sidevertex))
        # connected points same vertex reverse connection
    for key, value in New_Main_connect.items():
        Main_connected_points.get(key).extend(value)
        for val in value:
            Main_connected_points.get(val).append(key)
        # exclude for only 2 way paths 
    Over2_connected_points = {k: set(v) for k, v in Main_connected_points.items() if len(v) > 1}

    return recursive_connections(Over2_connected_points)

def blender_vertex_to_3dmigoto_vertex_outline(mesh, obj, blender_loop_vertex, layout, texcoords, export_Outline):
    blender_vertex = mesh.vertices[blender_loop_vertex.vertex_index]
    pos = list(blender_vertex.undeformed_co)
    blp_normal = list(blender_loop_vertex.normal)
    vertex = {}
    seen_offsets = set()

    # TODO: Warn if vertex is in too many vertex groups for this layout,
    # ignoring groups with weight=0.0
    vertex_groups = sorted(blender_vertex.groups, key=lambda x: x.weight, reverse=True)

    for elem in layout:
        if elem.InputSlotClass != 'per-vertex':
            continue

        if (elem.InputSlot, elem.AlignedByteOffset) in seen_offsets:
            continue
        seen_offsets.add((elem.InputSlot, elem.AlignedByteOffset))

        if elem.name == 'POSITION':
            if 'POSITION.w' in mesh.vertex_layers_float:
                vertex[elem.name] = pos + [mesh.vertex_layers_float['POSITION.w'].data[blender_loop_vertex.vertex_index].value]
            else:
                vertex[elem.name] = elem.pad(pos, 1.0)
        elif elem.name.startswith('COLOR'):
            if elem.name in mesh.vertex_colors:
                vertex[elem.name] = elem.clip(list(mesh.vertex_colors[elem.name].data[blender_loop_vertex.index].color))
            else:
                try:
                    vertex[elem.name] = list(mesh.vertex_colors[elem.name+'.RGB'].data[blender_loop_vertex.index].color)[:3] + \
                                            [mesh.vertex_colors[elem.name+'.A'].data[blender_loop_vertex.index].color[0]]
                except KeyError:
                    raise Fatal("ERROR: Unable to find COLOR property. Ensure the model you are exporting has a color attribute (of type Face Corner/Byte Color) called COLOR")
        elif elem.name == 'NORMAL':
            vertex[elem.name] = elem.pad(blp_normal, 0.0)
        elif elem.name.startswith('TANGENT'):
            vertex[elem.name] = elem.pad(export_Outline.get(blender_loop_vertex.vertex_index, blp_normal), blender_loop_vertex.bitangent_sign)
        elif elem.name.startswith('BINORMAL'):
            pass
        elif elem.name.startswith('BLENDINDICES'):
            i = elem.SemanticIndex * 4
            vertex[elem.name] = elem.pad([ x.group for x in vertex_groups[i:i+4] ], 0)
        elif elem.name.startswith('BLENDWEIGHT'):
            # TODO: Warn if vertex is in too many vertex groups for this layout
            i = elem.SemanticIndex * 4
            vertex[elem.name] = elem.pad([ x.weight for x in vertex_groups[i:i+4] ], 0.0)
        elif elem.name.startswith('TEXCOORD') and elem.is_float():
            # FIXME: Handle texcoords of other dimensions
            uvs = []
            for uv_name in ('%s.xy' % elem.name, '%s.zw' % elem.name):
                if uv_name in texcoords:
                    uvs += list(texcoords[uv_name][blender_loop_vertex.index])

            vertex[elem.name] = uvs
        else:
            # Unhandled semantics are saved in vertex layers
            data = []
            for component in 'xyzw':
                layer_name = '%s.%s' % (elem.name, component)
                if layer_name in mesh.vertex_layers_int:
                    data.append(mesh.vertex_layers_int[layer_name].data[blender_loop_vertex.vertex_index].value)
                elif layer_name in mesh.vertex_layers_float:
                    data.append(mesh.vertex_layers_float[layer_name].data[blender_loop_vertex.vertex_index].value)
            if data:
                vertex[elem.name] = data

        if elem.name not in vertex:
            print('NOTICE: Unhandled vertex element: %s' % elem.name)

    return vertex

def appendto(collection, destination, depth=1):
    '''Append all meshes in a collection to a list'''
    objs = [obj for obj in collection.objects if obj.type == "MESH"]
    sorted_objs = sorted(objs, key=lambda x: x.name)
    for obj in sorted_objs:
        destination.append((collection.name, depth, obj))
    for a_collection in collection.children:
        appendto(a_collection, destination, depth + 1)

def join_into(context, collection_name, obj):
    '''Join all meshes in a collection into a single mesh'''
    target_obj = bpy.data.objects[obj]
    objects_to_join = []
    if collection_name is not None:
        appendto(bpy.data.collections[collection_name.name], objects_to_join)
    objects_to_join = [obj for obj in objects_to_join 
                        if obj.type == "MESH" and obj.visible_get()]
    objs = objects_to_join
    objs.append(target_obj)

    # apply shapekeys
    for ob in objs:
        ob.hide_viewport = False  # should be visible
        if ob.data.shape_keys:
            ob.shape_key_add(name='CombinedKeys', from_mix=True)
            for shape_key in ob.data.shape_keys.key_blocks:
                ob.shape_key_remove(shape_key)

    # apply modifiers
    count_mod_applied = 0
    count_mod_removed = 0
    for obj in objs:
        for modifier in obj.modifiers:
            if not modifier.show_viewport:
                obj.modifiers.remove(modifier)
                count_mod_removed += 1
            else:
                bpy.ops.object.select_all(action='DESELECT')
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.object.modifier_apply(modifier=modifier.name)
                count_mod_applied += 1
    print(f"Applied {count_mod_applied} modifiers and removed {count_mod_removed} modifiers")

    # join stuff
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objs:
        obj.select_set(True)
    context.view_layer.objects.active = target_obj
    bpy.ops.object.join()
    target_obj.data = bpy.context.object.data

    # Remove all vertex groups with the word MASK on them
    vgs = [vg for vg in target_obj.vertex_groups if "MASK" in vg.name]
    if len(vgs) > 0:
        for vg in vgs:
            target_obj.vertex_groups.remove(vg)
        print(f"Removed {len(vgs)} vertex groups with the word 'MASK' in them")

def collect_vb(folder, name, classification, strides):
    position_stride, blend_stride, texcoord_stride = strides
    position = bytearray()
    blend = bytearray()
    texcoord = bytearray()
    # FIXME: hardcoded .vb0 extension. This should be a flexible for multiple buffer export
    if not os.path.exists(os.path.join(folder, f"{name}{classification}.vb0")):
        return position, blend, texcoord
    with open(os.path.join(folder, f"{name}{classification}.vb0"), "rb") as f:
        data = f.read()
        data = bytearray(data)
        i = 0
        while i < len(data):
            position += data[i                               : i+(position_stride)]
            blend    += data[i+(position_stride)             : i+(position_stride+blend_stride)]
            texcoord += data[i+(position_stride+blend_stride): i+(position_stride+blend_stride+texcoord_stride)]
            i += position_stride+blend_stride+texcoord_stride

    return position, blend, texcoord

def collect_ib(folder, name, classification, offset):
    ib = bytearray()
    if not os.path.exists(os.path.join(folder, f"{name}{classification}.ib")):
        return ib
    with open(os.path.join(folder, f"{name}{classification}.ib"), "rb") as f:
        data = f.read()
        data = bytearray(data)
        i = 0
        while i < len(data):
            ib += struct.pack('1I', struct.unpack('1I', data[i:i+4])[0]+offset)
            i += 4
    return ib

def collect_vb_single(folder, name, classification, stride):
    result = bytearray()
    # FIXME: harcoded vb0. This should be flexible for multiple buffer export
    if not os.path.exists(os.path.join(folder, f"{name}{classification}.vb0")):
        return result
    with open(os.path.join(folder, f"{name}{classification}.vb0"), "rb") as f:
        data = f.read()
        data = bytearray(data)
        i = 0
        while i < len(data):
            result += data[i:i+stride]
            i += stride
    return result


# Parsing the headers for vb0 txt files
# This has been constructed by the collect script, so its headers are much more accurate than the originals
def parse_buffer_headers(headers, filters):
    results = []
    # https://docs.microsoft.com/en-us/windows/win32/api/dxgiformat/ne-dxgiformat-dxgi_format
    for element in headers.split("]:")[1:]:
        lines = element.strip().splitlines()
        name = lines[0].split(": ")[1]
        index = lines[1].split(": ")[1]
        data_format = lines[2].split(": ")[1]
        bytewidth = sum([int(x) for x in re.findall("([0-9]*)[^0-9]", data_format.split("_")[0]+"_") if x])//8

        # A bit annoying, but names can be very similar so need to match filter format exactly
        element_name = name
        if index != "0":
            element_name += index
        if element_name+":" not in filters:
            continue

        results.append({"semantic_name": name, "element_name": element_name, "index": index, "format": data_format, "bytewidth": bytewidth})

    return results


def import_3dmigoto_raw_buffers(operator, context, vb_fmt_path, ib_fmt_path, vb_path=None, ib_path=None, vgmap_path=None, **kwargs):
    paths = (ImportPaths(vb_paths=list(zip(vb_path, [vb_fmt_path]*len(vb_path))), ib_paths=(ib_path, ib_fmt_path), use_bin=True, pose_path=None),)
    obj = import_3dmigoto(operator, context, paths, merge_meshes=False, **kwargs)
    if obj and vgmap_path:
        apply_vgmap(operator, context, targets=obj, filepath=vgmap_path, rename=True, cleanup=True)

def apply_vgmap(operator, context, targets=None, filepath='', commit=False, reverse=False, suffix='', rename=False, cleanup=False):
    if not targets:
        targets = context.selected_objects

    if not targets:
        raise Fatal('No object selected')

    vgmap = json.load(open(filepath, 'r'))

    if reverse:
        vgmap = {int(v):int(k) for k,v in vgmap.items()}
    else:
        vgmap = {k:int(v) for k,v in vgmap.items()}

    for obj in targets:
        if commit:
            raise Fatal('commit not yet implemented')

        prop_name = '3DMigoto:VGMap:' + suffix
        obj[prop_name] = keys_to_strings(vgmap)

        if rename:
            for k,v in vgmap.items():
                if str(k) in obj.vertex_groups.keys():
                    continue
                if str(v) in obj.vertex_groups.keys():
                    obj.vertex_groups[str(v)].name = k
                else:
                    obj.vertex_groups.new(name=str(k))
        if cleanup:
            for vg in obj.vertex_groups:
                if vg.name not in vgmap:
                    obj.vertex_groups.remove(vg)

        if '3DMigoto:VBLayout' not in obj:
            operator.report({'WARNING'}, '%s is not a 3DMigoto mesh. Vertex Group Map custom property applied anyway' % obj.name)
        else:
            operator.report({'INFO'}, 'Applied vgmap to %s' % obj.name)

def update_vgmap(operator, context, vg_step=1):
    if not context.selected_objects:
        raise Fatal('No object selected')

    for obj in context.selected_objects:
        vgmaps = {k:keys_to_ints(v) for k,v in obj.items() if k.startswith('3DMigoto:VGMap:')}
        if not vgmaps:
            raise Fatal('Selected object has no 3DMigoto vertex group maps')
        for (suffix, vgmap) in vgmaps.items():
            highest = max(vgmap.values())
            for vg in obj.vertex_groups.keys():
                if vg.isdecimal():
                    continue
                if vg in vgmap:
                    continue
                highest += vg_step
                vgmap[vg] = highest
                operator.report({'INFO'}, 'Assigned named vertex group %s = %i' % (vg, vgmap[vg]))
            obj[suffix] = vgmap
