# Made by Spalishe for github.com/Spalishe/MADL

import bpy
import mathutils
import random
import tempfile
from collections import defaultdict
import io
import struct
import subprocess
import threading

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
        return [None,None]
    
    material_output_node = None
    for node in material.node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            material_output_node = node
            break

    if not material_output_node:
        return [None,None]
        
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
        return [None,None]

    base_color_input = bsdf_node.inputs.get("Base Color")
    if base_color_input and base_color_input.is_linked:
        image_texture_node = base_color_input.links[0].from_node
        if image_texture_node.type == 'TEX_IMAGE':
            image = image_texture_node.image
            
            temp_file = tempfile.gettempdir() + "/base_texture_"+str(random.randint(0,0xFFFF))+"."+(tex_type.lower() == "vtf" and "png" or tex_type.lower())
            orig_image = image.pixels
            image.filepath_raw = temp_file
            image.file_format = tex_type == "VTF" and "PNG" or tex_type
            image.save()
            
            #image.pixels = orig_image
            #image.update()

            with open(temp_file, "rb") as f:
                base64_str = f.read().decode("latin-1")
            return [base64_str,temp_file]

    return [None,None]

def get_mat_emission(material,tex_type):
    if not material.node_tree:
        return [None,None]
    
    material_output_node = None
    for node in material.node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            material_output_node = node
            break

    if not material_output_node:
        return [None,None]
        
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
        return [None,None]

    base_color_input = bsdf_node.inputs.get("Emission")
    if base_color_input and base_color_input.is_linked:
        image_texture_node = base_color_input.links[0].from_node
        if image_texture_node.type == 'TEX_IMAGE':
            image = image_texture_node.image

            temp_file = tempfile.gettempdir() + "/emission_texture_"+str(random.randint(0,0xFFFF))+"."+(tex_type.lower() == "vtf" and "png" or tex_type.lower())
            orig_image = image.pixels
            image.filepath_raw = temp_file
            image.file_format = tex_type == "VTF" and "PNG" or tex_type
            image.save()
            
            #image.pixels = orig_image
            #image.update()
                        
            with open(temp_file, "rb") as f:
                base64_str = f.read().decode("latin-1")
            return [base64_str,temp_file]

    return [None,None]

def textureToVtf(idx,mat,base_filepath, emission_filepath, vtfcmd_path,vtf_results):
    print("VTF Handling: "+mat.name)
    base_tex_proc = subprocess.run(f"{vtfcmd_path} -file \"{base_filepath}\" -format \"dxt1_onebitalpha\" -alphaformat \"dxt1_onebitalpha\" -nothumbnail -noreflectivity -nomipmaps", stdout=subprocess.PIPE)
    print(base_tex_proc.stdout)
    
    if emission_filepath != None:
        emission_proc = subprocess.run(f"{vtfcmd_path} -file \"{emission_filepath}\" -format \"dxt1_onebitalpha\" -alphaformat \"dxt1_onebitalpha\" -nothumbnail -noreflectivity -nomipmaps", stdout=subprocess.PIPE)
        print(emission_proc.stdout)
    
    if base_tex_proc.returncode == 0:
        new_bt_filepath = base_filepath.split('.')[0] + ".vtf"
        with open(new_bt_filepath,"rb") as f:
            base_tex_data = f.read().decode("latin-1")
    else:
        base_tex_data = None
    
    emmision_data = None
    if emission_filepath != None:
        if emission_proc.returncode == 0:
            new_emission_filepath = emission_filepath.split('.')[0] + ".vtf"
            with open(new_emission_filepath,"rb") as f:
                emmision_data = f.read().decode("latin-1")
        else:
            emmision_data = None
            
    vtf_results[idx] = [mat,base_tex_data,emmision_data]

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

def main(self, context, filepath, add_tex, add_phy, add_anim, tex_type, vtfcmd_path):
    MADL = madl_st()
    MTEX = mtex_st()
    MPHY = mphy_st()
    MANI = mani_st()
    CHCKSUM = random.randint(-2147483648,2147483647)
    
    MADL.checksum = CHCKSUM
    MTEX.checksum = CHCKSUM
    MPHY.checksum = CHCKSUM
    MANI.checksum = CHCKSUM

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
    idx = 0
    vtf_mats = []
    vtf_results = {}
    vtf_threads = []
    if add_tex:
        for obj in objs:
            if len(obj.material_slots) == 0:
                continue
            for slot in obj.material_slots:
                mat = slot.material
                if mat in texture_table.keys() or mat in vtf_mats:
                    continue
                base_data = get_mat_base_texture(mat,tex_type)
                base_texture = base_data[0]
                bt_path = base_data[1]
                emission_data = get_mat_emission(mat,tex_type)
                emission = emission_data[0]
                et_path = emission_data[1]
                
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
                    vtf_mats.append(mat)
                    p = threading.Thread(target=textureToVtf,
                        args=(idx,mat, bt_path,emission != None and et_path or None,vtfcmd_path,vtf_results))
                    vtf_threads.append(p)
                    p.start()
                    idx = idx + 1
        if tex_type == "VTF":
            for p in vtf_threads:
                p.join()
                
        for idx,data in vtf_results.items():
            mat = data[0]
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
        
    # ANIMATIONS
    anim_table = []
    anim_index = 0
    flags = MBONEFLAGS()
    actions = []
    if rig.animation_data:
        if rig.animation_data.action:
            actions.append(rig.animation_data.action)
        
        for track in rig.animation_data.nla_tracks:
            for strip in track.strips:
                if strip.action:
                    actions.append(strip.action)
    for action in actions:
        ManiSeq = manimseq_st()
        ManiSeq.index = anim_index
        ManiSeq.name = get_name(action.name)
        
        rig.animation_data.action = action

        start_frame = int(action.frame_range[0])
        end_frame = int(action.frame_range[1])
        ManiSeq.numFrames = end_frame
        ManiSeq.fps = bpy.context.scene.render.fps

        rest_pose = {bone.name: (bone.bone.head_local.copy(), bone.bone.matrix_local.to_quaternion()) for bone in rig.pose.bones}
        data_arr = []
        
        prev_transforms = {}
        for frame in range(start_frame, end_frame + 1):
            bpy.context.scene.frame_set(frame)
            ManiData = manimdata_st()
            ManiData.frame = frame
            for index,bone in enumerate(rig.pose.bones):
                BonePos = mbonepos_t()
                bone_name = bone.name
                current_pos = bone.head
                current_rot = bone.matrix.to_quaternion()

                if frame == start_frame:
                    prev_pos, prev_rot = rest_pose[bone_name]
                else:
                    prev_pos, prev_rot = prev_transforms.get(bone_name, (current_pos, current_rot))

                delta_pos = current_pos - prev_pos
                delta_rot = (current_rot * prev_rot.inverted()).to_euler()
                
                Flags = flags.NOCHANGES
                
                # !!! CRINGE DETECTED !!!
                if delta_pos.x == 0:
                    Flags = Flags | flags.POSX
                if delta_pos.y == 0:
                    Flags = Flags | flags.POSY
                if delta_pos.z == 0:
                    Flags = Flags | flags.POSZ

                if delta_rot.x == 0:
                    Flags = Flags | flags.ROTX
                if delta_rot.y == 0:
                    Flags = Flags | flags.ROTY
                if delta_rot.z == 0:
                    Flags = Flags | flags.ROTZ
                
                prev_transforms[bone_name] = (current_pos, current_rot)
                BonePos.flags = Flags
                BonePos.boneIndex = index
                BonePos.posX = delta_pos.x
                BonePos.posY = delta_pos.y
                BonePos.posZ = delta_pos.z
                BonePos.rotX = delta_rot.x
                BonePos.rotY = delta_rot.y
                BonePos.rotZ = delta_rot.z
                ManiData.bone.append(BonePos)
            data_arr.append(ManiData)
        anim_index = anim_index + 1
        ManiSeq.frames = data_arr
        anim_table.append(ManiSeq)
    MANI.num_sequences = len(bpy.data.actions)
        
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
    if add_anim: writeMANI(new_filepath,MANI,anim_table)
    
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

def writeMANI(filepath,MANI,anim_table):
    with io.BytesIO(b'') as mani:
        mani.write(MANI.id.to_bytes(4, byteorder="little"))
        mani.write(MANI.version.to_bytes(4, byteorder="little"))
        mani.write(MANI.checksum.to_bytes(4, byteorder="little", signed=True))
        
        MANI.seq_offset = 20
        
        mani.write(MANI.num_sequences.to_bytes(4, byteorder="little"))
        mani.write(MANI.seq_offset.to_bytes(4, byteorder="little"))
        
        AnimSeqSection = io.BytesIO(b'')
        for seq in anim_table:
            AnimSeqSection.write(seq.index.to_bytes(4,byteorder="little"))
            AnimSeqSection.write(''.join(seq.name).encode("utf-8"))
            AnimSeqSection.write(seq.numFrames.to_bytes(4,byteorder="little"))
            AnimSeqSection.write(seq.fps.to_bytes(1,byteorder="little"))
            
            AnimDataSection = io.BytesIO(b'')
            for dat in seq.frames:
                AnimDataSection.write(dat.frame.to_bytes(2,byteorder="little"))
                for bone in dat.bone:
                    if bone.flags == 0:
                        continue
                    AnimDataSection.write(bone.flags.to_bytes(1,byteorder="little"))
                    AnimDataSection.write(bone.boneIndex.to_bytes(1,byteorder="little"))
                    if (bone.flags & 0x1) != 0:
                        AnimDataSection.write(struct.unpack('H', struct.pack('e', bone.posX))[0].to_bytes(2,byteorder="little"))
                    if (bone.flags & 0x2) != 0:
                        AnimDataSection.write(struct.unpack('H', struct.pack('e', bone.posY))[0].to_bytes(2,byteorder="little"))
                    if (bone.flags & 0x4) != 0:
                        AnimDataSection.write(struct.unpack('H', struct.pack('e', bone.posZ))[0].to_bytes(2,byteorder="little"))
                    if (bone.flags & 0x8) != 0:
                        AnimDataSection.write(struct.unpack('H', struct.pack('e', bone.rotX))[0].to_bytes(2,byteorder="little"))
                    if (bone.flags & 0x10) != 0:
                        AnimDataSection.write(struct.unpack('H', struct.pack('e', bone.rotY))[0].to_bytes(2,byteorder="little"))
                    if (bone.flags & 0x20) != 0:
                        AnimDataSection.write(struct.unpack('H', struct.pack('e', bone.rotZ))[0].to_bytes(2,byteorder="little"))
            AnimSeqSection.write(AnimDataSection.getvalue())
        mani.write(AnimSeqSection.getvalue())
        with open(filepath+"mani", "wb") as f:
            f.write(mani.getbuffer())

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
    
    add_anim: BoolProperty(
        name="Add animations",
        description="Create MANI file.",
        default=False,
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
        layout.prop(self, "add_anim")

    def execute(self, context):
        return main(self,context, self.filepath, self.add_tex, self.add_phy, self.add_anim, self.tex_type, self.vtfcmd_path)

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
    
#MANI
class mani_st:
    id = 1229865293
    version = 1
    checksum = 0
    
    num_sequences = 0
    seq_offset = 0
    
class manimseq_st:
    index = 0
    name = []
    numFrames = 0
    fps = 24 # got real
    
    frames = []
    
class manimdata_st:
    frame = 0
    bone = []
    
class mbonepos_t:
    flags = 0x0
    boneIndex = 0
    posX = 0
    posY = 0
    posZ = 0
    rotX = 0
    rotY = 0
    rotZ = 0

class MBONEFLAGS:
    NOCHANGES = 0x0
    POSX = 0x1
    POSY = 0x2
    POSZ = 0x4
    ROTX = 0x8
    ROTY = 0x10
    ROTZ = 0x20