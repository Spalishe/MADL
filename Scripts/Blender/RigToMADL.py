# Made by Spalishe for github.com/Spalishe/MADL
import bpy
import mathutils
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator
import io
import random

def writeMADL(context, filepath):
    MST = madl_st()
    CHCKSUM = random.randint(-2147483648,2147483647)
    MST.checksum = CHCKSUM
    
    def is_attached_to_rig(obj, rig):
        if obj.parent == rig:
            return True
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE' and mod.object == rig:
                return True
        return False

    selected_objs = bpy.context.selected_objects

    rigs = [obj for obj in selected_objs if obj.type == 'ARMATURE']
    meshes = [obj for obj in selected_objs if obj.type == 'MESH']

    if len(rigs) > 1:
        print("Ошибка: выбрано больше одного рига.")
        raise SystemExit("Выбрано больше одного рига.")

    if len(rigs) == 1:
        rig = rigs[0]
        for obj in meshes:
            if not is_attached_to_rig(obj, rig):
                print(f"Ошибка: объект {obj.name} не привязан к ригу {rig.name}.")
                raise SystemExit("Обнаружены объекты, не привязанные к ригу.")

    if len(rigs) == 1:
        rig = rigs[0]
        bones = list(rig.data.bones)  # Преобразуем к список для удобства получения индекса
        bone_table = []
        for index, bone in enumerate(bones):
            # Если у кости есть родитель, получаем его индекс из списка bones
            if bone.parent:
                parent_index = bones.index(bone.parent)
                bone_position = bone.head_local - bone.parent.head_local

                # Вычисляем разницу Эйлеровых углов по компонентам
                euler_current = bone.matrix_local.to_euler()
                euler_parent = bone.parent.matrix_local.to_euler()
                bone_angle = (
                    euler_current[0] - euler_parent[0],
                    euler_current[1] - euler_parent[1],
                    euler_current[2] - euler_parent[2]
                )
            else:
                parent_index = -1  # Если родителя нет, присваиваем -1
                bone_position = bone.head_local
                euler_current = bone.matrix_local.to_euler()
                bone_angle = (euler_current[0], euler_current[1], euler_current[2])

            # Формируем запись таблицы: [индекс, имя кости, индекс родителя, позиция, угол]
            st = mbone_st()
            st.index = index
            st.name = list(name)
            st.parent = parent_index
            st.bone_position = bone_position
            st.bone_angle = bone_angle
            bone_table.append(st)

        print("Таблица костей рига:")
        for row in bone_table:
            print(row)

    if len(rigs) == 0:
        #selected no rigs, only objects
        pass
    
    with io.BytesIO(b'') as file:
        file.write(MST.id.to_bytes(4, byteorder="little"))
        file.write(MST.version.to_bytes(4, byteorder="little"))
        file.write(MST.checksum.to_bytes(4, byteorder="little"))
        with open(filepath, "wb") as f:
            f.write(file.getbuffer())
    
    return {'FINISHED'}

class madl_st:
    id = 1818517869
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
        return writeMADL(context, self.filepath)

    
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