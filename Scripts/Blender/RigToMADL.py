# Made by Spalishe for github.com/Spalishe/MADL
import bpy
import mathutils
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator
import io
import random
import struct

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
        MST.name = list(rig.name.encode("utf-8").ljust(32,b"\x00").decode("utf-8"))
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
            print(parent_index)
            st.parent = parent_index
            st.bone_position = bone_position
            st.bone_angle = bone_angle
            bone_table.append(st)
            
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