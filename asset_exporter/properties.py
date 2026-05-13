import bpy

def update_forward_direction(self, context):
    from .utils import apply_forward_arrow
    apply_forward_arrow(context, self.forward_direction)


class ASSET_EXPORTER_V2_Properties(bpy.types.PropertyGroup):
    export_fbx: bpy.props.BoolProperty(
        name="导出 FBX",
        description="导出 FBX 格式模型文件",
        default=True,
    )
    export_glb: bpy.props.BoolProperty(
        name="导出 GLB",
        description="导出 GLB 格式模型文件",
        default=True,
    )
    forward_direction: bpy.props.EnumProperty(
        name="模型正前方向",
        description="选择当前模型的正前方向，将自动在模型原点生成箭头",
        items=[
            ("NONE", "无", "不定义正前方向，删除已有箭头"),
            ("POS_X", "+X", "正前方向为 +X 轴"),
            ("NEG_X", "-X", "正前方向为 -X 轴"),
            ("POS_Y", "+Y", "正前方向为 +Y 轴"),
            ("NEG_Y", "-Y", "正前方向为 -Y 轴"),
            ("POS_Z", "+Z", "正前方向为 +Z 轴"),
            ("NEG_Z", "-Z", "正前方向为 -Z 轴"),
        ],
        default="NONE",
        update=update_forward_direction
    )
    export_mode: bpy.props.EnumProperty(
        name="导出模式",
        description="合并：多选 → 一个 FBX/GLB 文件，文件内仍为多个独立物体；逐个：每个物体各一套与物体名同源的导出文件",
        items=[
            ("MERGED", "合并导出", "多选模型写入同一 .fbx/.glb，文件内保持多个独立物体与现有命名"),
            ("INDIVIDUAL", "逐个导出", "按当前每个物体各导出一套文件，主文件名与物体名一致（重名时自动加后缀）"),
        ],
        default="MERGED",
    )
    export_layout: bpy.props.EnumProperty(
        name="导出结构",
        description="选择是否创建外层资产文件夹",
        items=[
            ("PACKAGED", "打包导出", "每个资产创建独立外层文件夹（原有团队默认）"),
            ("DIRECT", "直接导出", "不创建外层文件夹，直接把文件导出到所选目录"),
        ],
        default="PACKAGED",
    )

    export_csv: bpy.props.BoolProperty(
        name="导出基础信息 CSV",
        description="导出基础信息检查报告 CSV",
        default=True,
    )
    export_basic_json: bpy.props.BoolProperty(
        name="导出基础信息 JSON",
        description="导出基础信息 JSON（便于开发读取）",
        default=True,
    )
    export_check_csv: bpy.props.BoolProperty(
        name="导出资产审查 CSV",
        description="联动「资产审查助手」：导出转置简洁表（模型名称/基本信息/各检查项），与旧版矩阵一致；需先对选中物体运行检查",
        default=True,
    )
    export_check_json: bpy.props.BoolProperty(
        name="导出资产审查 JSON",
        description="联动「资产审查助手」：与顶栏「导出报告」的 JSON 相同（含 export_columns 与 rows，字段含 display_value）",
        default=True,
    )
    export_blend: bpy.props.BoolProperty(
        name="备份 Blend 工程",
        description="导出完成后备份当前工程副本",
        default=True,
    )
    export_textures: bpy.props.BoolProperty(
        name="导出提取贴图",
        description="自动提取材质关联贴图到 Texture 目录内",
        default=True,
    )
    export_base_name: bpy.props.StringProperty(
        name="资产命名",
        description="主名称：合并导出时作为文件夹与 .fbx/.glb 主文件名；逐个导出时各文件仍取物体名，可点刷新将活动物体名填入此处作对照或切换模式后使用",
        default="",
    )
    export_chinese_name: bpy.props.StringProperty(
        name="资产中文名称（可选）",
        description="仅写入基础信息 CSV/JSON，不参与文件/目录命名",
        default="",
    )
    show_materials_info: bpy.props.BoolProperty(
        name="展开材质与贴图解析",
        description="显示或隐藏插槽材质及贴图详情",
        default=False,
    )
    last_export_directory: bpy.props.StringProperty(
        name="上次导出根目录",
        description="最近一次「选择目录并导出」所选父目录（用于快速在资源管理器中打开）",
        default="",
        subtype="DIR_PATH",
    )
