# 运行文档（Windows / PySide6 / Docker）

如果你完全不懂 Python / 开发，也可以按本文一步一步跑起来。

本文档包含三种运行方式：

- Python 脚本直跑（最推荐先跑通）
- PySide6 可视化界面（桌面版）
- Docker API（服务化）

---

## 0. 你只需要准备这些（建议先看完）

- 一台 Windows 电脑（Windows 10/11 均可）
- 已安装 Python（建议 3.11 / 3.12；Python 3.14 也可以）
- 能联网（首次运行会自动下载模型和 ExifTool）
- 准备 1 张图片当“测试样例”（jpg/png/webp 等都行）

### 0.1 打开 PowerShell，并进入项目根目录

你需要在“项目根目录”（也就是包含 `scripts/`、`apps/`、`data/` 的那个文件夹）执行命令。

如果你不确定怎么进目录：

1. 打开文件资源管理器，进入项目文件夹 `MoeGirlTabProject`
2. 在空白处按住 `Shift` + 右键 → 选择“在此处打开 PowerShell 窗口”（或 Windows Terminal）
3. 你看到的命令行前缀应该类似：`PS D:\Project\python\MoeGirlTabProject>`

### 0.2 检查 Python 是否可用

在 PowerShell 里执行：

```powershell
python --version
```

如果提示“找不到 python”：

- 说明你还没装 Python，或安装时没加入 PATH
- 重新安装 Python 时勾选 **Add Python to PATH**，再重新打开 PowerShell

### 0.3 安装依赖（只需要做一次）

在项目根目录执行（复制粘贴即可）：

```powershell
python -X utf8 -m pip install --upgrade pip
python -X utf8 -m pip install requests beautifulsoup4 numpy onnxruntime Pillow
```

说明：

- 这里的“依赖”就是脚本运行需要的第三方组件
- 重复执行不会有问题（已安装的会跳过）

### 0.4 准备 `image/` 文件夹（放你的测试图片）

在项目根目录执行：

```powershell
New-Item -ItemType Directory -Force "image" | Out-Null
```

然后把任意 1 张图片复制到 `image\` 目录里。

---

## 1. 目录约定

- 图片目录：`image/`
- 高精度实验目录：`image_high_precision/`
- 标签队列输出：`data/annotation_queue/*.jsonl`
- 标签规则：`data/character_library/`
- 自动打标脚本：`scripts/auto_tag_images.py`

---

## 2. Python 直跑（最推荐：先跑通再说）

你只需要做到两件事：

1. `image/` 里至少放 1 张图片
2. 已完成“0.3 安装依赖”

### 2.1 运行命令（推荐：单行版，复制就能用）

在项目根目录执行：

```powershell
python -X utf8 "scripts/auto_tag_images.py" --image-dir "image" --queue-output "data/annotation_queue/pending_annotations_pyside.jsonl" --taxonomy "data/character_library/feature_taxonomy.json" --synonyms "data/character_library/feature_synonyms.json" --priority-rules "data/character_library/feature_priority_rules.json" --custom-character-dir "data/character_library/custom" --model-dir "tools/wd14" --exiftool-dir "tools/exiftool" --feature-threshold 0.62 --custom-character-threshold 0.55 --custom-character-margin 0.12 --copyright-threshold 0.70
```

（可选）多行版（更好读）：

```powershell
python -X utf8 "scripts/auto_tag_images.py" `
  --image-dir "image" `
  --queue-output "data/annotation_queue/pending_annotations_pyside.jsonl" `
  --taxonomy "data/character_library/feature_taxonomy.json" `
  --synonyms "data/character_library/feature_synonyms.json" `
  --priority-rules "data/character_library/feature_priority_rules.json" `
  --custom-character-dir "data/character_library/custom" `
  --model-dir "tools/wd14" `
  --exiftool-dir "tools/exiftool" `
  --feature-threshold 0.62 `
  --custom-character-threshold 0.55 `
  --custom-character-margin 0.12 `
  --copyright-threshold 0.70
```

注意：PowerShell 的反引号 **必须是行末最后一个字符**（后面不能有空格）。如果你复制多行版报错，改用上面的单行版。

### 2.2 运行成功会输出什么

运行成功会输出类似：

- `Images found`
- `Queue written`
- `Metadata targets`
- `Metadata updated`
- `Metadata skipped`

说明：

- 会生成队列文件：`data/annotation_queue/pending_annotations_pyside.jsonl`
- 会把中文关键词写入图片“元数据关键字”（不会改图片像素内容）
- 建议先用测试图片跑通再处理你的图片库

### 2.3 第一次运行可能会等比较久（正常）

首次运行会自动准备运行所需文件：

- 如果 `tools/wd14/` 缺少模型文件，会自动下载到该目录
- 如果 `tools/exiftool/` 缺少 ExifTool，会自动下载到该目录

---

## 3. PySide6 桌面版运行

PySide6 项目路径：

- `apps/pyside/`

### 3.1 安装流程（具体步骤）

在项目根目录执行：

```powershell
python -m pip install -r "requirements-gui.txt"
```

或者手动安装：

```powershell
python -m pip install pyside6 PySide6-Fluent-Widgets
```

注意：

- Python `3.14` 请优先使用 `requirements-gui.txt`，避免旧版 `PySide6` 版本不兼容。

### 3.2 运行 PySide6 项目

```powershell
python -X utf8 "apps/pyside/moegirl_tagger_gui.py"
```

启动后操作：

1. 点击“选择文件夹”或“选择图片（多选）”
2. （可选）切到“角色库”页面：
   - 在线搜索角色并录入/删除本地角色
   - 支持“按作品搜索（Fandom）”：
     - 输入作品名后自动发现 Fandom wiki 候选并弹窗选择
     - 选择后会拉取该作品的角色候选列表，支持 Windows 多选后批量录入
     - 该流程仅使用 Fandom 数据源，不回退 AniList
   - 或使用“批量补图（仅已有角色）”为已有角色自动追加参考图
   - 批量补图不会新增新角色，只会增强你已录入角色的识别参考
   - 补图候选来源：Bing（主）-> DuckDuckGo（次）-> Danbooru（兜底）
   - 补图身份筛选：使用 CLIP（ONNX）图像相似度，与 WD14 特征识别解耦
   - 补图会按“角色名 + 作品名”进行来源约束，避免同名角色串库
   - 低置信候选会被直接丢弃（宁可少补，不混图）
   - 批量补图前会先自动清理该角色已有参考图中的低置信混图
   - 每角色补图上限默认 `5`，最大 `10`
   - 本地角色库支持 Windows 风格多选：`Ctrl+A`、`Ctrl+左键`、`Shift+左键`
   - 批量删除在后台执行，不阻塞界面
   - 首次批量补图会弹出提醒：可能较慢，请勿关闭应用（首次可能下载 `tools/clip-vit-b32/vision_model.onnx`）
3. 点击“开始分析”
4. 右侧列表实时显示每张图的中文特征摘要（文件名下方）
5. 点击列表项，在左侧查看大图预览

说明：

- GUI 会调用 `scripts/auto_tag_images.py`
- 使用临时图片清单传给 `--input-list`
- 如果存在 `data/character_library/custom`，会自动启用自定义角色检索
- 批量构建状态保存在 `data/character_library/custom/build_state.json`
- 批量构建日志写入 `data/logs/character_build.log`
- 输出队列默认：`data/annotation_queue/pending_annotations_pyside.jsonl`
- 当前界面为无标题栏、无系统边框的自定义窗口
- 列表项固定高度约 `50px`，双行结构为“文件名 + 特征”

### 3.3 快速验收检查

执行以下命令确认环境：

```powershell
python --version
python -c "import PySide6; print(PySide6.__version__)"
```

验收标准：

- `python` 命令可用
- 可成功导入 `PySide6`
- 点击 GUI “开始分析”后，日志框可看到 `Images found` / `Metadata updated`

---

## 4. Docker API 运行

### 4.1 启动

在项目根目录执行：

```powershell
docker compose -f "docker/docker-compose.api.yml" up --build
```

### 4.2 健康检查

```powershell
curl "http://localhost:8000/health"
```

### 4.3 执行打标

```powershell
curl -X POST "http://localhost:8000/v1/tagging/run" `
  -H "Content-Type: application/json" `
  -d "{\"image_dir\":\"image\",\"feature_threshold\":0.68,\"copyright_threshold\":0.8}"
```

---

## 5. 运行方式差异

如果你只想先跑通一遍，按第 0 节做即可；这一节用于按运行方式列出额外前置条件，方便你之后切换到 GUI / Docker。

### 5.1 Python 脚本直跑

- Python 3.10+（推荐 3.11 / 3.12；Python 3.14 也可）
- 可用命令：`python`
- 已安装依赖（至少）：`requests`、`beautifulsoup4`、`numpy`、`onnxruntime`、`Pillow`

### 5.2 PySide6 桌面版

- Windows 11
- Python 3.10+（推荐 3.11+）
- 可用命令：`python`
- GUI 依赖：`PySide6`、`PySide6-Fluent-Widgets`

### 5.3 Docker API

- Docker Desktop（含 Compose）

---

## 6. 常见问题

### 6.1 `ModuleNotFoundError: numpy / onnxruntime / requests / PIL`

说明缺依赖。回到项目根目录执行：

```powershell
python -X utf8 -m pip install requests beautifulsoup4 numpy onnxruntime Pillow
```

### 6.2 `FileNotFoundError: Image directory not found: ...`

说明缺少 `image/` 文件夹或里面没有图片。执行：

```powershell
New-Item -ItemType Directory -Force "image" | Out-Null
```

然后把图片放到 `image\` 下，再重试第 2 节命令。

### 6.3 `ModuleNotFoundError: fastapi`

本机未安装 API 依赖。可用：

```powershell
python -m pip install -r "requirements-docker.txt"
```

或直接使用 Docker 运行 API（推荐）。

如果你使用的是 Python 3.14，且安装 `requirements-docker.txt` 报错：

- 这是因为某些依赖版本固定写死了，Python 版本太新时可能没有对应版本
- 解决方式：优先用 Docker 跑 API；或改用 Python 3.12

### 6.4 `ModuleNotFoundError: PySide6`

未安装 GUI 依赖。执行：

```powershell
python -m pip install -r "requirements-gui.txt"
```

### 6.5 图片未写入标签

优先检查：

- 队列中 `feature_tags` 是否为空
- 图片路径是否存在
- `tools/exiftool` 是否可用

---

## 7. 推荐工作流

1. 先用 Python 直跑验证规则
2. 再用 PySide6 GUI 做交互式批处理
3. 最后用 Docker API 做服务化部署

---

## 8. 官方参考

- Qt for Python（PySide6）入门：  
  https://doc.qt.io/qtforpython-6/gettingstarted.html
- PySide6-Fluent-Widgets（PyPI）：  
  https://pypi.org/project/PySide6-Fluent-Widgets/
