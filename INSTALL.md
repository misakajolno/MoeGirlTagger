# 安装说明（Windows / CLI / GUI / Docker）

## 1. 环境要求

- Python 3.11+（推荐）
- Windows PowerShell（GUI 推荐 Windows 10/11）
- Docker Desktop（仅 Docker API 模式需要）
- 可联网（首次运行会下载模型与工具）

## 2. 克隆与进入目录

```powershell
git clone <your-repo-url>
cd MoeGirlTabProject
```

## 3. Python 环境（推荐虚拟环境）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -X utf8 -m pip install --upgrade pip
```

## 4. 安装依赖

### 4.1 CLI 基础依赖

```powershell
python -X utf8 -m pip install requests beautifulsoup4 numpy onnxruntime Pillow
```

### 4.2 GUI 依赖

```powershell
python -m pip install -r requirements-gui.txt
```

### 4.3 API 依赖（本机直跑 FastAPI 时）

```powershell
python -m pip install -r requirements-docker.txt
```

## 5. 运行方式

### 5.1 CLI

```powershell
python -X utf8 scripts/auto_tag_images.py --image-dir image --queue-output data/annotation_queue/pending_annotations.jsonl
```

### 5.2 GUI

```powershell
python -X utf8 apps/pyside/moegirl_tagger_gui.py
```

### 5.3 Docker API

```powershell
docker compose -f docker/docker-compose.api.yml up --build
```

健康检查：

```powershell
curl http://localhost:8000/health
```

## 6. 首次运行说明

- 首次推理可能自动下载模型到 `tools/` 目录。
- 首次写入元数据可能自动下载 ExifTool。
- 上述行为为正常现象，耗时取决于网络环境。

## 7. 常见问题

- `ModuleNotFoundError`：按对应模式重新安装依赖。
- GUI 无法启动：确认 `PySide6` 已安装且 Python 版本兼容。
- Docker 启动失败：确认 Docker Desktop 已启动并启用 Compose。

更多运行细节可参考 `docs/RUNNING.md`。
