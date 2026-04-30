import bpy
import os
import sys
import csv
import json
import shutil
import addon_utils
import math
from mathutils import Matrix

FBX_BLOCKED_KEYS = {
    "rna_type",
    "filepath",
    "check_existing",
    "filter_glob",
    "filemode",
    "display_type",
    "sort_method",
    "use_selection",
}

GLB_BLOCKED_KEYS = {
    "rna_type",
    "filepath",
    "check_existing",
    "filter_glob",
    "filemode",
    "display_type",
    "sort_method",
    "use_selection",
    "export_format",
}


def sanitize_export_basename(name: str) -> str:
    if not name:
        return ""
    clean = name.strip().replace(".", "_")
    for c in '\\/*?:"<>|':
        clean = clean.replace(c, "_")
    return clean.strip(" .")


def _collect_operator_last_kwargs(op_idname: str, blocked_keys=None):
    """
    收集 Blender 原生导出算子上一次设置的全部参数。
    用于“更多参数”统一在一键导出阶段生效。
    """
    blocked = set(blocked_keys or set())
    wm = bpy.context.window_manager
    op_props = wm.operator_properties_last(op_idname)
    kwargs = {}
    for prop in op_props.bl_rna.properties:
        pid = prop.identifier
        if pid in blocked:
            continue
        if getattr(prop, "is_hidden", False) or getattr(prop, "is_readonly", False):
            continue
        try:
            kwargs[pid] = getattr(op_props, pid)
        except Exception:
            continue
    return kwargs


def collect_fbx_kwargs():
    return _collect_operator_last_kwargs("export_scene.fbx", blocked_keys=FBX_BLOCKED_KEYS)


def collect_glb_kwargs():
    return _collect_operator_last_kwargs("export_scene.gltf", blocked_keys=GLB_BLOCKED_KEYS)


def strip_texture_links_for_fbx_export(obj):
    """
    在导出副本上剥离贴图节点引用，确保 FBX 为“纯模型”输出。
    仅处理副本对象，避免影响原场景材质。
    """
    if not obj or obj.type != "MESH":
        return

    for slot in obj.material_slots:
        mat = slot.material
        if not mat:
            continue
        # 复制一份材质再处理，防止改到原始材质数据块
        mat_local = mat.copy()
        slot.material = mat_local
        if not (mat_local.use_nodes and mat_local.node_tree):
            continue

        nodes = mat_local.node_tree.nodes
        tex_nodes = [n for n in nodes if n.type == "TEX_IMAGE"]
        for node in tex_nodes:
            try:
                nodes.remove(node)
            except Exception:
                continue


def get_selected_meshes(context):
    return [obj for obj in context.selected_objects if obj.type == "MESH"]


def get_suggested_merge_export_name(context) -> str:
    meshes = get_selected_meshes(context)
    if not meshes:
        return ""
    active = context.active_object
    if active and active.type == "MESH" and active in meshes:
        return active.name.replace(".", "_")
    return meshes[0].name.replace(".", "_")


def has_unapplied_transform(obj):
    loc = obj.location
    rot = obj.rotation_euler
    scale = obj.scale
    has_loc = abs(loc.x) > 0.001 or abs(loc.y) > 0.001 or abs(loc.z) > 0.001
    has_rot = abs(rot.x) > 0.001 or abs(rot.y) > 0.001 or abs(rot.z) > 0.001
    has_scale = abs(scale.x - 1.0) > 0.001 or abs(scale.y - 1.0) > 0.001 or abs(scale.z - 1.0) > 0.001
    return has_loc or has_rot or has_scale


def get_transform_status(obj):
    loc = obj.location
    rot = obj.rotation_euler
    scale = obj.scale
    has_loc = abs(loc.x) > 0.001 or abs(loc.y) > 0.001 or abs(loc.z) > 0.001
    has_rot = abs(rot.x) > 0.001 or abs(rot.y) > 0.001 or abs(rot.z) > 0.001
    has_scale = abs(scale.x - 1.0) > 0.001 or abs(scale.y - 1.0) > 0.001 or abs(scale.z - 1.0) > 0.001
    return has_loc, has_rot, has_scale


def collect_texture_details(obj):
    texture_details = []
    seen_images = set()
    for slot in obj.material_slots:
        mat = slot.material
        if not (mat and mat.use_nodes and mat.node_tree):
            continue
        for node in mat.node_tree.nodes:
            if node.type != "TEX_IMAGE" or not node.image:
                continue
            img = node.image
            if img.name in seen_images:
                continue
            seen_images.add(img.name)
            w, h = img.size[0], img.size[1]
            resolution = f"{w}x{h}" if w and h else "无数据/未加载"
            source_path = "Packed In Blend File" if img.packed_file else bpy.path.abspath(img.filepath)
            texture_details.append((img.name, resolution, source_path))
    return texture_details


def _has_animation_data(id_block):
    anim = getattr(id_block, "animation_data", None)
    if not anim:
        return False
    if getattr(anim, "action", None):
        return True
    nla_tracks = getattr(anim, "nla_tracks", None)
    if nla_tracks:
        try:
            for tr in nla_tracks:
                strips = getattr(tr, "strips", None)
                if strips and len(strips) > 0:
                    return True
        except Exception:
            return False
    return False


def _normalize_basic_info_global_quat(global_quat):
    """与 BasicInformation CSV/JSON 一致：恒为 [W,X,Y,Z] 四元数，缺省为单位四元数。"""
    identity = [1.0, 0.0, 0.0, 0.0]
    if not global_quat or len(global_quat) != 4:
        return identity
    try:
        return [round(float(global_quat[i]), 6) for i in range(4)]
    except (TypeError, ValueError):
        return identity


def get_animation_and_rig_status(obj):
    if not obj or getattr(obj, "type", None) != "MESH":
        return False, False, []

    is_rigged = False
    armature_obj = None
    try:
        for mod in getattr(obj, "modifiers", []) or []:
            if getattr(mod, "type", None) == "ARMATURE":
                is_rigged = True
                target = getattr(mod, "object", None)
                if target and getattr(target, "type", None) == "ARMATURE":
                    armature_obj = target
                break
    except Exception:
        pass

    try:
        parent = getattr(obj, "parent", None)
        if parent and getattr(parent, "type", None) == "ARMATURE":
            is_rigged = True
            if not armature_obj:
                armature_obj = parent
    except Exception:
        pass

    animation_types = []
    if armature_obj and _has_animation_data(armature_obj):
        animation_types.append("骨骼动画")

    shape_keys = None
    try:
        mesh_data = getattr(obj, "data", None)
        shape_keys = getattr(mesh_data, "shape_keys", None) if mesh_data else None
    except Exception:
        shape_keys = None

    if shape_keys and _has_animation_data(shape_keys):
        animation_types.append("形态键动画")

    has_animation = bool(animation_types)
    return is_rigged, has_animation, animation_types


def write_basic_information_csv(obj, report_path, model_file_path, export_textures, asset_chinese_name, asset_name_override=None, forward_axis="未定义", global_quat=None):
    obj.data.calc_loop_triangles()
    tri_count = len(obj.data.loop_triangles)
    has_loc, has_rot, has_scale = get_transform_status(obj)
    material_names = [slot.material.name for slot in obj.material_slots if slot.material]
    texture_details = collect_texture_details(obj)
    dimensions = obj.dimensions
    asset_name = asset_name_override or obj.name
    is_rigged, has_animation, animation_types = get_animation_and_rig_status(obj)
    animation_types_csv = "无" if not has_animation else " | ".join(animation_types)

    excel_safe_forward_axis = forward_axis
    if forward_axis in ["+X", "-X", "+Y", "-Y", "+Z", "-Z"]:
        excel_safe_forward_axis = f"{forward_axis[1]}轴 ({'正' if forward_axis[0] == '+' else '负'})"
        
    rows = [
        ["检查项", "结果", "状态", "备注"],
        ["资产名称", asset_name, "PASS", "导出资产名称（与文件名同源）"],
        ["资产中文名称", asset_chinese_name or "", "INFO", "仅用于中文检索/开发读取"],
        ["模型文件名", os.path.basename(model_file_path) if model_file_path else "未导出模型文件", "PASS", "主导出模型文件"],
        ["尺寸 X", f"{dimensions.x:.3f}", "INFO", "单位：米 (m)"],
        ["尺寸 Y", f"{dimensions.y:.3f}", "INFO", "单位：米 (m)"],
        ["尺寸 Z", f"{dimensions.z:.3f}", "INFO", "单位：米 (m)"],
        ["三角面数", str(tri_count), "INFO", "合并后网格的三角面数量 (Tris)"],
        ["材质球数量", str(len(material_names)), "INFO", "有效材质槽统计"],
        ["材质球名称", " | ".join(material_names) if material_names else "无", "INFO", "合并后材质列表"],
        ["贴图导出开关", "开启" if export_textures else "关闭", "INFO", "来自插件导出选项"],
        ["贴图数量", str(len(texture_details)), "INFO", "唯一贴图节点统计"],
        ["位置归零检查", "未归零" if has_loc else "已归零", "WARNING" if has_loc else "PASS", "导出时会自动修复"],
        ["旋转应用检查", "未应用" if has_rot else "已应用", "WARNING" if has_rot else "PASS", "导出时会自动修复"],
        ["缩放归一检查", "未归一" if has_scale else "已归一", "WARNING" if has_scale else "PASS", "导出时会自动修复"],
        ["是否绑定骨骼", "是" if is_rigged else "否", "INFO", "检测 ARMATURE 修改器或父级为骨骼对象"],
        ["是否包含动画", "是" if has_animation else "否", "INFO", "检测骨骼动画与形态键动画"],
        ["动画类型", animation_types_csv, "INFO", "骨骼动画 | 形态键动画；无则为“无”"],
        ["模型正前方向", excel_safe_forward_axis, "INFO", "来自导出界面的辅助箭头标记"],
        [
            "全局旋转四元数",
            str(_normalize_basic_info_global_quat(global_quat)),
            "INFO",
            "[W, X, Y, Z] 格式 (从世界矩阵提取)",
        ],
    ]

    if texture_details:
        for img_name, resolution, source_path in texture_details:
            rows.append(["贴图详情", img_name, "INFO", f"{resolution} | {source_path}"])
    else:
        rows.append(["贴图详情", "无", "INFO", "当前对象未检测到贴图节点"])

    with open(report_path, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(rows)


def write_basic_information_json(obj, json_path, model_file_path, export_textures, asset_chinese_name, asset_name_override=None, forward_axis="未定义", global_quat=None):
    obj.data.calc_loop_triangles()
    tri_count = len(obj.data.loop_triangles)
    has_loc, has_rot, has_scale = get_transform_status(obj)
    material_names = [slot.material.name for slot in obj.material_slots if slot.material]
    texture_details = collect_texture_details(obj)
    dimensions = obj.dimensions
    asset_name = asset_name_override or obj.name
    is_rigged, has_animation, animation_types = get_animation_and_rig_status(obj)
    quat_norm = _normalize_basic_info_global_quat(global_quat)

    # 字段顺序与数值精度与 *_BasicInformation.json 样例（SM_BDX01 / SM_SHQD01）一致
    payload = {
        "asset_name": asset_name,
        "asset_chinese_name": asset_chinese_name or "",
        "model_file_name": os.path.basename(model_file_path) if model_file_path else "未导出模型文件",
        "dimensions_meters": {
            "x": round(float(dimensions.x), 3),
            "y": round(float(dimensions.y), 3),
            "z": round(float(dimensions.z), 3),
        },
        "triangle_count": int(tri_count),
        "material_count": int(len(material_names)),
        "material_names": material_names,
        "export_textures_enabled": bool(export_textures),
        "texture_count": int(len(texture_details)),
        "transform_check": {
            "location_not_zero": bool(has_loc),
            "rotation_not_applied": bool(has_rot),
            "scale_not_unified": bool(has_scale),
        },
        "rig_and_animation": {
            "is_rigged": bool(is_rigged),
            "has_animation": bool(has_animation),
            "animation_types": list(animation_types),
        },
        "forward_axis": forward_axis,
        "global_rotation_quaternion": quat_norm,
        "texture_details": [
            {"name": n, "resolution": r, "source_path": p} for (n, r, p) in texture_details
        ],
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def get_image_extension(img):
    filepath = img.filepath
    if filepath:
        _, ext = os.path.splitext(filepath)
        if ext:
            return ext.lower()
    return getattr(img, "file_format", "PNG").lower().replace("jpeg", "jpg")


def copy_or_extract_image(img, target_dir):
    img_name = img.name
    ext = get_image_extension(img)
    if not img_name.lower().endswith(ext):
        if not ext.startswith("."):
            ext = "." + ext
        img_name += ext

    target_path = os.path.join(target_dir, img_name)
    if os.path.exists(target_path):
        return target_path

    if img.packed_file:
        orig_path = img.filepath
        try:
            img.filepath_raw = target_path
            img.save()
        except Exception:
            pass
        finally:
            img.filepath_raw = orig_path
    else:
        abs_path = bpy.path.abspath(img.filepath)
        if os.path.exists(abs_path):
            try:
                shutil.copy2(abs_path, target_path)
            except Exception:
                pass
        elif getattr(img, "has_data", False):
            orig_path = img.filepath
            try:
                img.filepath_raw = target_path
                img.save()
            except Exception:
                pass
            finally:
                img.filepath_raw = orig_path
    return target_path


def export_selected_objects_to_blend(filepath, objects, scene_name="Scene", collection_name="Collection"):
    export_blocks = set()
    queue = [obj for obj in (objects or []) if obj]
    visited_names = set()

    while queue:
        obj = queue.pop(0)
        if not obj or obj.name in visited_names:
            continue
        visited_names.add(obj.name)
        export_blocks.add(obj)

        obj_data = getattr(obj, "data", None)
        if obj_data:
            export_blocks.add(obj_data)

        anim = getattr(obj, "animation_data", None)
        if anim and getattr(anim, "action", None):
            export_blocks.add(anim.action)

        if getattr(obj, "type", None) == "MESH":
            for slot in getattr(obj, "material_slots", []) or []:
                mat = slot.material
                if not mat:
                    continue
                export_blocks.add(mat)
                node_tree = getattr(mat, "node_tree", None)
                if not node_tree:
                    continue
                export_blocks.add(node_tree)
                for node in node_tree.nodes:
                    if node.type == "TEX_IMAGE" and node.image:
                        export_blocks.add(node.image)

            for mod in getattr(obj, "modifiers", []) or []:
                if getattr(mod, "type", None) == "ARMATURE":
                    arm_obj = getattr(mod, "object", None)
                    if arm_obj:
                        queue.append(arm_obj)

            parent = getattr(obj, "parent", None)
            if parent and getattr(parent, "type", None) == "ARMATURE":
                queue.append(parent)

    if not export_blocks:
        raise RuntimeError("没有可写入 Blend 的对象数据")

    desired_scene_name = scene_name or "Scene"
    desired_collection_name = collection_name or "Collection"
    reserved_scene = reserve_id_name_for_export(bpy.data.scenes, desired_scene_name)
    reserved_collection = reserve_id_name_for_export(bpy.data.collections, desired_collection_name)

    temp_scene = bpy.data.scenes.new(name=desired_scene_name)
    temp_collection = bpy.data.collections.new(name=desired_collection_name)
    temp_scene.collection.children.link(temp_collection)

    linked_objects = []
    for obj in [o for o in (objects or []) if o]:
        if obj.name in bpy.data.objects:
            try:
                temp_collection.objects.link(obj)
                linked_objects.append(obj)
            except Exception:
                pass

    export_blocks.add(temp_scene)
    export_blocks.add(temp_collection)

    try:
        bpy.data.libraries.write(filepath, export_blocks)
    finally:
        for obj in linked_objects:
            if temp_collection in obj.users_collection:
                temp_collection.objects.unlink(obj)
        if temp_scene.name in bpy.data.scenes:
            bpy.data.scenes.remove(temp_scene, do_unlink=True)
        if temp_collection.name in bpy.data.collections:
            bpy.data.collections.remove(temp_collection, do_unlink=True)
        restore_reserved_id_name(reserved_collection)
        restore_reserved_id_name(reserved_scene)


def _make_unique_temp_name(base_name: str) -> str:
    seed = (base_name or "TEMP").replace(".", "_")
    idx = 1
    candidate = f"__AE_TMP__{seed}"
    while bpy.data.objects.get(candidate):
        idx += 1
        candidate = f"__AE_TMP__{seed}_{idx:03d}"
    return candidate


def _make_unique_temp_name_for_id_collection(data_collection, base_name: str) -> str:
    seed = (base_name or "TEMP").replace(".", "_")
    idx = 1
    candidate = f"__AE_TMP__{seed}"
    while data_collection.get(candidate):
        idx += 1
        candidate = f"__AE_TMP__{seed}_{idx:03d}"
    return candidate


def reserve_id_name_for_export(data_collection, desired_name):
    if not desired_name:
        return None
    existing = data_collection.get(desired_name)
    if not existing:
        return None
    old_name = existing.name
    existing.name = _make_unique_temp_name_for_id_collection(data_collection, desired_name)
    return (existing, old_name)


def restore_reserved_id_name(reserved_pair):
    if not reserved_pair:
        return
    datablock, old_name = reserved_pair
    try:
        datablock.name = old_name
    except Exception:
        pass


def reserve_object_name_for_export(target_obj, desired_name):
    if not target_obj:
        return []

    desired_name = sanitize_export_basename(desired_name) or desired_name
    if not desired_name:
        return []

    renamed = []
    conflict_obj = bpy.data.objects.get(desired_name)
    if conflict_obj and conflict_obj != target_obj:
        old_conflict_name = conflict_obj.name
        conflict_obj.name = _make_unique_temp_name(desired_name)
        renamed.append((conflict_obj, old_conflict_name))

    old_target_name = target_obj.name
    target_obj.name = desired_name
    renamed.append((target_obj, old_target_name))
    return renamed


def restore_reserved_object_names(renamed_pairs):
    for obj, old_name in reversed(renamed_pairs or []):
        if obj and obj.name in bpy.data.objects:
            try:
                obj.name = old_name
            except Exception:
                pass


def apply_forward_arrow(context, direction):
    meshes = get_selected_meshes(context)
    if not meshes:
        return
        
    for obj in meshes:
        arrows_to_delete = [child for child in obj.children if child.name.startswith("HELPER_ForwardArrow_")]
        for arrow in arrows_to_delete:
            bpy.data.objects.remove(arrow, do_unlink=True)
            
        arrow_name = "HELPER_ForwardArrow_" + obj.name
        old_arrow = bpy.data.objects.get(arrow_name)
        if old_arrow:
            bpy.data.objects.remove(old_arrow, do_unlink=True)
            
        if direction == "NONE":
            if "asset_export_forward_dir" in obj:
                del obj["asset_export_forward_dir"]
            continue
            
        arrow = bpy.data.objects.new(arrow_name, None)
        arrow.empty_display_type = 'SINGLE_ARROW'
        
        dims = obj.dimensions
        max_dim = max(dims.x, dims.y, dims.z)
        arrow.empty_display_size = max_dim * 0.8 if max_dim > 0.001 else 1.0
        arrow.show_in_front = True
        
        dir_text = direction.replace("POS_", "+").replace("NEG_", "-")
        arrow["forward_dir"] = dir_text
        obj["asset_export_forward_dir"] = dir_text
        
        context.collection.objects.link(arrow)
        
        arrow.location = obj.matrix_world.translation
        
        eul = (0.0, 0.0, 0.0)
        if direction == "POS_X": eul = (0.0, math.radians(90.0), 0.0)
        elif direction == "NEG_X": eul = (0.0, math.radians(-90.0), 0.0)
        elif direction == "POS_Y": eul = (math.radians(-90.0), 0.0, 0.0)
        elif direction == "NEG_Y": eul = (math.radians(90.0), 0.0, 0.0)
        elif direction == "POS_Z": eul = (0.0, 0.0, 0.0)
        elif direction == "NEG_Z": eul = (math.radians(180.0), 0.0, 0.0)
        
        arrow.rotation_euler = eul


def _assets_check_v2_rows(scene):
    """读取资产审查助手 2.x（assets_check）写入的 results_json。"""
    props = getattr(scene, "assets_check_next_props", None)
    if props is None:
        return None
    raw = getattr(props, "results_json", "") or ""
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    return rows


def get_assets_check_v1_module():
    """旧版 assets_check_v1_cn（node_tree_002）可选兼容。"""
    for key in ("assets_check_v1_cn", "assets_check"):
        mod = sys.modules.get(key)
        if mod and hasattr(mod, "node_tree_002"):
            return mod
    try:
        for module in addon_utils.modules():
            info = getattr(module, "bl_info", {}) or {}
            bl_name = str(info.get("name", "")).lower()
            if "assets_check" in bl_name and hasattr(module, "node_tree_002"):
                return module
    except Exception:
        pass
    for mod_name, module in sys.modules.items():
        if hasattr(module, "node_tree_002") and "assets_check" in mod_name.lower():
            return module
    return None


def get_assets_check_status(context, selected_meshes=None):
    """
    判定是否可导出审查 CSV/JSON。
    优先使用重构版 assets_check（Scene.results_json）；否则回退旧版 v1_cn。
    """
    if selected_meshes is None:
        selected_meshes = get_selected_meshes(context)
    scene = context.scene
    selected_names = {obj.name for obj in selected_meshes}

    rows = _assets_check_v2_rows(scene)
    if rows is not None:
        if not selected_names:
            return {
                "all_selected_checked": False,
                "reason": "当前未选中网格",
                "backend": None,
                "module": None,
            }
        in_results = {str(r.get("object_name", "")) for r in rows if r.get("object_name")}
        if not selected_names.issubset(in_results):
            return {
                "all_selected_checked": False,
                "reason": "检查结果中未包含全部选中物体，请在顶栏「检查」中对本次导出对象执行检查",
                "backend": "v2",
                "module": None,
            }
        return {
            "all_selected_checked": True,
            "reason": "可联动导出审查 CSV/JSON（与审查助手报告格式一致）",
            "backend": "v2",
            "module": None,
        }

    if hasattr(bpy.types.Scene, "assets_check_next_props"):
        return {
            "all_selected_checked": False,
            "reason": "已启用资产审查助手，但尚无检查结果：请在顶栏「检查」中运行「开始检查」",
            "backend": "v2",
            "module": None,
        }

    module = get_assets_check_v1_module()
    if not module:
        return {
            "all_selected_checked": False,
            "reason": "未检测到资产审查插件（请安装并启用「资产审查助手」或旧版 v1）",
            "backend": None,
            "module": None,
        }
    node_data = getattr(module, "node_tree_002", {}) or {}
    data_list = node_data.get("sna_check_obj_data_lis", []) or []
    class_list = node_data.get("sna_check_class_list", []) or []
    if not data_list or not class_list:
        return {
            "all_selected_checked": False,
            "reason": "尚未执行资产审查（旧版）",
            "backend": "v1",
            "module": module,
        }
    checked_names = {str(row[0]) for row in data_list if row}
    all_checked = selected_names.issubset(checked_names) if selected_names else False
    if not all_checked:
        return {
            "all_selected_checked": False,
            "reason": "当前选中对象未全部完成资产审查（旧版）",
            "backend": "v1",
            "module": module,
        }
    return {
        "all_selected_checked": True,
        "reason": "可联动导出审查 CSV/JSON（旧版矩阵格式）",
        "backend": "v1",
        "module": module,
    }


def _write_assets_check_csv_v1_legacy(module, object_names, report_path):
    node_data = getattr(module, "node_tree_002", {}) or {}
    data_list = node_data.get("sna_check_obj_data_lis", []) or []
    class_list = node_data.get("sna_check_class_list", []) or []
    if not data_list or not class_list:
        raise RuntimeError("没有可用的资产审查结果，请先执行资产审查")
    selected_rows = [row for row in data_list if row and str(row[0]) in object_names]
    if not selected_rows:
        raise RuntimeError("未找到当前资产对应的审查结果，请先执行资产审查")

    checks = [c.replace("-", "") for c in class_list]
    transposed_rows = []

    row_model = ["模型名称"]
    for obj_data in selected_rows:
        row_model.append(str(obj_data[0]) if len(obj_data) > 0 else "")
    transposed_rows.append(row_model)

    row_info = ["基本信息"]
    for obj_data in selected_rows:
        row_info.append(str(obj_data[1]) if len(obj_data) > 1 else "")
    transposed_rows.append(row_info)

    for i, check_name in enumerate(checks):
        row_check = [check_name]
        data_index = i + 2
        for obj_data in selected_rows:
            val = obj_data[data_index] if data_index < len(obj_data) else None
            result_str = "Fail (警告/错误)" if isinstance(val, bool) and val else ("Pass (通过)" if isinstance(val, bool) else str(val))
            row_check.append(result_str)
        transposed_rows.append(row_check)

    with open(report_path, mode="w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(transposed_rows)


def _write_assets_check_json_v1_legacy(module, object_names, report_path):
    node_data = getattr(module, "node_tree_002", {}) or {}
    data_list = node_data.get("sna_check_obj_data_lis", []) or []
    class_list = node_data.get("sna_check_class_list", []) or []
    if not data_list or not class_list:
        raise RuntimeError("没有可用的资产审查结果，请先执行资产审查")
    selected_rows = [row for row in data_list if row and str(row[0]) in object_names]
    if not selected_rows:
        raise RuntimeError("未找到当前资产对应的审查结果，请先执行资产审查")

    checks = [c.replace("-", "") for c in class_list]
    objects_payload = []
    for obj_data in selected_rows:
        obj_name = str(obj_data[0]) if len(obj_data) > 0 else ""
        basic_info = str(obj_data[1]) if len(obj_data) > 1 else ""
        check_items = []
        for i, check_name in enumerate(checks):
            data_index = i + 2
            value = obj_data[data_index] if data_index < len(obj_data) else None
            status = "Fail (警告/错误)" if isinstance(value, bool) and value else ("Pass (通过)" if isinstance(value, bool) else str(value))
            check_items.append({"name": check_name, "raw_value": value, "status": status})
        objects_payload.append({"object_name": obj_name, "basic_info": basic_info, "checks": check_items})

    payload = {"check_headers": checks, "object_count": len(objects_payload), "objects": objects_payload}
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_assets_check_csv(context, object_names, report_path, check_status):
    """与资产审查助手「导出报告」CSV 列一致：Object, Check, Status, Message（v2）；旧版仍为转置矩阵。"""
    backend = check_status.get("backend")
    if backend == "v2":
        rows = _assets_check_v2_rows(context.scene)
        if not rows:
            raise RuntimeError("没有可用的资产审查结果，请先执行检查")
        names = set(object_names)
        filtered = [r for r in rows if r.get("object_name") in names]
        with open(report_path, mode="w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Object", "Check", "Status", "Message"])
            for r in filtered:
                writer.writerow([
                    r.get("object_name", ""),
                    r.get("check_id", ""),
                    r.get("status", ""),
                    r.get("message", ""),
                ])
        return
    if backend == "v1" and check_status.get("module"):
        _write_assets_check_csv_v1_legacy(check_status["module"], object_names, report_path)
        return
    raise RuntimeError("没有可用的资产审查数据源")


def write_assets_check_json(context, object_names, report_path, check_status):
    """v2 与审查助手一致：{\"rows\": [...] }；v1 为旧 objects 结构。"""
    backend = check_status.get("backend")
    if backend == "v2":
        rows = _assets_check_v2_rows(context.scene)
        if not rows:
            raise RuntimeError("没有可用的资产审查结果，请先执行检查")
        names = set(object_names)
        filtered = [r for r in rows if r.get("object_name") in names]
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({"rows": filtered}, f, ensure_ascii=False, indent=2)
        return
    if backend == "v1" and check_status.get("module"):
        _write_assets_check_json_v1_legacy(check_status["module"], object_names, report_path)
        return
    raise RuntimeError("没有可用的资产审查数据源")


def last_export_directory_is_valid(props) -> bool:
    """上次记录的导出父目录是否存在（用于 UI 灰显）。"""
    raw = getattr(props, "last_export_directory", "") or ""
    if not raw.strip():
        return False
    path = bpy.path.abspath(raw)
    return os.path.isdir(path)


def validate_export_request(context, props):
    meshes = get_selected_meshes(context)
    if not meshes:
        return False, "当前未选中可导出的网格对象（MESH）"
    has_any_output = any([
        props.export_fbx, props.export_glb, props.export_csv, props.export_basic_json,
        props.export_check_csv, props.export_check_json, props.export_blend, props.export_textures,
    ])
    if not has_any_output:
        return False, "请至少勾选一种导出内容（模型/报告/Blend/贴图）"
    if props.export_mode == "MERGED":
        base_name = sanitize_export_basename(props.export_base_name)
        if not base_name:
            return False, "合并导出请填写有效的资产主名称"
    return True, ""


def sanitize_optional_exports_by_availability(props, check_status, reporter=None):
    if (props.export_check_csv or props.export_check_json) and not check_status["all_selected_checked"]:
        if reporter:
            reporter.report({"WARNING"}, f"资产审查结果不可用，本次跳过审查 CSV/JSON：{check_status['reason']}")


def run_export_pipeline(context, base_dir, reporter):
    props = context.scene.asset_exporter_v2_props
    selected_meshes = get_selected_meshes(context)
    check_status = get_assets_check_status(context, selected_meshes)
    sanitize_optional_exports_by_availability(props, check_status, reporter)
    ok, err = validate_export_request(context, props)
    if not ok:
        reporter.report({"ERROR"}, err)
        return {"CANCELLED"}

    if props.export_mode == "MERGED":
        merge_name = sanitize_export_basename(props.export_base_name)
        if not merge_name:
            reporter.report({"ERROR"}, "合并导出请填写有效的资产主名称")
            return {"CANCELLED"}
        props.export_base_name = merge_name

    original_selected = context.selected_objects.copy()
    original_active = context.active_object

    def build_direct_texture_dir_name(asset_name: str) -> str:
        """
        直接导出模式贴图目录命名：
        - SM_KDJZ01 -> T_KDJZ01
        - 其他名称 -> T_<资产名>
        """
        clean = sanitize_export_basename(asset_name or "") or "Asset"
        if clean.upper().startswith("SM_"):
            core = clean[3:] or "Asset"
        else:
            core = clean
        return f"T_{core}"

    def build_unique_export_target(source_name):
        base_name = source_name.replace(".", "_")
        export_name = base_name
        packaged = (props.export_layout == "PACKAGED")
        idx = 1

        while True:
            model_dir = os.path.join(base_dir, export_name) if packaged else base_dir
            fbx_path = os.path.join(model_dir, f"{export_name}.fbx")
            glb_path = os.path.join(model_dir, f"{export_name}.glb")
            blend_path = os.path.join(model_dir, f"{export_name}.blend")
            report_path = os.path.join(model_dir, f"{export_name}_BasicInformation.csv")
            basic_json_path = os.path.join(model_dir, f"{export_name}_BasicInformation.json")
            check_report_path = os.path.join(model_dir, f"{export_name}_Check.csv")
            check_json_path = os.path.join(model_dir, f"{export_name}_Check.json")

            if packaged:
                conflict = os.path.isdir(model_dir)
            else:
                conflict = any(os.path.exists(p) for p in (
                    fbx_path, glb_path, blend_path, report_path, basic_json_path, check_report_path, check_json_path
                ))

            if not conflict:
                return export_name, model_dir, fbx_path, glb_path, blend_path, report_path, basic_json_path, check_report_path, check_json_path

            export_name = f"{base_name}_{idx:03d}"
            idx += 1

    def export_one_asset(source_objects, folder_base_name):
        folder_base_name = sanitize_export_basename(folder_base_name)
        if not folder_base_name:
            raise RuntimeError("资产主名称无效，请检查命名")

        export_model_name, model_dir, fbx_path, glb_path, blend_path, report_path, basic_json_path, check_report_path, check_json_path = build_unique_export_target(folder_base_name)
        tex_dir = (
            os.path.join(model_dir, "Texture")
            if props.export_layout == "PACKAGED"
            else os.path.join(model_dir, build_direct_texture_dir_name(export_model_name))
        )

        os.makedirs(model_dir, exist_ok=True)
        if props.export_textures:
            os.makedirs(tex_dir, exist_ok=True)

        bpy.ops.object.select_all(action="DESELECT")
        for obj in source_objects:
            obj.select_set(True)
        context.view_layer.objects.active = source_objects[0]
        
        main_source_obj = source_objects[0]
        source_collection_name = (
            main_source_obj.users_collection[0].name
            if getattr(main_source_obj, "users_collection", None) and len(main_source_obj.users_collection) > 0
            else "Collection"
        )
        forward_axis = main_source_obj.get("asset_export_forward_dir", "未定义")
        for child in main_source_obj.children:
            if child.name.startswith("HELPER_ForwardArrow_"):
                forward_axis = child.get("forward_dir", "未定义")
                break
                
        arrow_name = "HELPER_ForwardArrow_" + main_source_obj.name
        helper_arrow = bpy.data.objects.get(arrow_name)
        if helper_arrow:
            forward_axis = helper_arrow.get("forward_dir", "未定义")
                
        global_quat = main_source_obj.matrix_world.to_quaternion()
        global_quat_list = [round(global_quat.w, 6), round(global_quat.x, 6), round(global_quat.y, 6), round(global_quat.z, 6)]
        
        bpy.ops.object.duplicate()

        copied_objects = context.selected_objects.copy()
        if len(copied_objects) > 1:
            context.view_layer.objects.active = copied_objects[0]
            bpy.ops.object.join()

        temp_obj = context.active_object
        renamed_pairs = reserve_object_name_for_export(temp_obj, export_model_name)

        try:
            main_model_path = fbx_path if props.export_fbx else (glb_path if props.export_glb else "")
            if props.export_csv:
                write_basic_information_csv(temp_obj, report_path, main_model_path, props.export_textures, props.export_chinese_name, export_model_name, forward_axis, global_quat_list)
            if props.export_basic_json:
                write_basic_information_json(temp_obj, basic_json_path, main_model_path, props.export_textures, props.export_chinese_name, export_model_name, forward_axis, global_quat_list)
            # 资产审查联动：任何异常都不应阻止模型正常导出，只给出警告并跳过
            # v2 下即便“未完全覆盖选中对象”，也允许导出当前可匹配到的结果（含空结构文件）。
            can_try_export_check = check_status.get("backend") in {"v2", "v1"}
            if (props.export_check_csv or props.export_check_json) and can_try_export_check:
                try:
                    names = {obj.name for obj in source_objects}
                    if props.export_check_csv:
                        write_assets_check_csv(context, names, check_report_path, check_status)
                    if props.export_check_json:
                        write_assets_check_json(context, names, check_json_path, check_status)
                except Exception as e:
                    reporter.report({"WARNING"}, f"导出资产审查 CSV/JSON 失败，已跳过：{e}")

            # 先应用变换，保证导出的坐标/尺寸正确
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

            # 在导出副本上执行一次三角化，避免目标 DCC/引擎仍然保留 N 边面/四边面
            try:
                tri_mod = temp_obj.modifiers.new(name="__TEMP_TRIANGULATE__", type='TRIANGULATE')
                bpy.ops.object.modifier_apply(modifier=tri_mod.name)
            except Exception as e:
                print(f"[Asset Exporter] 三角化失败，已跳过：{e}")

            if props.export_textures:
                extracted_images = set()
                for slot in temp_obj.material_slots:
                    mat = slot.material
                    if mat and mat.use_nodes and mat.node_tree:
                        for node in mat.node_tree.nodes:
                            if node.type == "TEX_IMAGE" and node.image and node.image.name not in extracted_images:
                                copy_or_extract_image(node.image, tex_dir)
                                extracted_images.add(node.image.name)

            bpy.ops.object.select_all(action="DESELECT")
            temp_obj.select_set(True)
            context.view_layer.objects.active = temp_obj

            if props.export_fbx:
                fbx_kwargs = collect_fbx_kwargs()
                fbx_kwargs["filepath"] = fbx_path
                # 团队规范：统一从当前选中资产导出。
                fbx_kwargs["use_selection"] = True
                # 团队规范：仅导出网格，避免相机/灯光等混入。
                fbx_kwargs["object_types"] = {"MESH"}
                # 团队规范：FBX 仅导出纯模型，不写入贴图路径/嵌入贴图，后续由管线逻辑重链接。
                fbx_kwargs["path_mode"] = "STRIP"
                if "embed_textures" in fbx_kwargs:
                    fbx_kwargs["embed_textures"] = False
                # 关键：移除材质中的贴图节点，避免 FBX 记录贴图引用导致回导粉色。
                strip_texture_links_for_fbx_export(temp_obj)
                bpy.ops.export_scene.fbx(**fbx_kwargs)
            if props.export_glb:
                glb_kwargs = collect_glb_kwargs()
                glb_kwargs["filepath"] = glb_path
                # 团队规范：统一导出 GLB，且仅导出选中对象。
                glb_kwargs["export_format"] = "GLB"
                glb_kwargs["use_selection"] = True
                bpy.ops.export_scene.gltf(**glb_kwargs)

            if props.export_blend:
                export_selected_objects_to_blend(
                    blend_path,
                    [temp_obj],
                    scene_name=export_model_name,
                    collection_name=source_collection_name,
                )
        finally:
            restore_reserved_object_names(renamed_pairs)
            if temp_obj and temp_obj.name in bpy.data.objects:
                bpy.ops.object.select_all(action="DESELECT")
                temp_obj.select_set(True)
                context.view_layer.objects.active = temp_obj
                bpy.ops.object.delete()

        return {"name": export_model_name, "dir": model_dir}

    try:
        if props.export_mode == "MERGED":
            result = export_one_asset(selected_meshes, props.export_base_name)
            if props.export_layout == "PACKAGED":
                reporter.report({"INFO"}, f"资产导出成功：{result['dir']}")
            else:
                reporter.report({"INFO"}, f"资产导出成功：{base_dir}")
        else:
            for obj in selected_meshes:
                export_one_asset([obj], obj.name)
            reporter.report({"INFO"}, f"逐个导出完成：共 {len(selected_meshes)} 个资产")
        props.last_export_directory = os.path.normpath(bpy.path.abspath(base_dir))
        return {"FINISHED"}
    except Exception as e:
        reporter.report({"ERROR"}, f"导出失败：{e}")
        return {"CANCELLED"}
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in original_selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if original_active and original_active.name in bpy.data.objects:
            context.view_layer.objects.active = original_active
