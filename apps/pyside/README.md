# PySide 角色库管理说明

## 文档范围

- 本文只说明 `apps/pyside` GUI 中“角色库”和相关“设置”功能。
- 数据结构与标签库细节请参考 `data/character_library/README.md`。

## 本地数据布局

角色库相关数据位于 `data/character_library/custom`：

- `characters.json`：角色记录（名称、别名、作品、渠道映射、参考图列表等）
- `avatars/`：角色头像缓存
- `references/<source_key>/<character_id>/*`：角色参考图
- `build_state.json`：批量补图状态（用于中断恢复提示）
- `index.npz` / `index_meta.json`：自定义角色检索索引
- `correlation_profiles.json`：角色相关性缓存（可在设置页强制重建）

## 参考图目录归一化

参考图目录按“作品维度”组织：`references/<source_key>/<character_id>/`。

`source_key` 规则：

1. 先裁剪作品名后缀（如 ` - `、`|`、括号补充信息）。
2. 再做 slug 归一化。
3. 对常见作品做同义归并，跨语言/别名统一到同一目录（例如 `honkai_star_rail` 与“崩坏星穹铁道”归并）。

启动时会自动执行目录迁移：旧路径会移动到新结构，并清理空目录。

## 角色库页面行为

### 在线角色

- 输入角色名或作品名后点击 `在线角色`。
- 在线候选可录入本地角色库。
- 录入时会维护 `provider/provider_entity_id` 与 `provider_links`，用于去重和后续补图。

### 本地角色搜索（按钮触发）

- 在“搜索本地角色库”输入框输入关键字后，点击 `搜索本地角色`（或回车）。
- 搜索在后台线程执行，避免主线程卡顿。
- 匹配范围：
  - `display_name`
  - `source_title`
  - `aliases`
  - `source_aliases`
- 支持多语言文本归一化匹配。
- 非实时过滤：输入时不会立即刷新列表，只有触发搜索才会变更。
- 输入为空字符串时会清空过滤，显示全部角色。

### 列表操作

- 操作区按钮顺序：`录入所选角色`、`刷新列表` 在左；`补充参考图`、`删除所选角色` 固定在最右。
- 本地列表支持多选（`Ctrl` / `Shift` / `Ctrl+A`）。
- 批量删除在后台线程执行。

## 批量补图（仅已有角色）

- 只会为“已存在”角色补参考图，不会新增角色。
- 每个角色先计算剩余可补数量：
  - `remaining = per_character_limit - current_reference_count`
  - `remaining <= 0` 直接跳过
- 在线抓图与身份过滤都使用 `remaining` 作为上限，避免无效下载和超量补图。
- 补图前会先清理该角色已存在参考图中的明显混图（身份过滤）。
- 进度、失败和中断信息写入：`data/logs/character_build.log`。

## 设置页：强制重建相关性缓存

- 按钮位置：阈值配置“保存修改”下方。
- 功能：强制重建 `correlation_profiles.json`。
- 影响范围：仅影响自定义角色识别，不影响标签识别。
- 当参考图或特征规则变更后，建议手动执行一次重建。

## 维护建议

- 本地搜索命中异常时，优先检查 `characters.json` 中的 `aliases/source_aliases` 是否完整。
- 角色补图精度下降时，先补充高质量参考图，再执行一次“强制重建角色相关性缓存”。
