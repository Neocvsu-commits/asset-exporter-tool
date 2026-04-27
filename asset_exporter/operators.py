import os
import importlib

import bpy

from .utils import (
    get_selected_meshes,
    get_suggested_merge_export_name,
    last_export_directory_is_valid,
    run_export_pipeline,
    sanitize_export_basename,
)


class ASSET_EXPORTER_V2_OT_RefreshExportName(bpy.types.Operator):
    bl_idname = "asset_exporter_v2.refresh_export_name"
    bl_label = "刷新预设名称"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "asset_exporter_v2_props", None)
        return bool(props and props.export_mode == "MERGED")

    def execute(self, context):
        props = context.scene.asset_exporter_v2_props
        props.export_base_name = get_suggested_merge_export_name(context)
        self.report({"INFO"}, f"已刷新预设名称：{props.export_base_name}")
        return {"FINISHED"}


class ASSET_EXPORTER_V2_OT_Export(bpy.types.Operator):
    bl_idname = "export_scene.norm_asset_v2"
    bl_label = "选择目录并导出"
    bl_description = "选择导出目录后直接执行导出"
    bl_options = {"REGISTER", "UNDO"}

    directory: bpy.props.StringProperty(
        name="导出目录",
        subtype="DIR_PATH",
        default="",
    )

    @classmethod
    def poll(cls, context):
        return len(get_selected_meshes(context)) > 0

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        props = context.scene.asset_exporter_v2_props
        if props.export_mode == "MERGED":
            props.export_base_name = sanitize_export_basename(props.export_base_name)
            if not props.export_base_name:
                props.export_base_name = get_suggested_merge_export_name(context)

        chosen = bpy.path.abspath(self.directory or "")
        if not chosen:
            self.report({"ERROR"}, "请选择有效导出目录")
            return {"CANCELLED"}
        return run_export_pipeline(context, chosen, self)


class ASSET_EXPORTER_V2_OT_OpenLastExportDir(bpy.types.Operator):
    bl_idname = "asset_exporter_v2.open_last_export_dir"
    bl_label = "打开上次导出目录"
    bl_description = "在系统文件管理器中打开最近一次导出所选父目录"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "asset_exporter_v2_props", None)
        if not props:
            return False
        return last_export_directory_is_valid(props)

    def execute(self, context):
        props = context.scene.asset_exporter_v2_props
        path = bpy.path.abspath(props.last_export_directory or "")
        if not path or not os.path.isdir(path):
            self.report({"WARNING"}, "上次导出目录不存在或无效")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=path)
        return {"FINISHED"}


class ASSET_EXPORTER_V2_OT_OpenFBXAdvancedOptions(bpy.types.Operator):
    bl_idname = "asset_exporter_v2.open_fbx_advanced_options"
    bl_label = "更多 FBX 参数"
    bl_description = "打开 FBX 参数弹窗（仅配置，不直接导出；参数与当前 Blender 版本一致）"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "asset_exporter_v2_props", None)
        return bool(props and props.export_fbx)

    @staticmethod
    def _apply_recommended_defaults(op_props):
        # 与统一导出流程保持一致的推荐默认值（可在弹窗中手动修改）
        defaults = {
            "use_selection": True,
            "object_types": {"MESH"},
            "global_scale": 1.0,
            "apply_unit_scale": True,
            "axis_forward": "Y",
            "axis_up": "Z",
            "bake_space_transform": True,
            "mesh_smooth_type": "FACE",
            "use_mesh_modifiers": True,
            "use_mesh_edges": False,
            "use_triangles": True,
            "use_tspace": True,
            # 纯模型策略：FBX 不保留贴图路径，不做贴图嵌入。
            "path_mode": "STRIP",
            "embed_textures": False,
        }
        for key, value in defaults.items():
            try:
                setattr(op_props, key, value)
            except Exception:
                continue

    def invoke(self, context, event):
        op_props = context.window_manager.operator_properties_last("export_scene.fbx")
        self._apply_recommended_defaults(op_props)
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        mod = importlib.import_module("io_scene_fbx")
        op_props = context.window_manager.operator_properties_last("export_scene.fbx")
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        head = layout.box()
        head.label(text="参数来源：Blender 当前版本 FBX 导出器", icon="INFO")
        head.label(text="仅记录参数；统一导出时固定“选定的物体”", icon="CHECKMARK")
        mod.export_main(layout, op_props, True)
        mod.export_panel_include(layout, op_props, True)
        mod.export_panel_transform(layout, op_props)
        mod.export_panel_geometry(layout, op_props)
        mod.export_panel_armature(layout, op_props)
        mod.export_panel_animation(layout, op_props)

    def execute(self, context):
        self.report({"INFO"}, "FBX 参数已更新，将在“选择目录并导出”时生效")
        return {"FINISHED"}


class ASSET_EXPORTER_V2_OT_OpenGLBAdvancedOptions(bpy.types.Operator):
    bl_idname = "asset_exporter_v2.open_glb_advanced_options"
    bl_label = "更多 GLB 参数"
    bl_description = "打开 GLB 参数弹窗（仅配置，不直接导出；参数与当前 Blender 版本一致）"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = getattr(context.scene, "asset_exporter_v2_props", None)
        return bool(props and props.export_glb)

    @staticmethod
    def _apply_recommended_defaults(op_props):
        # 与统一导出流程保持一致的推荐默认值（可在弹窗中手动修改）
        defaults = {
            "export_format": "GLB",
            "use_selection": True,
            "export_apply": True,
            "export_texcoords": True,
            "export_normals": True,
            "export_tangents": False,
            "export_colors": True,
            "export_materials": "EXPORT",
            "export_animations": True,
            "export_yup": True,
        }
        for key, value in defaults.items():
            try:
                setattr(op_props, key, value)
            except Exception:
                continue

    def invoke(self, context, event):
        op_props = context.window_manager.operator_properties_last("export_scene.gltf")
        self._apply_recommended_defaults(op_props)
        return context.window_manager.invoke_props_dialog(self, width=560)

    def draw(self, context):
        mod = importlib.import_module("io_scene_gltf2")
        op_props = context.window_manager.operator_properties_last("export_scene.gltf")
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        head = layout.box()
        head.label(text="参数来源：Blender 当前版本 GLTF/GLB 导出器", icon="INFO")
        head.label(text="仅记录参数；统一导出时固定“GLB + 选定的物体”", icon="CHECKMARK")
        mod.export_main(layout, op_props, True)
        mod.export_panel_collection(layout, op_props, True)
        mod.export_panel_include(layout, op_props, True)
        mod.export_panel_transform(layout, op_props)
        mod.export_panel_data(layout, op_props)
        mod.export_panel_animation(layout, op_props)
        gltfpack_path = context.preferences.addons['io_scene_gltf2'].preferences.gltfpack_path_ui.strip()
        if gltfpack_path != "":
            mod.export_panel_gltfpack(layout, op_props)
        mod.export_panel_user_extension(context, layout)

    def execute(self, context):
        self.report({"INFO"}, "GLB 参数已更新，将在“选择目录并导出”时生效")
        return {"FINISHED"}
