# MoeGirlTagProject

动漫图片自动打标与角色识别项目，提供三种使用方式：

- 命令行批处理（CLI）
- PySide6 桌面 GUI
- FastAPI + Docker API

## 项目说明

本项目围绕 `scripts/auto_tag_images.py` 与 `core/` 能力层构建，目标是把图片中的角色、特征与标签自动识别并写回元数据。
- PS1: 目前角色识别能力比较差，还没有想到什么合理的办法，毕竟角色太多了，我是按照上千个角色的特征来设计的，如果两个角色相接近，很容易识别错误，虽然两个角色不接近也容易识别错误。
- PS2: AI参与度1000%，代码没看一眼，辣眼睛请见谅。

核心能力：

- WD14 本地推理自动标签识别
- 标签归一化与优先级/冲突处理
- 本地自定义角色库
- 角色库批量补图
- 本地角色库后台搜索

## 目录结构

- `apps/pyside/`：桌面 GUI 入口与界面逻辑
- `apps/api/`：FastAPI 服务入口
- `core/`：公共核心能力（pipeline、检索与存储）
- `scripts/`：命令行脚本
- `data/character_library/`：标签库与角色库数据
- `tests/`：单元测试

## 快速开始

详细安装见 [INSTALL.md](./INSTALL.md)。

常用启动命令：

```powershell
# CLI
python -X utf8 scripts/auto_tag_images.py --image-dir image

# GUI
python -X utf8 apps/pyside/moegirl_tagger_gui.py

# Docker API
docker compose -f docker/docker-compose.api.yml up --build
```

## 相关文档

- 运行说明：`docs/RUNNING.md`
- 架构说明：`docs/ARCHITECTURE.md`
- PySide 角色库说明：`apps/pyside/README.md`
- 角色/标签数据说明：`data/character_library/README.md`
- 开源与合规说明：[OPEN_SOURCE.md](./OPEN_SOURCE.md)
- 第三方声明：`THIRD_PARTY_NOTICES.md`

## 测试

```powershell
python -m unittest
```

## 开源说明

请先阅读 [OPEN_SOURCE.md](./OPEN_SOURCE.md) 和 `THIRD_PARTY_NOTICES.md`，再进行公开发布或二次分发。
