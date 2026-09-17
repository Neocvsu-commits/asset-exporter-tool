import bpy

from .utils import (
    get_assets_check_status,
    get_selected_meshes,
    has_unapplied_transform,
)


def _draw_update_banner(layout):
    """Always show the installed version and the update entry in the working UI."""
    from . import bl_info
    from .update_checker import get_update_info, get_check_status

    row = layout.row(align=True)
    row.alignment = "LEFT"
    row.label(text="v" + ".".join(map(str, bl_info["version"])), icon="INFO")
    row.operator("asset_exporter_v2.check_update", text="检查更新", icon="FILE_REFRESH")
    status = get_check_status("Neocvsu-commits", "asset-exporter-tool")
    state = status.get("status", "pending")
    if state == "checking":
        row.label(text="检查中…", icon="SORTTIME")
    elif state == "no_update":
        row.label(text="已是最新版", icon="CHECKMARK")
    elif state == "error":
        layout.label(text="更新检查失败，请重试", icon="ERROR")
    elif state == "no_release":
        row.label(text="暂无发布版本", icon="INFO")

    info = get_update_info("Neocvsu-commits", "asset-exporter-tool")
    if info:
        update_row = layout.row(align=True)
        update_row.alert = True
        update_row.label(text=f"可更新至 v{info['latest_version']}", icon="IMPORT")
        update_row.operator("asset_exporter_v2.install_update", text="一键更新", icon="IMPORT")
        update_row.operator("wm.url_open", text="更新说明", icon="URL").url = info["html_url"]



class ASSET_EXPORTER_V2_PT_Panel(bpy.types.Panel):
    bl_label = "资产规范导出"
    bl_idname = "ASSET_EXPORTER_V2_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Export"

    def draw(self, context):
        layout = self.layout
        _draw_update_banner(layout)
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
                mode_tip = "将打成一个文件（内多物体）" if props.export_mode == "MERGED" else "将按物体各出一套文件"
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

        # ---- GLB 快捷设置 ----
        if props.export_glb:
            glb_row = format_box.row(align=True)
            glb_row.prop(props, "glb_draco_compression")
            glb_row.prop(props, "glb_image_format", text="贴图")

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
        row_name = name_box.row(align=True)
        row_name.prop(props, "export_base_name", text="主名称")
        row_name.operator("asset_exporter_v2.refresh_export_name", text="", icon="FILE_REFRESH")
        name_box.prop(props, "export_chinese_name", text="中文名称")

        layout.separator()
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



def draw_support_preferences(layout):
    _draw_update_banner(layout)
    layout.separator()
    feedback_box = layout.box()
    feedback_box.label(text="反馈 & 支持", icon="HELP")
    fb_row = feedback_box.row(align=True)
    fb_row.operator(
        "wm.url_open",
        text="Bug / 功能建议",
        icon="GHOST_ENABLED",
    ).url = "https://github.com/Neocvsu-commits/asset-exporter-tool/issues/new"
    fb_row.operator(
        "wm.url_open",
        text="匿名反馈",
        icon="COMMUNITY",
    ).url = "https://docs.qq.com/form/page/DTm5sVnJuTkpSbGZ5?templateId=25000&create_type=2&no_promotion=1&is_blank_or_template=blank#/fill"
    fb_row2 = feedback_box.row()
    fb_row2.operator(
        "wm.url_open",
        text="⭐ 作者主页（了解更多工具）",
        icon="URL",
    ).url = "https://github.com/Neocvsu-commits"
