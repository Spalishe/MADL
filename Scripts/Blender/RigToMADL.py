# Made by Spalishe for github.com/Spalishe/MADL
# Before use it, Separate each rig mesh by materials, because MADL format dont support multiple materials
# on objects.
# Also bake all materials, because its finding for Image texture, connected to BSDF

import bpy
import mathutils
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator
import io
import random
import struct
import tempfile
import base64

def get_vertex_position_and_normal(obj, bone, vertex_index):
    """
    Gets the position and normal of a vertex relative to a bone.

    :param obj: The object with the mesh and armature.
    :param bone_name: The name of the bone relative to which the data should be retrieved.
    :param vertex_index: The index of the vertex to retrieve position and normal for.
    :return: A tuple of position (vector) and normal (vector) in local bone coordinates.
    """
    # Get the armature (if it exists)
    armature = obj.find_armature()
    if not armature:
        raise ValueError("The object does not have an armature.")

    # Get the vertex by index
    if vertex_index >= len(obj.data.vertices):
        raise IndexError("Invalid vertex index.")
    
    vertex = obj.data.vertices[vertex_index]

    # Get the vertex position in world coordinates
    world_pos = obj.matrix_world @ vertex.co

    # Get the vertex normal in world coordinates
    world_normal = obj.matrix_world.to_3x3() @ vertex.normal

    # Convert the position and normal to the local coordinates of the bone
    bone_matrix = bone.matrix
    local_pos = bone_matrix.inverted() @ world_pos
    local_normal = bone_matrix.inverted().to_3x3() @ world_normal

    return local_pos, local_normal

def get_base_color_texture_from_material(material):
    if not material.node_tree:
        raise ValueError(f"Material {material.name} has no nodes.")

    material_output_node = None
    for node in material.node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            material_output_node = node
            break

    if not material_output_node:
        raise ValueError(f"No Material Output node in {material.name}.")
        
    bsdf_node = None
    for node in material.node_tree.nodes:
        for input_socket in node.inputs:
            if input_socket.is_linked:
                if node.type == 'BSDF_PRINCIPLED':
                    bsdf_node = node
                    break
        if bsdf_node:
            break

    if not bsdf_node:
        raise ValueError(f"No BSDF node found in {material.name}.")

    base_color_input = bsdf_node.inputs.get("Base Color")
    if base_color_input and base_color_input.is_linked:
        image_texture_node = base_color_input.links[0].from_node
        if image_texture_node.type == 'TEX_IMAGE':
            image = image_texture_node.image

            temp_file = tempfile.gettempdir() + "/base_color_texture.png"
            image.filepath_raw = temp_file
            image.file_format = 'PNG'
            image.save()

            with open(temp_file, "rb") as f:
                base64_str = base64.b64encode(f.read()).decode('utf-8')

            return base64_str

    return None

def get_objects_parented_to_rig(rig):
    parented_objects = []

    for obj in bpy.context.scene.objects:
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object == rig:
                parented_objects.append(obj)
                break

    return parented_objects

def get_vertex_uvs(obj):
    if not obj.data.uv_layers:
        return None
    
    uv_layer = obj.data.uv_layers.active.data
    tbl = {}    
    for loop in obj.data.loops:
        tbl[loop.vertex_index] = uv_layer[loop.index].uv
    
    return tbl

def writeMADL(self,context, filepath):
    MST = madl_st()
    CHCKSUM = random.randint(-2147483648,2147483647)
    MST.checksum = CHCKSUM

    selected_objs = bpy.context.selected_objects
    rigs = [obj for obj in selected_objs if obj.type == 'ARMATURE']

    if len(rigs) > 1:
        self.report({'ERROR'},"Selected more than one rig.")
        return {'CANCELLED'}

    if len(rigs) == 1:
        rig = rigs[0]
        mesh_objs = get_objects_parented_to_rig(rig)
        
        MST.name = list(rig.name.encode("utf-8").ljust(32,b"\x00").decode("utf-8"))
        
        mesh_to_obj = {}
        for obj in mesh_objs:
            mesh_to_obj[obj.data] = obj
        
        objects_uvs = {}
        for obj in mesh_objs:
            objects_uvs[obj] = get_vertex_uvs(obj)
        
        # TEXTURES
        texture_table = []
        for obj in mesh_objs:
            if len(obj.material_slots) == 0:
                continue
            slot = obj.material_slots[0]
            mat = slot.material
            get_base_color_texture_from_material(mat)
        
        # BONES
        bones = list(rig.data.bones)
        bone_table = []
        for index, bone in enumerate(bones):
            if bone.parent:
                parent_index = bones.index(bone.parent)
                bone_position = bone.head_local - bone.parent.head_local

                euler_current = bone.matrix_local.to_euler()
                euler_parent = bone.parent.matrix_local.to_euler()
                bone_angle = (
                    euler_current[0] - euler_parent[0],
                    euler_current[1] - euler_parent[1],
                    euler_current[2] - euler_parent[2]
                )
            else:
                parent_index = -1
                bone_position = bone.head_local
                euler_current = bone.matrix_local.to_euler()
                bone_angle = (euler_current[0], euler_current[1], euler_current[2])

            st = mbone_st()
            st.index = index
            st.name = list(bone.name.encode("utf-8").ljust(32,b"\x00").decode("utf-8"))
            st.parent = parent_index
            st.bone_position = bone_position
            st.bone_angle = bone_angle
            bone_table.append(st)
            
        # STATIC MESHES
        meshes_table = {}
        for obj in mesh_objs:
            for triag in obj.data.polygons:
                for idx in triag.vertices:
                    vert = obj.data.vertices[idx]
                    groups = vert.groups
                    if len(groups) != 1:
                        break
                    if groups[0].weight != 1.0:
                        break
                    bone_ind = obj.vertex_groups[groups[0].group].index
                    if not bone_ind in meshes_table.keys():
                        meshes_table[bone_ind] = []
                    meshes_table[bone_ind].append(vert)
        
        i = 0
        for bone_indx,vert_array in meshes_table.items():
            bone = rig.data.bones[bone_indx]
            st1 = mstmesh_st()
            i = i + 1
            st1.index = i
            st1.name = list(vert_array[0].id_data.name+"_sm"+str(bone_indx))
            st1.parented = 1
            st1.boneIndex = bone_indx
            st1.position = mathutils.Vector((0.0,0.0,0.0))
            st1.angle = mathutils.Euler((0.0, 0.0, 0.0),'XYZ')
            st1.vertices_count = len(vert_array)
            new_vert_array = []
            for vert in vert_array:
                obj = mesh_to_obj[vert.id_data]
                pos,normal = get_vertex_position_and_normal(mesh_to_obj[vert.id_data],bone,vert.index)
                
                uvs_table = objects_uvs[obj]
                
                vertC = m_stvert_st()
                vertC.vert_position = pos
                vertC.vert_normal = normal
                vertC.vert_texcord = uvs_table[vert.index]
                new_vert_array.append(vertC)
            st1.vertices = new_vert_array
            st1.texture = 0
            
    if len(rigs) == 0:
        self.report({'ERROR'},"No rigs selected.")
        return {'CANCELLED'}
    
    with io.BytesIO(b'') as file:
        file.write(MST.id.to_bytes(4, byteorder="little"))
        file.write(MST.version.to_bytes(4, byteorder="little"))
        file.write(MST.checksum.to_bytes(4, byteorder="little", signed=True))
        file.write(''.join(MST.name).encode("utf-8"))
        
        BonesSection = io.BytesIO(b'')
        for bone in bone_table:
            BonesSection.write(bone.index.to_bytes(4,byteorder="little"))
            BonesSection.write(''.join(bone.name).encode("utf-8"))
            BonesSection.write(bone.parent.to_bytes(4,byteorder="little",signed=True))
            BonesSection.write(struct.pack("<f", bone.bone_position[0]))
            BonesSection.write(struct.pack("<f", bone.bone_position[1]))
            BonesSection.write(struct.pack("<f", bone.bone_position[2]))
            BonesSection.write(struct.pack("<f", bone.bone_angle[0]))
            BonesSection.write(struct.pack("<f", bone.bone_angle[1]))
            BonesSection.write(struct.pack("<f", bone.bone_angle[2]))
            
        bones_offset = 68 # Main header end
        bones_count = len(bone_table)
        static_mesh_offset = bones_offset+len(BonesSection.getvalue()) # Bones section end
        static_mesh_count = len(bone_table)
        dvertx_offset = static_mesh_offset+len(BonesSection.getvalue()) # Static meshes section end
        dvertx_count = len(bone_table)
        
        file.write(bones_count.to_bytes(4,byteorder="little"))
        file.write(bones_offset.to_bytes(4,byteorder="little"))
        file.write(static_mesh_count.to_bytes(4,byteorder="little"))
        file.write(static_mesh_offset.to_bytes(4,byteorder="little"))
        file.write(dvertx_count.to_bytes(4,byteorder="little"))
        file.write(dvertx_offset.to_bytes(4,byteorder="little"))
        
        file.write(BonesSection.getvalue())
        
        with open(filepath, "wb") as f:
            f.write(file.getbuffer())
    
    return {'FINISHED'}

class madl_st:
    id = 1279541581
    version = 1
    checksum = 0
    name = []
    
    bone_count = 0
    bone_offset = 0
    
    static_mesh_count = 0
    static_mesh_offset = 0
    
    dvertx_count = 0
    dvertx_offset = 0
    
class mbone_st:
    index = 0
    name = []
    parent = 0
    bone_position = mathutils.Vector((0.0, 0.0, 0.0))
    bone_angle = mathutils.Euler((0.0, 0.0, 0.0),'XYZ')
    
class mstmesh_st:
    struct_size = 0
    index = 0
    name = []
    parented = 0 # 0 - False, >0 - True
    boneIndex = 0
    position = mathutils.Vector((0.0,0.0,0.0))
    angle = mathutils.Euler((0.0, 0.0, 0.0),'XYZ')
    vertices_count = 0
    vertices = []
    texture = 0
    
class m_stvert_st:
    vert_position = mathutils.Vector((0.0,0.0,0.0))
    vert_normal = mathutils.Vector((0.0,0.0,0.0))
    vert_texcoord = mathutils.Vector((0.0,0.0,0.0)) # third axis ignored
    
class mdynvertex_st:
    struct_size = 0
    numbones = 0
    weight = []
    bone = []
    vert_position = mathutils.Vector((0.0,0.0,0.0))
    vert_normal = mathutils.Vector((0.0,0.0,0.0))
    vert_texcoord = mathutils.Vector((0.0,0.0,0.0)) # third axis ignored
    
class ExportMADL(Operator, ExportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "madl.export"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "MADL (.madl)"

    # ExportHelper mixin class uses this
    filename_ext = ".madl"

    filter_glob: StringProperty(
        default="*.madl",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    def execute(self, context):
        return writeMADL(self,context, self.filepath)

    
# Only needed if you want to add into a dynamic menu
def menu_func_export(self, context):
    self.layout.operator(ExportMADL.bl_idname, text="MADL (.madl)")


# Register and add to the "file selector" menu (required to use F3 search "Text Export Operator" for quick access).
def register():
    bpy.utils.register_class(ExportMADL)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(ExportMADL)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()