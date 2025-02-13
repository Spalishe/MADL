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
            image.scale(1024,1024) # compression 
            image.save()

            with open(temp_file, "rb") as f:
                base64_str = f.read().decode("latin-1")
            return base64_str

    return None


def get_emission_texture_from_material(material):
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

    base_color_input = bsdf_node.inputs.get("Emission")
    if base_color_input and base_color_input.is_linked:
        image_texture_node = base_color_input.links[0].from_node
        if image_texture_node.type == 'TEX_IMAGE':
            image = image_texture_node.image

            temp_file = tempfile.gettempdir() + "/emission_texture.png"
            image.filepath_raw = temp_file
            image.file_format = 'PNG'
            image.scale(1024,1024) # compression 
            image.save()

            with open(temp_file, "rb") as f:
                base64_str = f.read().decode("latin-1")

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

def writeMADL(self,context, filepath, add_phy):
    MST = madl_st()
    MTEX = mtex_st()
    MPHY = mphy_st()
    CHCKSUM = random.randint(-2147483648,2147483647)
    MST.checksum = CHCKSUM
    MTEX.checksum = CHCKSUM
    MPHY.checksum = CHCKSUM

    selected_objs = bpy.context.selected_objects
    rigs = [obj for obj in selected_objs if obj.type == 'ARMATURE']

    if len(rigs) > 1:
        self.report({'ERROR'},"Selected more than one rig.")
        return {'CANCELLED'}

    if len(rigs) == 1:
        rig = rigs[0]
        rig.data.pose_position = 'REST'

        mesh_objs = get_objects_parented_to_rig(rig)
        
        # TODO: make physics
        if add_phy:
            phy_obj = [obj for obj in mesh_objs if "phy" in obj.name][0]
            mesh_objs.remove(phy_obj)
        
        MST.name = list(rig.name.encode("utf-8").ljust(32,b"\x00").decode("utf-8"))
        
        mesh_to_obj = {}
        for obj in mesh_objs:
            mesh_to_obj[obj.data] = obj
        
        objects_uvs = {}
        for obj in mesh_objs:
            objects_uvs[obj] = get_vertex_uvs(obj)
        
        # TEXTURES
        texture_table = {}
        text_ind_temp = 0
        for obj in mesh_objs:
            if len(obj.material_slots) == 0:
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if mat in texture_table.keys():
                    continue
                base = get_base_color_texture_from_material(mat)
                dat = mtexdata_st()
                dat.texture = text_ind_temp
                text_ind_temp = text_ind_temp + 1
                dat.data_length = len(base)
                dat.data = list(base)
                dat.name = list(mat.name.encode("utf-8").ljust(32,b"\x00").decode("utf-8"))
                emission = get_emission_texture_from_material(mat)
                if emission != None:
                    dat.emission = 1
                    dat.emission_data_length = len(emission)
                    dat.emission_data = list(base)
                
                texture_table[mat] = dat
        
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
        
        # TODO: remake this cuz i stupid
        
        fin_meshes_table = []
        used_triags = {}
        meshes_table = {}
        for i in range(len(mesh_objs)):
            obj = mesh_objs[i]
            for triag in obj.data.polygons:
                ValidTriag = True
                for idx in triag.vertices:
                    vert = obj.data.vertices[idx]
                    groups = vert.groups
                    if len(groups) != 1:
                        ValidTriag = False
                        break
                    if groups[0].weight != 1.0:
                        ValidTriag = False
                        break
                    bone_ind = obj.vertex_groups[groups[0].group].index
                    if not i in meshes_table.keys():
                        meshes_table[i] = [bone_ind,[]]
                    meshes_table[i][1].append(vert)
                if ValidTriag:
                    if not obj in used_triags.keys():
                        used_triags[obj] = []
                    used_triags[obj].append(triag)
        
        i1 = 0
        for i,data in meshes_table.items():
            vert_array = data[1]
            bone_indx = data[0]
            bone = rig.data.bones[bone_indx]
            st1 = mstmesh_st()
            i1 = i1 + 1
            st1.index = i1
            st1.name = list((vert_array[0].id_data.name+"_sm"+str(bone_indx)).encode("utf-8").ljust(32,b"\x00").decode("utf-8"))
            st1.parented = 1
            st1.boneIndex = bone_indx
            st1.position = mathutils.Vector((0.0,0.0,0.0))
            st1.angle = mathutils.Euler((0.0, 0.0, 0.0),'XYZ')
            st1.vertices_count = len(vert_array)
            obj = mesh_to_obj[vert_array[0].id_data]
            new_vert_array = []
            for vert in vert_array:
                pos,normal = get_vertex_position_and_normal(mesh_to_obj[vert.id_data],bone,vert.index)
                
                uvs_table = objects_uvs[obj]
                
                vertC = m_stvert_st()
                vertC.vert_position = pos
                vertC.vert_normal = normal
                vertC.vert_texcord = uvs_table[vert.index]
                new_vert_array.append(vertC)
            st1.vertices = new_vert_array
            try:
                st1.texture = texture_table[obj.material_slots[0].material].texture
            except IndexError:
                st1.texture = -1
            
            fin_meshes_table.append(st1)
            
        # DYNAMIC VERTICES
        dyn_vertx_table = []
        dyn_indx = 0
        for obj,triag_array in used_triags.items():
            dyn_st = mdynmesh_st()
            dyn_st.index = dyn_indx
            dyn_st.name = list((obj.name+"_dm"+str(dyn_indx)).encode("utf-8").ljust(32,b"\x00").decode("utf-8"))
            dyn_indx = dyn_indx + 1
            try:
                dyn_st.texture = texture_table[obj.material_slots[0].material].texture
            except IndexError:
                dyn_st.texture = -1
            
            uvs_table = objects_uvs[obj]
            new_vert_table = []
            for triag in triag_array:
                for vert_ind in triag.vertices:
                    vert = obj.data.vertices[vert_ind]
                    dynvert = mdynvert_st()
                    numbones = 0
                    weights = []
                    bone = []
                    for g in vert.groups:
                        weights.append(g.weight)
                        group_name = obj.vertex_groups[g.group].name
                        bone.append(rig.data.bones.find(group_name))
                        numbones = numbones + 1
                    dynvert.numbones = numbones
                    dynvert.weight = weights
                    dynvert.bone = bone
                    dynvert.struct_size = 33 + 8 * numbones
                    dynvert.vert_position = vert.co
                    dynvert.vert_normal = vert.normal
                    dynvert.vert_texcoord = uvs_table[vert.index]
                    new_vert_table.append(dynvert)
            dyn_st.vertices_count = len(new_vert_table)
            dyn_st.vertices = new_vert_table
            dyn_vertx_table.append(dyn_st)
        
    if len(rigs) == 0:
        self.report({'ERROR'},"No rigs selected.")
        return {'CANCELLED'}
    
    new_filepath = filepath[:-4]
    with io.BytesIO(b'') as madl:
        madl.write(MST.id.to_bytes(4, byteorder="little"))
        madl.write(MST.version.to_bytes(4, byteorder="little"))
        madl.write(MST.checksum.to_bytes(4, byteorder="little", signed=True))
        madl.write(''.join(MST.name).encode("utf-8"))
        
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
        
        StaticMeshSection = io.BytesIO(b'')
        for stm in fin_meshes_table:
            stm.struct_size = 70 + len(stm.vertices)*32
            StaticMeshSection.write(stm.struct_size.to_bytes(4,byteorder="little"))
            StaticMeshSection.write(stm.index.to_bytes(4,byteorder="little"))
            StaticMeshSection.write(''.join(stm.name).encode("utf-8"))
            StaticMeshSection.write(stm.parented.to_bytes(1,byteorder="little"))
            StaticMeshSection.write(stm.boneIndex.to_bytes(4,byteorder="little"))
            StaticMeshSection.write(struct.pack("<f", stm.position[0]))
            StaticMeshSection.write(struct.pack("<f", stm.position[1]))
            StaticMeshSection.write(struct.pack("<f", stm.position[2]))
            StaticMeshSection.write(struct.pack("<f", stm.angle[0]))
            StaticMeshSection.write(struct.pack("<f", stm.angle[1]))
            StaticMeshSection.write(struct.pack("<f", stm.angle[2]))
            StaticMeshSection.write(stm.vertices_count.to_bytes(4,byteorder="little"))
            for vert in stm.vertices:
                StaticMeshSection.write(struct.pack("<f", vert.vert_position[0]))
                StaticMeshSection.write(struct.pack("<f", vert.vert_position[1]))
                StaticMeshSection.write(struct.pack("<f", vert.vert_position[2]))
                StaticMeshSection.write(struct.pack("<f", vert.vert_normal[0]))
                StaticMeshSection.write(struct.pack("<f", vert.vert_normal[1]))
                StaticMeshSection.write(struct.pack("<f", vert.vert_normal[2]))
                StaticMeshSection.write(struct.pack("<f", vert.vert_texcoord[0]))
                StaticMeshSection.write(struct.pack("<f", vert.vert_texcoord[1]))
            StaticMeshSection.write(stm.texture.to_bytes(1,byteorder="little",signed=True))
            
        DynamicVertxSection = io.BytesIO(b'')
        for dvm in dyn_vertx_table:
            DynamicVertxSection.write(dvm.struct_size.to_bytes(4,byteorder="little"))
            DynamicVertxSection.write(dvm.index.to_bytes(4,byteorder="little"))
            DynamicVertxSection.write(''.join(dvm.name).encode("utf-8"))
            DynamicVertxSection.write(dvm.vertices_count.to_bytes(4,byteorder="little"))
            for vert in dvm.vertices:
                DynamicVertxSection.write(vert.struct_size.to_bytes(4,byteorder="little"))
                DynamicVertxSection.write(vert.numbones.to_bytes(1,byteorder="little"))
                for weight in vert.weight:
                    DynamicVertxSection.write(struct.pack("<f", weight))
                for bone in vert.bone:
                    DynamicVertxSection.write(bone.to_bytes(1,byteorder="little"))
                DynamicVertxSection.write(struct.pack("<f", vert.vert_position[0]))
                DynamicVertxSection.write(struct.pack("<f", vert.vert_position[1]))
                DynamicVertxSection.write(struct.pack("<f", vert.vert_position[2]))
                DynamicVertxSection.write(struct.pack("<f", vert.vert_normal[0]))
                DynamicVertxSection.write(struct.pack("<f", vert.vert_normal[1]))
                DynamicVertxSection.write(struct.pack("<f", vert.vert_normal[2]))
                DynamicVertxSection.write(struct.pack("<f", vert.vert_texcoord[0]))
                DynamicVertxSection.write(struct.pack("<f", vert.vert_texcoord[1]))
            DynamicVertxSection.write(dvm.texture.to_bytes(1,byteorder="little",signed=True))
            
        
        bones_offset = 68 # Main header end
        bones_count = len(bone_table)
        static_mesh_offset = bones_offset+len(BonesSection.getvalue()) # Bones section end
        static_mesh_count = len(fin_meshes_table)
        dvertx_offset = static_mesh_offset+len(StaticMeshSection.getvalue()) # Static meshes section end
        dvertx_count = len(dyn_vertx_table)
        
        madl.write(bones_count.to_bytes(4,byteorder="little"))
        madl.write(bones_offset.to_bytes(4,byteorder="little"))
        madl.write(static_mesh_count.to_bytes(4,byteorder="little"))
        madl.write(static_mesh_offset.to_bytes(4,byteorder="little"))
        madl.write(dvertx_count.to_bytes(4,byteorder="little"))
        madl.write(dvertx_offset.to_bytes(4,byteorder="little"))
        
        madl.write(BonesSection.getvalue())
        madl.write(StaticMeshSection.getvalue())
        madl.write(DynamicVertxSection.getvalue())
        
        with open(new_filepath+"madl", "wb") as f:
            f.write(madl.getbuffer())
            
    with io.BytesIO(b'') as mtex:        
        mtex.write(MTEX.id.to_bytes(4, byteorder="little"))
        mtex.write(MTEX.version.to_bytes(4, byteorder="little"))
        mtex.write(MTEX.checksum.to_bytes(4, byteorder="little", signed=True))
        
        TextureDataSection = io.BytesIO(b'')
        for mat,texture in texture_table.items():
            texture.struct_size = 13 + 32 + texture.data_length + texture.emission_data_length
            TextureDataSection.write(texture.struct_size.to_bytes(4,byteorder="little"))
            TextureDataSection.write(texture.texture.to_bytes(4,byteorder="little"))
            TextureDataSection.write(''.join(texture.name).encode("utf-8"))
            TextureDataSection.write(texture.data_length.to_bytes(4,byteorder="little"))
            TextureDataSection.write(''.join(texture.data).encode("utf-8"))
            TextureDataSection.write(texture.emission.to_bytes(1,byteorder="little"))
            TextureDataSection.write(texture.emission_data_length.to_bytes(4,byteorder="little"))
            TextureDataSection.write(''.join(texture.emission_data).encode("utf-8"))
        
        tex_offset = 12 # Main header end
        tex_count = len(texture_table)
        
        mtex.write(tex_count.to_bytes(4,byteorder="little"))
        mtex.write(tex_offset.to_bytes(4,byteorder="little"))
        
        mtex.write(TextureDataSection.getvalue())
        
        with open(new_filepath+"mtex", "wb") as f:
            f.write(mtex.getbuffer())
    
    rig.data.pose_position = 'POSE'
    return {'FINISHED'}

#MADL
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
    
class mdynvert_st:
    struct_size = 0
    numbones = 0
    weight = []
    bone = []
    vert_position = mathutils.Vector((0.0,0.0,0.0))
    vert_normal = mathutils.Vector((0.0,0.0,0.0))
    vert_texcoord = mathutils.Vector((0.0,0.0,0.0)) # third axis ignored

class mdynmesh_st:
    struct_size = 0
    index = 0
    name = []
    vertices_count = 0
    vertices = []
    texture = 0

#MTEX
class mtex_st:
    id = 1480938573
    version = 1
    checksum = 0
    
    tex_count = 0
    tex_offset = 0

class mtexdata_st:
    struct_size = 0
    texture = 0
    name = []
    data_length = 0
    data = []
    emission = 0
    emission_data_length = 0
    emission_data = []

#MPHY
class mphy_st:
    id = 1497911373
    version = 1
    checksum = 0
    
    phy_count = 0
    phy_offset = 0
    
class mphysdata_st:
    struct_size = 0
    index = 0
    name = []
    parented = 0
    boneIndex = 0
    position = mathutils.Vector((0.0, 0.0, 0.0))
    angle = mathutils.Euler((0.0, 0.0, 0.0),'XYZ')
    vertices_count = 0
    vertices = []

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
    add_phy: BoolProperty(
        name="Add physics",
        description="Require object with name \"phy\" in rig",
        default=True,
    )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    def execute(self, context):
        return writeMADL(self,context, self.filepath, self.add_phy)

    
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