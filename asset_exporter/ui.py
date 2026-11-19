import bpy

from .utils import get_assets_check_status, get_selected_meshes, has_unapplied_transform


def _draw_update_banner(layout):
    from . import bl_info
    from .update_checker import get_check_status, get_update_info

    repo = ("Neocvsu-commits", "asset-exporter-tool")
    state = get_check_status(*repo).get("status")
    text, icon = {
        "checking": ("检查中…", "SORTTIME"),
        "no_update": ("已是最新版", "CHECKMARK"),
        "error": ("检查失败，重试", "ERROR"),
        "no_release": ("暂无发布版本", "INFO"),
    }.get(state, ("检查更新", "FILE_REFRESH"))
    row = layout.row(align=True)
    row.label(text="v" + ".".join(map(str, bl_info["version"])))
    row.operator("asset_exporter_v2.check_update", text=text, icon=icon)

    info = get_update_info(*repo)
    if info:
        row = layout.row(align=True)
        row.operator("asset_exporter_v2.install_update", text=f"更新至 v{info['latest_version']}", icon="IMPORT")
        row.operator("wm.url_open", text="更新说明", icon="URL").url = info["html_url"]


def _disclosure(layout, props, prop_name, text):
    expanded = getattr(props, prop_name)
    icon = "TRIA_DOWN" if expanded else "TRIA_RIGHT"
    layout.prop(props, prop_name, text=text, icon=icon, emboss=False)
    return expanded


def _draw_asset_preview(layout, props, meshes, active):
    if not meshes:
        layout.label(text="请选择网格物体", icon="MESH_DATA")
        return

    if len(meshes) == 1:
        active = meshes[0]
        title = active.name
    else:
        title = f"已选 {len(meshes)} 个网格"
    if active not in meshes:
        layout.label(text=title, icon="MESH_DATA")
        return

    box = layout.box()
    if not _disclosure(box, props, "show_asset_details", title):
        return
    if len(meshes) > 1:
        box.label(text=active.name, icon="MESH_DATA")
    box.label(text=f"{len(active.data.polygons):,} 面", icon="MESH_DATA")
    box.label(text="尺寸")
    row = box.row(align=True)
    for index, axis in enumerate("XYZ"):
        row.prop(active, "dimensions", index=index, text=axis)
    if has_unapplied_transform(active):
        box.label(text="导出时应用变换到副本", icon="INFO")

    slots = [slot for slot in active.material_slots if slot.material]
    if not slots:
        box.label(text="无材质", icon="MATERIAL")
        return
    if not _disclosure(box, props, "show_materials_info", f"材质与贴图 ({len(slots)})"):
        return
    for slot in slots:
        mat = slot.material
        if not mat.use_nodes or not mat.node_tree:
            box.label(text=f"{slot.name} · 未启用节点", icon="MATERIAL")
            continue
        images = [n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
        box.label(text=slot.name if images else f"{slot.name} · 无贴图", icon="MATERIAL")
        for img in images:
            width, height = img.size
            size = f"{width} × {height}" if width and height else "未加载"
            box.label(text=f"{img.name} · {size}", icon="IMAGE_DATA" if width and height else "ERROR")


def _draw_extra_files(layout, context, props, meshes):
    box = layout.box()
    if not _disclosure(box, props, "show_extra_files", "附属文件"):
        return

    check_status = get_assets_check_status(context, meshes)
    basic = box.row(align=True)
    basic.label(text="基础信息")
    basic.prop(props, "export_csv", text="CSV")
    basic.prop(props, "export_basic_json", text="JSON")
    review = box.row(align=True)
    review.enabled = check_status["all_selected_checked"]
    review.label(text="资产审查")
    review.prop(props, "export_check_csv", text="CSV")
    review.prop(props, "export_check_json", text="JSON")
    if meshes and not review.enabled:
        reason = "请先审查全部所选网格" if check_status["backend"] else "请启用资产审查助手"
        box.label(text=reason, icon="INFO")
    row = box.row(align=True)
    row.prop(props, "export_blend", text="工程备份")
    row.prop(props, "export_textures", text="提取贴图")


class ASSET_EXPORTER_V2_PT_Panel(bpy.types.Panel):
    bl_label = "资产规范导出"
    bl_idname = "ASSET_EXPORTER_V2_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Export"

    def draw(self, context):
        layout = self.layout
        props = context.scene.asset_exporter_v2_props
        meshes = get_selected_meshes(context)
        active = context.active_object
        _draw_update_banner(layout)
        _draw_asset_preview(layout, props, meshes, active)

        layout.row(align=True).prop(props, "export_mode", expand=True)
        names = layout.column(align=True)
        row = names.row(align=True)
        row.prop(props, "export_base_name", text="主名称")
        row.operator("asset_exporter_v2.refresh_export_name", text="", icon="FILE_REFRESH")
        names.prop(props, "export_chinese_name", text="中文名称")

        saved = active.get("asset_export_forward_dir") if active and active.type == "MESH" else None
        direction = props.forward_direction
        row = layout.row(align=True)
        row.alert = bool(meshes) and direction == "NONE"
        row.prop(props, "forward_direction", text="正前方向")
        # The scene selector may still show the direction of the previous selection.
        axis = direction.replace("POS_", "+").replace("NEG_", "-")
        if active and active.type == "MESH" and (saved or "NONE") != axis:
            layout.label(text=f"活动物体朝向　{saved or '未设置'}", icon="INFO")

        formats = layout.box()
        row = formats.row(align=True)
        for label, toggle, operator in (
            ("FBX", "export_fbx", "asset_exporter_v2.open_fbx_advanced_options"),
            ("GLB", "export_glb", "asset_exporter_v2.open_glb_advanced_options"),
        ):
            group = row.row(align=True)
            group.prop(props, toggle, text=label)
            settings = group.row(align=True)
            settings.enabled = getattr(props, toggle)
            settings.operator(operator, text="", icon="PREFERENCES")
        if props.export_glb:
            row = formats.row(align=True)
            row.prop(props, "glb_draco_compression", text="Draco 压缩")
            row.prop(props, "glb_image_format", text="GLB 贴图")

        _draw_extra_files(layout, context, props, meshes)

        has_output = any((
            props.export_fbx, props.export_glb, props.export_csv, props.export_basic_json,
            props.export_check_csv, props.export_check_json, props.export_blend, props.export_textures,
        ))
        if meshes and not has_output:
            layout.label(text="请选择导出格式或附属文件", icon="INFO")
        row = layout.row(align=True)
        row.scale_y = 1.25
        export = row.row(align=True)
        export.enabled = bool(meshes) and has_output
        export.operator("export_scene.norm_asset_v2", text="选择目录并导出", icon="EXPORT")
        row.operator("asset_exporter_v2.open_last_export_dir", text="", icon="FILE_FOLDER")


def draw_support_preferences(layout):
    _draw_update_banner(layout)
    layout.separator()
    row = layout.row(align=True)
    row.operator("wm.url_open", text="问题与建议", icon="HELP").url = "https://github.com/Neocvsu-commits/asset-exporter-tool/issues/new"
    row.operator("wm.url_open", text="匿名反馈", icon="COMMUNITY").url = "https://docs.qq.com/form/page/DTm5sVnJuTkpSbGZ5?templateId=25000&create_type=2&no_promotion=1&is_blank_or_template=blank#/fill"
    row.operator("wm.url_open", text="作者主页", icon="URL").url = "https://github.com/Neocvsu-commits"
