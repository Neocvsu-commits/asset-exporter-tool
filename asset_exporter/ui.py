import bpy

from .utils import get_assets_check_status, get_selected_meshes


def _format_dim(value):
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _draw_update_banner(layout):
    from . import bl_info
    from .update_checker import get_check_status, get_update_info

    repo = ("Neocvsu-commits", "asset-exporter-tool")
    state = get_check_status(*repo).get("status")
    text, icon = {
        "checking": ("检查中…", "SORTTIME"),
        "no_update": ("已是最新版", "CHECKMARK"),
        "error": ("重试", "ERROR"),
        "no_release": ("暂无发布", "INFO"),
    }.get(state, ("检查更新", "FILE_REFRESH"))

    row = layout.row(align=True)
    row.alignment = "LEFT"
    ver = row.row(align=True)
    ver.alignment = "LEFT"
    ver.active = False
    ver.label(text="v" + ".".join(map(str, bl_info["version"])), translate=False)
    info = get_update_info(*repo)
    row.operator("asset_exporter_v2.check_update", text="" if info else text, icon=icon)

    if info:
        update_row = layout.row(align=True)
        update_row.alert = True
        update_row.operator(
            "asset_exporter_v2.install_update",
            text=f"更新至 v{info['latest_version']}",
            icon="IMPORT",
        )
        update_row.operator("wm.url_open", text="", icon="URL").url = info["html_url"]


def _disclosure(layout, props, prop_name, text, *, translate=True):
    expanded = getattr(props, prop_name)
    icon = "TRIA_DOWN" if expanded else "TRIA_RIGHT"
    row = layout.row(align=True)
    row.alignment = "LEFT"
    row.prop(props, prop_name, text=text, icon=icon, emboss=False, translate=translate)
    return expanded


def _draw_field(layout, label, *, alert=False, enabled=True):
    split = layout.split(factor=0.34, align=False)
    split.enabled = enabled
    lbl = split.row(align=True)
    lbl.alignment = "RIGHT"
    lbl.label(text=label)
    val = split.row(align=True)
    val.alert = alert
    return val


def _draw_asset_preview(layout, props, meshes, active):
    box = layout.box()
    if not meshes:
        row = box.row(align=True)
        row.active = False
        row.label(text="请选择网格物体", icon="MESH_DATA")
        return

    target = active if active in meshes else meshes[0]
    title = target.name if len(meshes) == 1 else f"已选 {len(meshes)} 个网格"
    if not _disclosure(box, props, "show_asset_details", title, translate=False):
        return

    col = box.column(align=True)
    if len(meshes) > 1:
        col.label(text=target.name, icon="OBJECT_DATA", translate=False)
    dims = target.dimensions
    dim_text = f"{_format_dim(dims.x)} × {_format_dim(dims.y)} × {_format_dim(dims.z)} m"
    col.label(text=f"{len(target.data.polygons):,} 面", icon="MESH_DATA", translate=False)
    col.label(text=dim_text, icon="EMPTY_AXIS", translate=False)

    slots = [slot for slot in target.material_slots if slot.material]
    if not slots:
        empty = col.row(align=True)
        empty.active = False
        empty.label(text="无材质", icon="MATERIAL")
        return
    if not _disclosure(box, props, "show_materials_info", f"材质 ({len(slots)})", translate=False):
        return

    mat_col = box.column(align=True)
    for slot in slots:
        mat = slot.material
        if not mat.use_nodes or not mat.node_tree:
            mat_col.label(text=f"{slot.name} · 无节点", icon="MATERIAL", translate=False)
            continue
        images = [n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
        mat_col.label(text=slot.name if images else f"{slot.name} · 无贴图", icon="MATERIAL", translate=False)
        for img in images:
            width, height = img.size
            size = f"{width}×{height}" if width and height else "未加载"
            sub = mat_col.row(align=True)
            sub.separator(factor=1.2)
            sub.label(
                text=f"{img.name} ({size})",
                icon="IMAGE_DATA" if width and height else "ERROR",
                translate=False,
            )


def _draw_extra_files(layout, context, props, meshes):
    box = layout.box()
    if not _disclosure(box, props, "show_extra_files", "附属文件"):
        return

    check_status = get_assets_check_status(context, meshes)
    review_ready = check_status["all_selected_checked"]

    col = box.column(align=True)
    for label, csv_prop, json_prop, enabled in (
        ("基础信息", "export_csv", "export_basic_json", True),
        ("资产审查", "export_check_csv", "export_check_json", review_ready),
    ):
        split = col.split(factor=0.38, align=True)
        split.enabled = enabled
        split.label(text=label)
        checks = split.row(align=True)
        checks.prop(props, csv_prop, text="CSV")
        checks.prop(props, json_prop, text="JSON")

    if meshes and not review_ready:
        hint = box.row(align=True)
        hint.active = False
        hint.label(text="需先审查所选网格" if check_status["backend"] else "未启用资产审查")

    box.separator(factor=0.3)
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
        if props.export_mode == "MERGED":
            val = _draw_field(names, "主名称")
            val.prop(props, "export_base_name", text="")
            val.operator("asset_exporter_v2.refresh_export_name", text="", icon="FILE_REFRESH")
        _draw_field(names, "中文名称").prop(props, "export_chinese_name", text="")

        val = _draw_field(
            layout,
            "正前方向",
            alert=bool(meshes) and props.forward_direction == "NONE",
            enabled=bool(meshes),
        )
        val.prop(props, "forward_direction", text="")

        formats = layout.box()
        for label, toggle, operator in (
            ("FBX", "export_fbx", "asset_exporter_v2.open_fbx_advanced_options"),
            ("GLB", "export_glb", "asset_exporter_v2.open_glb_advanced_options"),
        ):
            row = formats.row(align=True)
            row.prop(props, toggle, text=label)
            settings = row.row(align=True)
            settings.alignment = "RIGHT"
            settings.enabled = getattr(props, toggle)
            settings.operator(operator, text="", icon="PREFERENCES")
            if toggle == "export_glb" and props.export_glb:
                sub = formats.row(align=False)
                sub.separator(factor=1.2)
                split = sub.split(factor=0.42, align=False)
                split.prop(props, "glb_draco_compression", text="Draco")
                fmt_row = split.row(align=False)
                fmt_row.use_property_split = True
                fmt_row.use_property_decorate = False
                fmt_row.prop(props, "glb_image_format", text="贴图")

        _draw_extra_files(layout, context, props, meshes)

        has_output = any((
            props.export_fbx, props.export_glb, props.export_csv, props.export_basic_json,
            props.export_check_csv, props.export_check_json, props.export_blend, props.export_textures,
        ))
        row = layout.row(align=True)
        row.scale_y = 1.25
        export = row.row(align=True)
        export.enabled = bool(meshes) and has_output
        export_text = "选择目录并导出" if (not meshes or has_output) else "未勾选导出项"
        export.operator("export_scene.norm_asset_v2", text=export_text, icon="EXPORT")
        row.operator("asset_exporter_v2.open_last_export_dir", text="", icon="FILE_FOLDER")


def draw_support_preferences(layout):
    _draw_update_banner(layout)
    layout.separator()
    row = layout.row(align=True)
    row.operator("wm.url_open", text="问题与建议", icon="HELP").url = "https://github.com/Neocvsu-commits/asset-exporter-tool/issues/new"
    row.operator("wm.url_open", text="匿名反馈", icon="COMMUNITY").url = "https://docs.qq.com/form/page/DTm5sVnJuTkpSbGZ5?templateId=25000&create_type=2&no_promotion=1&is_blank_or_template=blank#/fill"
    row.operator("wm.url_open", text="作者主页", icon="URL").url = "https://github.com/Neocvsu-commits"
