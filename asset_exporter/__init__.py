bl_info = {
    "name": "资产导出助手",
    "description": "资产规范化导出：FBX/GLB、基础信息与审查报告、Blend 与贴图提取（正式版）",
    "author": "Neo",
    "version": (2, 3, 8),
    "blender": (3, 6, 0),
    "location": "3D 视图 > N 面板 > Asset Export",
    "warning": "",
    "wiki_url": "",
    "category": "Import-Export",
}

import bpy

if "bpy" in locals():
    import importlib
    if "properties" in locals():
        importlib.reload(properties)
    if "utils" in locals():
        importlib.reload(utils)
    if "operators" in locals():
        importlib.reload(operators)
    if "ui" in locals():
        importlib.reload(ui)

from . import properties
from . import utils
from . import operators
from . import ui


classes = (
    properties.ASSET_EXPORTER_V2_Properties,
    operators.ASSET_EXPORTER_V2_OT_RefreshExportName,
    operators.ASSET_EXPORTER_V2_OT_Export,
    operators.ASSET_EXPORTER_V2_OT_OpenLastExportDir,
    operators.ASSET_EXPORTER_V2_OT_OpenFBXAdvancedOptions,
    operators.ASSET_EXPORTER_V2_OT_OpenGLBAdvancedOptions,
    ui.ASSET_EXPORTER_V2_PT_Panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.asset_exporter_v2_props = bpy.props.PointerProperty(type=properties.ASSET_EXPORTER_V2_Properties)


def unregister():
    if hasattr(bpy.types.Scene, "asset_exporter_v2_props"):
        del bpy.types.Scene.asset_exporter_v2_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
