# 架构方案（PySide6 + Docker 互不影响）

## 目标

在同一仓库内同时支持：

- Win11 桌面可视化（PySide6 + Fluent 风格）
- Docker API 服务（批处理/远程调用）

且二者共享同一套打标能力与规则文件，不重复维护逻辑。

## 分层结构

- `core/`：跨运行时公共能力（命令封装、后续可演进为纯 Python Pipeline SDK）
- `apps/api/`：Docker 运行的 FastAPI 服务
- `apps/pyside/`：Win11 桌面可视化入口（PySide6）
- `scripts/`：CLI 执行入口（本地/调试/手工批处理）
- `data/character_library/`：特征库与优先级规则（SSOT）

## 当前最小骨架

- `core.moegirl_tagger.runner`
  - `AutoTagOptions`
  - `run_auto_tag_pipeline`
  - `parse_pipeline_summary`
- `apps.api.main`
  - `GET /health`
  - `POST /v1/tagging/run`
- `apps/pyside/moegirl_tagger_gui.py`（入口脚本）
  - 创建 `QApplication` 并显示主窗口
- `apps/pyside/moegirl_tagger_gui_window.py`（主窗口）
  - 无标题栏/无系统边框的自定义窗口
  - 左侧大图预览 + 右侧 50px 双行任务列表（文件名 + 特征）
  - “开始分析”按钮联动 Python 打标脚本并回填中文标签摘要
  - 其余职责拆分到同目录下的 `moegirl_tagger_gui_*.py` 模块（model/list/widgets/worker/common）

## 演进路线

1. 将 `scripts/auto_tag_images.py` 逐步下沉到 `core/`，脚本仅保留参数解析。
2. PySide6 端直接调用 `core`（或调用 API）实现统一行为。
3. 增加作业队列与异步任务管理（Celery/Redis 或本地队列）。
4. 增加结果审计与版本化（按 run_id 保存执行摘要）。
