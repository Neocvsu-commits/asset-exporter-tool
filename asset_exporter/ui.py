import bpy

from .utils import (
    get_assets_check_status,
    get_selected_meshes,
    has_unapplied_transform,
)


class ASSET_EXPORTER_V2_PT_Panel(bpy.types.Panel):
    bl_label = "资产规范导出"
    bl_idname = "ASSET_EXPORTER_V2_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Export"

    def draw(self, context):
        layout = self.layout
        props = context.scene.asset_exporter_v2_props
        selected_meshes = get_selected_meshes(context)
        check_status = get_assets_check_status(context, selected_meshes)

        box = layout.box()
        box.label(text="当前资产状态预览", icon="VIS_SEL_11")
        if not selected_meshes:
            box.label(text="请先在视图中选择 MESH", icon="ERROR")
        else:
            active = context.active_object
            if len(selected_meshes) == 1 and active and active.type == "MESH":
                box.label(text=f"已选中: {active.name}", icon="OBJECT_DATA")
            else:
                mode_tip = "导出将合并" if props.export_mode == "MERGED" else "将逐个导出"
                box.label(text=f"共选中 {len(selected_meshes)} 个模型（{mode_tip}）", icon="GROUP")

            if active and active.type == "MESH":
                col = box.column(align=True)
                dim_col = col.column(align=True)
                dim_col.label(text="尺寸 (XYZ):")
                dim_row = dim_col.row(align=True)
                dim_row.prop(active, "dimensions", index=0, text="X")
                dim_row.prop(active, "dimensions", index=1, text="Y")
                dim_row.prop(active, "dimensions", index=2, text="Z")

                if has_unapplied_transform(active):
                    warn = col.box()
                    warn.label(text="检测到未应用的 Transform", icon="ERROR")
                    warn.label(text="导出时将在后台副本自动应用", icon="INFO")
                else:
                    col.label(text="所有 Transform 已正确归零/应用", icon="CHECKMARK")

                info = col.row(align=True)
                info.label(text=f"面数: {len(active.data.polygons)}", icon="MESH_DATA")
                mat_count = len([s for s in active.material_slots if s.material])
                info.label(text=f"材质球: {mat_count}个", icon="MATERIAL")

                if mat_count > 0:
                    mat_box = col.box()
                    icon = "TRIA_DOWN" if props.show_materials_info else "TRIA_RIGHT"
                    mat_box.prop(props, "show_materials_info", icon=icon, text="展开插槽贴图分析详情", emboss=False)
                    if props.show_materials_info:
                        for slot in active.material_slots:
                            if not slot.material:
                                continue
                            mat = slot.material
                            mat_col = mat_box.column(align=True)
                            if mat.use_nodes and mat.node_tree:
                                tex_nodes = [n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
                                if not tex_nodes:
                                    mat_col.label(text=f"[{slot.name}] - 无贴图", icon="MATERIAL")
                                else:
                                    mat_col.label(text=f"[{slot.name}] 包含贴图:", icon="MATERIAL")
                                    for node in tex_nodes:
                                        img = node.image
                                        w, h = img.size[0], img.size[1]
                                        res_text = f"{w} x {h}" if w and h else "无数据/未加载"
                                        icon_type = "IMAGE_DATA" if w > 0 else "ERROR"
                                        mat_col.label(text=f" └ {img.name}: {res_text}", icon=icon_type)
                            else:
                                mat_col.label(text=f"[{slot.name}] - 未启用节点树", icon="INFO")

        mode_box = layout.box()
        mode_box.label(text="导出模式", icon="PREFERENCES")
        mode_box.prop(props, "export_mode", text="")

        format_box = layout.box()
        format_box.label(text="模型格式", icon="FILE_3D")
        row_format = format_box.row(align=True)
        row_format.prop(props, "export_fbx")
        row_format.prop(props, "export_glb")
        row_adv = format_box.row(align=True)
        row_adv_fbx = row_adv.row(align=True)
        row_adv_fbx.enabled = props.export_fbx
        row_adv_fbx.operator(
            "asset_exporter_v2.open_fbx_advanced_options",
            text="更多 FBX 参数",
            icon="PREFERENCES",
        )
        row_adv_glb = row_adv.row(align=True)
        row_adv_glb.enabled = props.export_glb
        row_adv_glb.operator(
            "asset_exporter_v2.open_glb_advanced_options",
            text="更多 GLB 参数",
            icon="PREFERENCES",
        )

        forward_box = layout.box()
        forward_box.label(text="定义模型正前方向（在模型原点生成参考箭头）", icon="ORIENTATION_GLOBAL")
        fwd_row = forward_box.row(align=True)
        fwd_row.prop(props, "forward_direction", text="方向")
        active_obj = context.active_object
        saved_forward = None
        if active_obj and active_obj.type == "MESH":
            saved_forward = active_obj.get("asset_export_forward_dir", None)
        forward_box.label(
            text=f"当前活动对象已保存朝向：{saved_forward if saved_forward else '未设置'}",
            icon="INFO",
        )
        forward_tip = forward_box.box()
        if props.forward_direction == "NONE":
            forward_tip.alert = True
            forward_tip.label(text="重要：请先选择模型正前方向，再执行导出", icon="ERROR")
        else:
            forward_tip.label(text="已设置模型正前方向，将写入导出信息", icon="CHECKMARK")

        extra_box = layout.box()
        extra_box.label(text="附属文件", icon="PACKAGE")
        extra_box.prop(props, "export_csv")
        extra_box.prop(props, "export_basic_json")
        row_check_csv = extra_box.row()
        row_check_csv.enabled = check_status["all_selected_checked"]
        row_check_csv.prop(props, "export_check_csv")
        row_check_json = extra_box.row()
        row_check_json.enabled = check_status["all_selected_checked"]
        row_check_json.prop(props, "export_check_json")
        if not check_status["all_selected_checked"]:
            extra_box.label(text=f"审查 CSV/JSON 不可用：{check_status['reason']}", icon="INFO")

        extra_box.prop(props, "export_blend")
        extra_box.prop(props, "export_textures")

        name_box = layout.box()
        name_box.label(text="导出命名", icon="SORTALPHA")
        if props.export_mode == "MERGED":
            name_box.label(text="预设已填入下方，可点刷新同步物体名", icon="INFO")
            row_name = name_box.row(align=True)
            row_name.prop(props, "export_base_name", text="主名称")
            row_name.operator("asset_exporter_v2.refresh_export_name", text="", icon="FILE_REFRESH")
        else:
            name_box.label(text="逐个导出时将使用各物体名", icon="BLANK1")
        name_box.prop(props, "export_chinese_name", text="中文名称")

        hint_box = layout.box()
        if props.export_textures:
            hint_box.label(text="安全模式提取关联贴图（不影响原盘）", icon="CHECKMARK")
        else:
            hint_box.label(text="已关闭贴图提取，仅导出模型文件", icon="INFO")

        layout.separator()
        layout.prop(props, "export_layout", text="导出结构")
        op_row = layout.row()
        has_any_output = any([
            props.export_fbx,
            props.export_glb,
            props.export_csv,
            props.export_basic_json,
            props.export_check_csv,
            props.export_check_json,
            props.export_blend,
            props.export_textures,
        ])
        op_row.enabled = len(selected_meshes) > 0 and has_any_output
        op_row.operator("export_scene.norm_asset_v2", text="选择目录并导出", icon="EXPORT")
        layout.operator(
            "asset_exporter_v2.open_last_export_dir",
            text="打开上次导出目录",
            icon="FILE_FOLDER",
        )
