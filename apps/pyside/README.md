# 角色库（原神 / 绝区零）

- 生成时间: 2026-02-09 20:44:00
- 数据来源:
  - https://genshin-impact.fandom.com/wiki/Character/List
  - https://zenless-zone-zero.fandom.com/wiki/Agent/List
  - https://api.hakush.in/gi/data/character.json
  - https://api.hakush.in/zzz/data/character.json
- 文件说明:
  - genshin_impact_characters.csv: 原神可玩角色（按 Character/List 第一张表）
  - zenless_zone_zero_agents.csv: 绝区零可用 Agent（按 Agent/List 第一张表）
  - custom/characters.json: 本地自定义角色库（GUI 动态维护）
  - custom/references/<character_id>/*: 自定义角色参考图
  - custom/index.npz: 自定义角色检索索引
  - custom/index_meta.json: 检索索引元信息
  - custom/build_state.json: 批量构建状态快照（中断恢复提示）
  - feature_taxonomy.json: 角色特征标签库（分类、标签、互斥组）
  - feature_synonyms.json: 标签同义词映射（用于归一化）
  - sensitive_terms.json: 敏感词扩展库（独立维护，运行时自动合并）
  - feature_priority_rules.json: 特征优先级与冲突消解规则（用于自动打标）
- 备注: 仅包含当前可玩角色，不包含 Upcoming 列表。

## 特征库使用约定

- `feature_taxonomy.json`
  - `categories`: 按维度分组的 canonical 标签集合
  - `mutually_exclusive_groups`: 互斥标签组，归一化后建议只保留其中一个
  - 发色扩展: 已加入 `hair_coloring`（双色、阴阳染、渐变、挑染、内染、明暗色调）
  - 发型扩展: 已加入卷直发、双马尾长短、高低马尾、辫型、遮眼发型等
  - 已扩展分类: `face_details`、`footwear`、`species_traits`（含猫娘等）
  - 已精简分类: 已移除 `props_weapons`、`visual_effects`
- `feature_synonyms.json`
  - `canonical_to_aliases`: 别名（中文、英文、历史写法）映射到 canonical tag
  - `deprecated_tags`: 旧标签到新标签的一对一替换规则
- `sensitive_terms.json`
  - `taxonomy`: 敏感分类与标签扩展（会与 `feature_taxonomy.json` 合并）
  - `synonyms`: 敏感别名与旧标签映射扩展（会与 `feature_synonyms.json` 合并）
  - `priority_rules`: 敏感展示层级与风控规则扩展（会与 `feature_priority_rules.json` 合并）
- `feature_priority_rules.json`
  - `tag_priority_order`: 标签类别优先级（高到低）
  - `display_tag_priority`: 展示细粒度顺序（乳量/体型优先，18X分级靠后）
  - `adult_display_layer_order` + `adult_display_layers`: 18X 分层展示顺序（分级→暴露→裸露→器官→焦点→行为→道具）
  - `conflict_resolution.blocked_tags`: 黑名单强过滤（命中即剔除，优先级高于模型置信度）
  - `source_priority_order`: 标签来源优先级（人工 > 模板 > 模型）
  - `confidence_thresholds`: 自动接收/复核阈值
  - `conflict_resolution`: 互斥冲突处理与每类标签上限
  - `adult_content`: 已纳入增强版 18X 特征标签（分级 + 暴露部位 + 器官 + 性相关动作 + 道具 + 焦点）

## 推荐标注结构（示例）

```json
{
  "image_path": "images/zzz/00123.png",
  "characters": ["雅", "丽娜"],
  "feature_tags": ["blue_hair", "long_hair", "leg_ring", "ankle_socks", "catgirl"],
  "source_game": ["zenless_zone_zero"]
}
```

## 写回图片“标记”字段

- 使用脚本: `scripts/write_tags_to_image_metadata.py`
- 典型命令:
  - `python -X utf8 scripts/write_tags_to_image_metadata.py --queue data/annotation_queue/pending_annotations.jsonl --taxonomy data/character_library/feature_taxonomy.json --priority-rules data/character_library/feature_priority_rules.json --image-root . --status labeled_draft`
- 说明:
  - 将 `characters` + `feature_tags`（自动映射中文）+ `source_game` 写入图片元数据
  - 写入前自动执行精度控制：未知标签剔除、互斥组消解、每类标签数量上限
  - 展示顺序优化：同一图片中优先显示乳量/体型等常规体征，再显示 18X 相关标签
  - JPEG/TIFF 会同步写入 `XPKeywords`（资源管理器“标记”更易识别）
  - PNG 等格式写入 `XMP-dc:Subject`

## 自动识别并填充标签

- 一键脚本: `scripts/auto_tag_images.py`
- 功能:
  - 使用本地 WD14 模型自动识别图片标签
  - 自动归一化到 `feature_taxonomy.json` canonical 标签
  - 自动识别角色名（优先原神/绝区零角色库）
  - 支持自定义角色库检索（`data/character_library/custom`）
  - 自动将中文标签写回图片元数据“标记”
- 典型命令:
  - `python -X utf8 scripts/auto_tag_images.py --image-dir image --queue-output data/annotation_queue/pending_annotations.jsonl --feature-threshold 0.62 --adult-feature-threshold 0.55 --footwear-feature-threshold 0.50 --barefoot-feature-threshold 0.35 --custom-character-threshold 0.55 --custom-character-margin 0.12`
  - 说明: `adult_content` 与 `footwear` 分类会优先使用各自阈值，`barefoot` 还支持单独阈值；自定义角色检索会同时参考 `--custom-character-threshold`（最低命中）和 `--custom-character-margin`（与次高候选的差值保护）。

## 自定义角色库（动态增删）

- GUI 新增“角色库”页面，可在线搜索角色并录入到本地库。
- 支持“批量补图（仅已有角色）”：
  - 仅对本地已存在角色追加参考图，不会新增新角色
  - 候选来源顺序：Bing（主）-> DuckDuckGo（次）-> Danbooru（兜底）
  - 补图身份筛选：CLIP（ONNX）图像相似度，与 WD14 特征识别解耦
  - 补图时会按“角色名 + 作品名”做来源约束，避免同名异作品混入
  - 低置信候选会被直接丢弃（宁可少补，不混图）
  - 批量补图前会先自动清理该角色已有参考图中的低置信混图
  - 可配置“每角色补图上限”（默认 5，最大 10）
  - 首次批量补图会弹出明确提醒：可能耗时较长，请勿关闭应用（首次可能下载 `tools/clip-vit-b32/vision_model.onnx`）
  - 本地角色库支持 Windows 风格多选：`Ctrl+A` 全选，`Ctrl+左键` 增减选择，`Shift+左键` 区间选择
  - 批量删除在后台执行，避免卡住界面
  - 构建日志：`data/logs/character_build.log`
- 搜索源:
  - AniList（主）
  - Jikan / MyAnimeList（兜底）
- 每个角色可维护多张参考图，删除角色后索引会同步移除。
- 当前检索后端: `WD14 score vector + cosine similarity`

## 后续升级（方案 3）

- 现有角色存储和 GUI 管理流程保持不变。
- 检索向量可从 `WD14 score vector` 升级为 `CLIP embedding` 或专用角色模型。
- 升级仅替换检索后端与索引构建逻辑（`custom/index.npz` + `custom/index_meta.json` 版本化迁移）。
