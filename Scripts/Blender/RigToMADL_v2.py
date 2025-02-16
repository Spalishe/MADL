# Made by Spalishe for github.com/Spalishe/MADL

import bpy
import mathutils
import random
import tempfile
from collections import defaultdict
import io
import struct
import subprocess

def get_vertex_position_and_normal(obj, bone, vertex_index):
    armature = obj.find_armature()
    if not armature:
        raise ValueError("The object does not have an armature.")

    if vertex_index >= len(obj.data.vertices):
        raise IndexError("Invalid vertex index.")
    
    vertex = obj.data.vertices[vertex_index]

    world_pos = obj.matrix_world @ vertex.co

    world_normal = obj.matrix_world.to_3x3() @ vertex.normal

    bone_matrix = bone.matrix
    local_pos = bone_matrix.inverted() @ world_pos
    local_normal = bone_matrix.inverted().to_3x3() @ world_normal

    return local_pos, local_normal

def get_name(name):
    return list(name.encode("utf-8").ljust(32,b"\x00").decode("utf-8"))
    
def get_mat_base_texture(material,tex_type):
    if not material.node_tree:
        return None
    
    material_output_node = None
    for node in material.node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            material_output_node = node
            break

    if not material_output_node:
        return None
        
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
        return None

    base_color_input = bsdf_node.inputs.get("Base Color")
    if base_color_input and base_color_input.is_linked:
        image_texture_node = base_color_input.links[0].from_node
        if image_texture_node.type == 'TEX_IMAGE':
            image = image_texture_node.image

            temp_file = tempfile.gettempdir() + "/base_texture_"+str(random.randint(0,0xFFFF))+"."+tex_type.lower()
            orig_image = image.pixels
            image.filepath_raw = temp_file
            image.file_format = tex_type == "VTF" and "PNG" or tex_type
            image.save()
            
            image.pixels = orig_image
            image.update()

            with open(temp_file, "rb") as f:
                base64_str = f.read().decode("latin-1")
            return base64_str,temp_file

    return None

def get_mat_emission(material,tex_type):
    if not material.node_tree:
        return None
    
    material_output_node = None
    for node in material.node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            material_output_node = node
            break

    if not material_output_node:
        return None
        
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
        return None

    base_color_input = bsdf_node.inputs.get("Emission")
    if base_color_input and base_color_input.is_linked:
        image_texture_node = base_color_input.links[0].from_node
        if image_texture_node.type == 'TEX_IMAGE':
            image = image_texture_node.image

            temp_file = tempfile.gettempdir() + "/emission_texture_"+str(random.randint(0,0xFFFF))+"."+tex_type.lower()
            orig_image = image.pixels
            image.filepath_raw = temp_file
            image.file_format = tex_type == "VTF" and "PNG" or tex_type
            image.save()
            
            image.pixels = orig_image
            image.update()
                        
            with open(temp_file, "rb") as f:
                base64_str = f.read().decode("latin-1")
            return base64_str,temp_file

    return None

def textureToVtf(mat_name,base_filepath, emission_filepath, vtfcmd_path):
    print("VTF Handling: "+mat_name)
    base_tex_proc = subprocess.run([vtfcmd_path, f"-file \"{base_filepath}\"", "-format \"dxt1\"", "-alphaformat \"dxt1_onebitalpha\"", "-nothumbnail", "-noreflectivity", "-nomipmaps"], stdout=subprocess.PIPE)
    if emission_filepath != None:
        emission_proc = subprocess.run([vtfcmd_path, f"-file \"{emission_filepath}\"", "-format \"dxt1\"", "-alphaformat \"dxt1_onebitalpha\"", "-nothumbnail", "-noreflectivity", "-nomipmaps"], stdout=subprocess.PIPE)
    
    if base_tex_proc.returncode == 0:
        new_bt_filepath = base_filepath.split('.')[0] + ".vtf"
        with open(new_bt_filepath,"rb") as f:
            base_tex_data = f.read()
    else:
        base_tex_data = None
    
    if emission_proc.returncode == 0:
        new_emission_filepath = emission_filepath.split('.')[0] + ".vtf"
        with open(new_emission_filepath,"rb") as f:
            emmision_data = f.read()
    else:
        emmision_data = None
        
    return [mat_name,base_tex_data,emmision_data]

def get_objects_parented_to_rig(rig):
    parented_objects = []

    for obj in bpy.context.scene.objects:
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object == rig:
                parented_objects.append(obj)
                break

    return parented_objects

def separate_polygons_by_material(obj):
    polys_by_material = defaultdict(list)

    for poly in obj.data.polygons:
        material = obj.data.materials[poly.material_index] if poly.material_index < len(obj.data.materials) else None
        polys_by_material[material].append(poly)

    return polys_by_material

def get_vertex_uvs(obj):
    if not obj.data.uv_layers:
        return None
    
    uv_layer = obj.data.uv_layers.active.data
    tbl = {}    
    for loop in obj.data.loops:
        tbl[loop.vertex_index] = uv_layer[loop.index].uv
    
    return tbl

def main(self, context, filepath, add_tex, add_phy, tex_type, vtfcmd_path):
    MADL = madl_st()
    MTEX = mtex_st()
    MPHY = mphy_st()
    CHCKSUM = random.randint(-2147483648,2147483647)
    
    MADL.checksum = CHCKSUM
    MTEX.checksum = CHCKSUM
    MPHY.checksum = CHCKSUM

    selected_objs = bpy.context.selected_objects
    rigs = [obj for obj in selected_objs if obj.type == 'ARMATURE']
    
    if len(rigs) == 0:
        self.report({'ERROR'},"Selected more than one rig.")
        return {'CANCELLED'}
    if len(rigs) > 1:
        self.report({'ERROR'},"Select only one rig.")
        return {'CANCELLED'}
    rig = rigs[0]
    rig.data.pose_position = 'REST'
    objs = get_objects_parented_to_rig(rig)
    objects_uvs = {}
    for obj in objs:
        objects_uvs[obj] = get_vertex_uvs(obj)
    
    
    # PHYSICS
    if add_phy:
        phy_objs = [obj for obj in objs if "phy" in obj.name]
        if len(phy_objs) > 1:
            self.report({'ERROR'},"Rig contains more than one phy object.")
            return {'CANCELLED'}
        if len(phy_objs) == 0:
            self.report({'ERROR'},"Rig has no phy objects")
            return {'CANCELLED'}
        phy_obj = phy_objs[0]
        objs.remove(phy_obj)
        
        max_phys_index = 0
        phys_table = []
        for vg in phy_obj.vertex_groups:
            group_vertices = [v.index for v in obj.data.vertices if vg.index in [g.group for g in v.groups]]

            if len(group_vertices) > 0:
                mphysdata = mphysdata_st()
                max_phys_index = max_phys_index + 1
                mphysdata.index = max_phys_index
                mphysdata.name = get_name(phy_obj.name+"_phy_"+str(max_phys_index))
                mphysdata.parented = 1
                mphysdata.boneIndex = vg.index
                mphysdata.position = mathutils.Vector((0.0, 0.0, 0.0))
                mphysdata.angle = mathutils.Euler((0.0, 0.0, 0.0),'XYZ')
                mphysdata.vertices_count = len(group_vertices)
                vertices = []
                for vert in group_vertices:
                    pos,normal = get_vertex_position_and_normal(phy_obj,rig.data.bones[vg.index],vert)
                    vertices.append(pos)
                mphysdata.vertices = vertices
                mphysdata.struct_size = 69 + len(group_vertices) * 12
                phys_table.append(mphysdata)
        
    # TEXTURE
    texture_table = {}
    texture_max_index = 0
    if add_tex:
        for obj in objs:
            if len(obj.material_slots) == 0:
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if mat in texture_table.keys():
                    continue
                base_texture,bt_path = get_mat_base_texture(mat,tex_type)
                emission,et_path = get_mat_emission(mat,tex_type)
                
                if tex_type != "VTF":
                    mtexdata = mtexdata_st()
                    texture_max_index = texture_max_index + 1
                    mtexdata.texture = texture_max_index
                    mtexdata.name = get_name(mat.name)
                    mtexdata.data_length = len(base_texture)
                    mtexdata.data = list(base_texture)
                    if emission != None:
                        mtexdata.emission = 1
                        mtexdata.emission_data_length = len(emission)
                        mtexdata.emission_data = list(emission)
                    
                    mtexdata.struct_size = 45
                    
                    texture_table[mat] = mtexdata
                else:
                    data = textureToVtf(mat.name,bt_path,emission != None and et_path or None,vtfcmd_path)
                    mat_name = data[0]
                    base_data = data[1]
                    emission_data = data[2]
                    mtexdata = mtexdata_st()
                    texture_max_index = texture_max_index + 1
                    mtexdata.texture = texture_max_index
                    mtexdata.name = get_name(mat.name)
                    if base_data != None:
                        mtexdata.data_length = len(base_data)
                        mtexdata.data = list(base_data)
                    if emission_data != None:
                        mtexdata.emission = 1
                        mtexdata.emission_data_length = len(emission_data)
                        mtexdata.emission_data = list(emission_data)
                    
                    mtexdata.struct_size = 45
                    
                    texture_table[mat] = mtexdata
            
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

        mbone = mbone_st()
        mbone.index = index
        mbone.name = get_name(bone.name)
        mbone.parent = parent_index
        mbone.bone_position = bone_position
        mbone.bone_angle = bone_angle
        bone_table.append(mbone)
        
    # SORTING
    good_polys = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    bad_polys = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    for obj in objs:
        polyt = separate_polygons_by_material(obj)
        for mat,polys in polyt.items():
            for poly in polys:
                valid_triag = True
                for vert_ind in poly.vertices:
                    vert = obj.data.vertices[vert_ind]
                    groups = vert.groups
                    if len(groups) != 1:
                        valid_triag = False
                        break
                    if groups[0].weight != 1:
                        valid_triag = False
                        break
                if valid_triag:
                    for vert_ind in poly.vertices:
                        vert = obj.data.vertices[vert_ind]
                        good_polys[obj][mat][obj.vertex_groups[vert.groups[0].group].index].append(vert)
                else:
                    for vert_ind in poly.vertices:
                        vert = obj.data.vertices[vert_ind]
                        bad_polys[obj][mat][obj.vertex_groups[vert.groups[0].group].index].append(vert)
                
    # STATIC MESHES
    static_meshes = []
    max_static_meshes = 0
    for obj,mat_list in good_polys.items():
        for mat,bone_list in mat_list.items():
            for bone_ind,vert_list in bone_list.items():
                bone = rig.data.bones[bone_ind]
                mstmesh = mstmesh_st()
                max_static_meshes = max_static_meshes + 1
                mstmesh.index = max_static_meshes
                mstmesh.name = get_name(obj.name+"_sm_"+str(bone_ind))
                mstmesh.parented = 1
                mstmesh.boneIndex = bone_ind
                mstmesh.position = mathutils.Vector((0.0,0.0,0.0))
                mstmesh.angle = mathutils.Euler((0.0, 0.0, 0.0),'XYZ')
                mstmesh.vertices_count = len(vert_list)
                new_vert_array = []
                for vert in vert_list:
                    pos,normal = get_vertex_position_and_normal(obj,bone,vert.index)
                    uvs_table = objects_uvs[obj]
                    vertC = m_stvert_st()
                    vertC.vert_position = pos
                    vertC.vert_normal = normal
                    vertC.vert_texcord = uvs_table[vert.index]
                    new_vert_array.append(vertC)
                mstmesh.vertices = new_vert_array
                try:
                    mstmesh.texture = texture_table[obj.material_slots[0].material].texture
                except IndexError:
                    mstmesh.texture = -1
                except KeyError:
                    mstmesh.texture = -1
                static_meshes.append(mstmesh)
                
    # DYNAMIC MESHES
    max_dynamic_meshes = 0
    dynamic_meshes = []
    for obj,mat_list in bad_polys.items():
        for mat,bone_list in mat_list.items():
            for bone_ind,vert_list in bone_list.items():
                bone = rig.data.bones[bone_ind]
                dyn_st = mdynmesh_st()
                max_dynamic_meshes = max_dynamic_meshes + 1
                dyn_st.index = max_dynamic_meshes
                dyn_st.name = get_name(obj.name+"_dm_"+str(max_dynamic_meshes))
                try:
                    dyn_st.texture = texture_table[obj.material_slots[0].material].texture
                except IndexError:
                    dyn_st.texture = -1
                except KeyError:
                    dyn_st.texture = -1
                
                uvs_table = objects_uvs[obj]
                new_vert_table = []
                for vert in vert_list:
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
                dynamic_meshes.append(dyn_st)
    
    new_filepath = filepath[:-4]
    writeMADL(new_filepath,MADL,bone_table,static_meshes,dynamic_meshes)
    if add_tex: writeMTEX(new_filepath,MTEX,texture_table)
    if add_phy: writeMPHY(new_filepath,MPHY,phys_table)
    
    rig.data.pose_position = 'POSE'
    return {'FINISHED'}

def writeMADL(filepath,MADL,bone_table,static_meshes,dynamic_meshes):
    with io.BytesIO(b'') as madl:
        madl.write(MADL.id.to_bytes(4, byteorder="little"))
        madl.write(MADL.version.to_bytes(4, byteorder="little"))
        madl.write(MADL.checksum.to_bytes(4, byteorder="little", signed=True))
        madl.write(''.join(MADL.name).encode("utf-8"))
        
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
        for stm in static_meshes:
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
        for dvm in dynamic_meshes:
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
        static_mesh_count = len(static_meshes)
        dvertx_offset = static_mesh_offset+len(StaticMeshSection.getvalue()) # Static meshes section end
        dvertx_count = len(dynamic_meshes)
        
        madl.write(bones_count.to_bytes(4,byteorder="little"))
        madl.write(bones_offset.to_bytes(4,byteorder="little"))
        madl.write(static_mesh_count.to_bytes(4,byteorder="little"))
        madl.write(static_mesh_offset.to_bytes(4,byteorder="little"))
        madl.write(dvertx_count.to_bytes(4,byteorder="little"))
        madl.write(dvertx_offset.to_bytes(4,byteorder="little"))
        
        madl.write(BonesSection.getvalue())
        madl.write(StaticMeshSection.getvalue())
        madl.write(DynamicVertxSection.getvalue())
        
        with open(filepath+"madl", "wb") as f:
            f.write(madl.getbuffer())

def writeMTEX(filepath,MTEX,texture_table):
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
        
        tex_offset = 20 # Main header end
        tex_count = len(texture_table)
        
        mtex.write(tex_count.to_bytes(4,byteorder="little"))
        mtex.write(tex_offset.to_bytes(4,byteorder="little"))
        
        mtex.write(TextureDataSection.getvalue())
        
        with open(filepath+"mtex", "wb") as f:
            f.write(mtex.getbuffer())

def writeMPHY(filepath,MPHY,phys_table):
    with io.BytesIO(b'') as mphy:
        mphy.write(MPHY.id.to_bytes(4, byteorder="little"))
        mphy.write(MPHY.version.to_bytes(4, byteorder="little"))
        mphy.write(MPHY.checksum.to_bytes(4, byteorder="little", signed=True))
        
        PhyDataSection = io.BytesIO(b'')
        for phy in phys_table:
            PhyDataSection.write(phy.struct_size.to_bytes(4,byteorder="little"))
            PhyDataSection.write(phy.index.to_bytes(4,byteorder="little"))
            PhyDataSection.write(''.join(phy.name).encode("utf-8"))
            PhyDataSection.write(phy.parented.to_bytes(1,byteorder="little"))
            PhyDataSection.write(phy.boneIndex.to_bytes(4,byteorder="little"))
            PhyDataSection.write(struct.pack("<f", phy.position[0]))
            PhyDataSection.write(struct.pack("<f", phy.position[1]))
            PhyDataSection.write(struct.pack("<f", phy.position[2]))
            PhyDataSection.write(struct.pack("<f", phy.angle[0]))
            PhyDataSection.write(struct.pack("<f", phy.angle[1]))
            PhyDataSection.write(struct.pack("<f", phy.angle[2]))
            PhyDataSection.write(phy.vertices_count.to_bytes(4,byteorder="little"))
            for vert in phy.vertices:
                PhyDataSection.write(struct.pack("<f", vert[0]))
                PhyDataSection.write(struct.pack("<f", vert[1]))
                PhyDataSection.write(struct.pack("<f", vert[2]))
        
        phy_offset = 20 # Main header end
        phy_count = len(phys_table)
        
        mphy.write(phy_count.to_bytes(4,byteorder="little"))
        mphy.write(phy_offset.to_bytes(4,byteorder="little"))
        
        mphy.write(PhyDataSection.getvalue())
        
        with open(filepath+"mphy", "wb") as f:
            f.write(mphy.getbuffer())

from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

class ExportMADL(Operator, ExportHelper):
    bl_idname = "madl.export"
    bl_label = "MADL (.madl)"

    filename_ext = ".madl"

    filter_glob: StringProperty(
        default="*.madl",
        options={'HIDDEN'},
        maxlen=255, 
    )
    add_phy: BoolProperty(
        name="Add physics",
        description="Require object with name \"phy\" in rig.",
        default=False,
    )
    
    add_tex: BoolProperty(
        name="Add textures",
        description="Create MTEX file.",
        default=True,
    )

    tex_type: EnumProperty(
        name="Texture format",
        description="Images type",
        items=(
            ('PNG', ".PNG", "Export as Portable Network Graphics"),
            ('JPEG', ".JPEG (.JPG)", "Export as Joint Photographic Expert Group"),
            ('VTF', ".VTF", "Export as Valve Texture Format"),
        ),
        default='PNG',
    )
    
    # If you cant download VTFCMD go to
    # https://web.archive.org/web/20191223154323if_/http://nemesis.thewavelength.net/files/files/vtflib132.zip
    # Unpack, VTFCMD in bin\x64\
    # If you copying, dont forget to copy all DLL's
    vtfcmd_path: StringProperty(
        name="VTFCMD path",
        description="Must be a valid path to VTFCMD",
        default='',
    )
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "add_tex")

        column = layout.column()
        column.enabled = self.add_tex
        column.prop(self, "tex_type")
        if self.tex_type == "VTF":
            column.prop(self, "vtfcmd_path")

        layout.prop(self, "add_phy")

    def execute(self, context):
        return main(self,context, self.filepath, self.add_tex, self.add_phy, self.tex_type, self.vtfcmd_path)

def menu_func_export(self, context):
    self.layout.operator(ExportMADL.bl_idname, text="MADL (.madl)")
    
def register():
    bpy.utils.register_class(ExportMADL)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(ExportMADL)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()

""" Types, see https://github.com/Spalishe/MADL/blob/main/MADL specification.txt"""

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