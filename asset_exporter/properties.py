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
        description="选择合并导出或逐个导出",
        items=[
            ("MERGED", "合并导出", "将选中模型合并后导出为一个资产包"),
            ("INDIVIDUAL", "逐个导出", "每个选中模型分别导出为独立资产包"),
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
        description="联动「资产审查助手」：与顶栏检查内导出报告相同列（Object, Check, Status, Message），需先对选中物体运行检查",
        default=True,
    )
    export_check_json: bpy.props.BoolProperty(
        name="导出资产审查 JSON",
        description="联动「资产审查助手」：与检查结果的 rows 结构一致，需先对选中物体运行检查",
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
        description="合并导出：文件夹与主文件名；逐个导出时以各物体名为准",
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
