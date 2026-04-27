# Asset Exporter (Structured)

这是 `asset_exporter_v2.py` 的模块化拆分版本，功能保持一致，便于后续维护和多人协作。

## 目录结构

- `__init__.py`：插件入口、`bl_info`、注册与卸载
- `properties.py`：面板状态与导出选项属性
- `ui.py`：N 面板 UI 绘制
- `operators.py`：操作符（刷新命名、选择目录并导出）
- `utils.py`：导出核心流程、CSV/JSON 写出、贴图提取、审查联动

## 当前状态

- 行为目标：与单文件 `asset_exporter_v2.py` 对齐
- 使用方式：按 Blender 常规安装插件目录（包含 `__init__.py` 的文件夹）

## 备注

- 建议保留单文件版作为回退基线，结构版用于持续迭代。
