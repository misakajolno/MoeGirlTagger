"""Shared constants and utility helpers for MoeGirlTagger GUI."""

from __future__ import annotations

import json
import re
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QIcon

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
DEFAULT_FEATURE_TEXT = "编辑标签"
ROW_MARGIN_X = 4
ROW_MARGIN_Y = 3
DELETE_BUTTON_SIZE = 24
DELETE_BUTTON_MARGIN = 10
TAG_EDIT_BUTTON_SIZE = 24
TAG_EDIT_BUTTON_MARGIN = 10
SHOW_DELETE_HITBOX = False
LAST_OPEN_DIR_SETTING_KEY = "ui/last_open_dir"
LANGUAGE_SETTING_KEY = "ui/language"
CHARACTER_RECOGNITION_SETTING_KEY = "analysis/recognize_characters"
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "app_icon.ico"
SPIN_UP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "spin_up.svg"
SPIN_DOWN_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "spin_down.svg"
WINDOW_CLOSE_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "window_close.svg"
LIST_DELETE_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "list_delete.svg"
TAG_EDITOR_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icons" / "tags.svg"
FEATURE_PREVIEW_LIMIT = 8
FEATURE_FORCE_VISIBLE = ("barefoot",)
THRESHOLD_MIN_VALUE = 0.0
THRESHOLD_MAX_VALUE = 1.0
DEFAULT_RECOGNIZE_CHARACTERS = True
DEFAULT_LANGUAGE = "zh-CN"
LANGUAGE_OPTIONS = (
    ("zh-CN", "中文"),
    ("en-US", "English"),
    ("ja-JP", "日本語"),
    ("ko-KR", "한국어"),
)
DEFAULT_THRESHOLDS = {
    "feature_threshold": 0.62,
    "adult_feature_threshold": 0.55,
    "footwear_feature_threshold": 0.50,
    "barefoot_feature_threshold": 0.35,
    "custom_character_threshold": 0.55,
    "custom_character_margin": 0.12,
    "copyright_threshold": 0.70,
}
THRESHOLD_CLI_ARGS = {
    "feature_threshold": "--feature-threshold",
    "adult_feature_threshold": "--adult-feature-threshold",
    "footwear_feature_threshold": "--footwear-feature-threshold",
    "barefoot_feature_threshold": "--barefoot-feature-threshold",
    "custom_character_threshold": "--custom-character-threshold",
    "custom_character_margin": "--custom-character-margin",
    "copyright_threshold": "--copyright-threshold",
}
THRESHOLD_SETTING_KEYS = {key: f"analysis/{key}" for key in DEFAULT_THRESHOLDS}
THRESHOLD_LABEL_KEYS = {
    "feature_threshold": "threshold_feature",
    "adult_feature_threshold": "threshold_adult_feature",
    "footwear_feature_threshold": "threshold_footwear_feature",
    "barefoot_feature_threshold": "threshold_barefoot_feature",
    "custom_character_threshold": "threshold_custom_character",
    "custom_character_margin": "threshold_custom_character_margin",
    "copyright_threshold": "threshold_copyright",
}
TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "menu_analysis": "分析",
        "menu_characters": "角色库",
        "menu_settings": "设置",
        "btn_choose_folder": "选择文件夹",
        "btn_choose_images": "选择图片（多选）",
        "btn_remove_all": "删除全部",
        "btn_edit_tags": "编辑标签",
        "btn_clear_tags": "清除标签",
        "btn_remove_tagged": "删除包含标签",
        "btn_start_analysis": "开始分析",
        "btn_stop_analysis": "停止分析",
        "selected_count": "已选择：{count} 张",
        "preview_placeholder": "左侧预览区\n选择列表中的图片后显示",
        "status_waiting_select": "状态：等待选择图片",
        "status_busy_modify_list": "分析中无法修改列表。",
        "status_clearing_tags_busy": "正在清除标签，请稍后再开始分析。",
        "status_clearing_tags": "状态：正在清除标签（{count} 张）...",
        "status_no_tagged_images": "状态：列表中没有已有标签的图片",
        "status_tags_cleared": "状态：已清除 {count} 张图片的标签",
        "status_pending_analysis": "待分析",
        "status_clear_tags_failed": "清除标签失败：{error}",
        "status_exiftool_missing": "未找到 ExifTool，无法清除标签。",
        "dialog_clear_tags_title": "清除标签",
        "dialog_clear_tags_message": "将清除 {count} 张图片的已有标签，仅移除标签字段，不影响其他信息。是否继续？",
        "dialog_clear_tags_confirm": "确认清除",
        "dialog_clear_tags_cancel": "取消",
        "status_preview_failed": "预览失败：{name}",
        "status_please_select_images": "请先选择图片。",
        "status_stopping_analysis": "正在停止分析…",
        "status_analysis_started": "开始分析：{count} 张",
        "status_analysis_completed": "分析完成",
        "status_selected_images": "已选择图片：{count} 张",
        "status_loaded_folder": "已加载文件夹：{folder}（{count} 张）",
        "dialog_choose_folder": "选择图片文件夹",
        "dialog_choose_images": "选择图片（可多选）",
        "dialog_image_files_filter": "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff)",
        "status_prefix": "状态",
        "status_analysis_in_progress": "分析中...",
        "status_analysis_stopped": "已停止分析",
        "status_exec_failed": "执行失败",
        "status_no_obvious_features": "未识别到明显特征",
        "section_character": "角色：",
        "section_feature": "特征：",
        "section_tags": "标签：",
        "character_page_title": "角色库管理",
        "character_search_placeholder": "输入角色名或作品名后在线搜索",
        "character_search_button": "在线角色",
        "character_library_search_placeholder": "搜索本地角色库（角色/作品，支持多语言）",
        "character_library_search_button": "搜索本地角色",
        "character_work_search_button": "按作品搜索（Fandom）",
        "character_bulk_count_label": "每角色补图上限",
        "character_bulk_build_button": "批量补图（仅已有角色）",
        "character_import_button": "录入所选角色",
        "character_delete_button": "删除所选角色",
        "character_add_refs_button": "补充参考图",
        "character_refresh_button": "刷新列表",
        "character_search_results_title": "在线候选结果",
        "character_library_title": "本地角色库",
        "character_library_list_disabled_suffix": "（已禁用）",
        "character_library_list_refs_label": "参考图：",
        "status_character_search_empty_keyword": "请输入角色名称后再搜索。",
        "status_character_searching": "正在搜索角色，请稍候...",
        "status_character_search_done": "角色搜索完成：{count} 条候选",
        "status_character_search_failed": "角色搜索失败：{error}",
        "status_character_library_searching": "正在搜索本地角色库，请稍候...",
        "status_character_library_search_running": "本地角色库搜索进行中，请稍候。",
        "status_character_library_search_done": "本地角色库搜索完成：{count} 条。",
        "status_character_library_search_failed": "本地角色库搜索失败：{error}",
        "status_character_work_searching": "正在检索 Fandom 作品，请稍候...",
        "status_character_work_search_done": "作品候选已获取：{count} 条，请选择正确作品。",
        "status_character_work_no_result": "未找到可用的 Fandom 作品候选，请尝试更具体的作品名。",
        "status_character_work_search_failed": "作品检索失败：{error}",
        "status_character_work_pick_cancelled": "已取消作品选择。",
        "status_character_work_fetching": "正在拉取作品角色候选：{title}（{domain}）...",
        "status_character_work_fetch_done": "作品角色候选已加载：{title}，共 {count} 条。",
        "status_character_work_fetch_failed": "拉取作品角色失败：{error}",
        "status_character_bulk_recovered": "检测到上次批量补图未正常结束，已标记为中断。",
        "status_character_bulk_running": "角色库批量补图进行中，请稍候。",
        "status_character_bulk_no_existing": "本地角色库为空，请先添加角色后再批量补图。",
        "status_character_bulk_start": "开始批量补图：共 {count} 个已有角色（每角色上限 {limit} 张），请勿关闭应用。",
        "status_character_bulk_progress_waiting": "正在拉取候选角色...",
        "status_character_bulk_progress": "批量补图中：{processed}/{total}（已更新 {updated} 角，新增参考图 {added}，跳过 {skipped}）当前：{name}",
        "status_character_bulk_done": "批量补图完成：更新角色 {updated}，新增参考图 {added}，跳过 {skipped}，失败 {failed}",
        "status_character_bulk_failed": "批量补图失败：{error}",
        "status_character_bulk_interrupted": "批量补图已中断。",
        "status_character_bulk_cancelled": "已取消批量补图。",
        "status_character_import_no_selection": "请先选择在线候选角色。",
        "status_character_import_success": "角色已录入：{name}",
        "status_character_import_failed": "录入角色失败：{error}",
        "status_character_import_batch_result": "角色录入完成：成功 {success}，失败 {failed}",
        "status_character_import_batch_result_with_skipped": "角色录入完成：成功 {success}，失败 {failed}，取消 {skipped}",
        "status_character_import_cancelled_all": "已取消本次角色录入。",
        "dialog_character_merge_confirm_title": "检测到疑似同一角色",
        "dialog_character_merge_confirm_text": "检测到候选角色与已有角色可能是同一人，请选择处理方式。",
        "dialog_character_merge_confirm_details": "已有渠道映射：{links}",
        "dialog_character_merge_confirm_merge": "合并到已有角色",
        "dialog_character_merge_confirm_new": "添加为新角色",
        "dialog_character_merge_confirm_cancel": "取消",
        "dialog_character_merge_candidate_title": "候选角色",
        "dialog_character_merge_existing_title": "已有角色",
        "dialog_character_merge_source_line": "作品：{source}",
        "dialog_character_merge_links_line": "渠道：{links}",
        "status_character_delete_no_selection": "请先在本地角色库中选择角色。",
        "status_character_delete_busy": "角色删除进行中，请稍候。",
        "status_character_delete_background_start": "正在后台删除角色（{count} 个）...",
        "status_character_delete_progress": "后台删除中：{processed}/{total}，当前：{name}",
        "status_character_delete_batch_done": "角色删除完成：成功 {deleted}，不存在 {missing}，失败 {failed}",
        "status_character_delete_interrupted": "角色删除已中断。",
        "status_character_delete_success": "角色已删除：{name}",
        "status_character_delete_failed": "删除角色失败：{error}",
        "dialog_character_delete_confirm_title": "删除角色确认",
        "dialog_character_delete_confirm_message": "将从本地角色库删除所选 {count} 个角色及其参考图，此操作不可撤销。是否继续？",
        "dialog_character_delete_confirm_confirm": "确认删除",
        "dialog_character_delete_confirm_cancel": "取消",
        "status_character_refs_no_selection": "请先选择本地角色后再补充参考图。",
        "status_character_refs_multi_selection": "补充参考图仅支持单角色，请只选择一个角色。",
        "status_character_refs_added": "已为 {name} 增加 {count} 张参考图。",
        "status_character_refs_failed": "补充参考图失败：{error}",
        "dialog_character_bulk_first_title": "首次批量补图提醒",
        "dialog_character_bulk_first_message": "将仅为已存在角色在线补充参考图，不会新增角色。首次批量补图可能较慢（每角色上限 {count} 张），请勿关闭应用。是否继续？",
        "dialog_character_bulk_first_confirm": "继续补图",
        "dialog_character_bulk_first_cancel": "取消",
        "dialog_character_bulk_interrupt_title": "中断批量补图",
        "dialog_character_bulk_interrupt_message": "角色库仍在批量补图中，关闭窗口会中断任务。确定要退出吗？",
        "dialog_character_bulk_interrupt_confirm": "中断并退出",
        "dialog_character_bulk_interrupt_cancel": "继续等待",
        "dialog_character_delete_interrupt_title": "中断角色删除",
        "dialog_character_delete_interrupt_message": "角色仍在后台删除中，关闭窗口会中断任务。确定要退出吗？",
        "dialog_character_delete_interrupt_confirm": "中断并退出",
        "dialog_character_delete_interrupt_cancel": "继续等待",
        "dialog_character_work_pick_title": "选择作品",
        "dialog_character_work_pick_label": "请选择正确的 Fandom 作品：",
        "settings_title": "设置",
        "settings_subtitle": "非必要不要修改，避免影响分析稳定性。",
        "settings_range_hint": "阈值可调范围：最小值 {min}，最大值 {max}。",
        "settings_diff_hint": "最小值更宽松（更容易命中），最大值更严格（更不容易命中）。",
        "settings_language_title": "语言切换",
        "settings_character_recognition_label": "是否识别角色",
        "settings_threshold_title": "阈值配置",
        "settings_threshold_helper": "所有阈值保存后会用于下一次分析。",
        "settings_threshold_notes": "备注：\n自定义角色阈值：自定义角色库最低相似度。\n自定义角色区分边距：第一候选与第二候选的最小差值，越大越不易混图。\n作品阈值：作品（版权）标签最低命中分。",
        "settings_reset": "重置默认值",
        "settings_save": "保存修改",
        "settings_rebuild_correlation_profiles": "强制重建角色相关性缓存",
        "settings_rebuild_correlation_profiles_hint": "当角色库参考图或特征规则更新后，点击此按钮可强制重建 correlation_profiles.json（仅影响自定义角色识别，不影响标签识别）。",
        "settings_project_github": "项目 GitHub",
        "settings_version_text": "版本 v{version}",
        "settings_saved_toast": "保存成功",
        "settings_saved_status": "设置已保存，下次分析生效。",
        "settings_rebuild_correlation_profiles_done_toast": "重建完成",
        "settings_rebuild_correlation_profiles_failed_toast": "重建失败",
        "status_open_project_github_failed": "无法打开项目 GitHub 链接。",
        "status_rebuild_correlation_profiles_start": "开始强制重建自定义角色相关性缓存，请稍候...",
        "status_rebuild_correlation_profiles_running": "角色相关性缓存正在重建中，请稍候。",
        "status_rebuild_correlation_profiles_done": "强制重建完成：已生成 {count} 个角色相关性档案。",
        "status_rebuild_correlation_profiles_empty": "重建完成：当前没有可用的自定义角色参考数据。",
        "status_rebuild_correlation_profiles_failed": "强制重建失败：{error}",
        "threshold_feature": "特征阈值",
        "threshold_adult_feature": "成人特征阈值",
        "threshold_footwear_feature": "鞋类特征阈值",
        "threshold_barefoot_feature": "裸足特征阈值",
        "threshold_custom_character": "自定义角色阈值",
        "threshold_custom_character_margin": "自定义角色区分边距",
        "threshold_copyright": "作品阈值",
        "settings_spin_hint": "最小值 {min} / 最大值 {max}",
        "feature_edit_tags": "编辑标签",
        "btn_tag_editor_tooltip": "编辑当前图片标签",
        "tag_editor_dialog_title": "标签编辑",
        "tag_editor_left_title": "特征与角色",
        "tag_editor_right_title": "已选择标签",
        "tag_editor_feature_group_prefix": "特征 / ",
        "tag_editor_character_group_prefix": "角色 / ",
        "tag_editor_rules": "规则：双击或拖拽可在左右区域移动标签；左侧灰色项表示已选择，可在右侧双击或拖回左侧移除。",
        "tag_editor_apply": "应用",
        "tag_editor_cancel": "取消",
        "status_tag_editor_no_selection": "请先在列表中选择一张图片后再编辑标签。",
        "status_tag_editor_saved": "标签已更新（共 {count} 项）。",
        "status_tag_editor_multi_required": "请先在列表中多选至少两张图片后再编辑标签。",
        "status_tag_editor_batch_no_changes": "未选择要追加的标签，未执行批量编辑。",
        "status_tag_editor_batch_saved": "已为 {count} 张图片追加标签（新增特征 {feature_count}，新增角色 {character_count}）。",
        "worker_log_running_command": "运行命令：{command}",
        "worker_status_script_failed": "脚本执行失败（退出码 {code}）",
        "worker_status_exception": "执行异常：{error}",
        "status_unknown_error": "未知错误",
    },
    "en-US": {
        "menu_analysis": "Analysis",
        "menu_characters": "Character Library",
        "menu_settings": "Settings",
        "btn_choose_folder": "Select Folder",
        "btn_choose_images": "Select Images",
        "btn_remove_all": "Remove All",
        "btn_edit_tags": "Edit Tags",
        "btn_clear_tags": "Clear Tags",
        "btn_remove_tagged": "Remove Tagged",
        "btn_start_analysis": "Start Analysis",
        "btn_stop_analysis": "Stop Analysis",
        "selected_count": "Selected: {count}",
        "preview_placeholder": "Preview area\nSelect an image from the list",
        "status_waiting_select": "Status: Waiting for image selection",
        "status_busy_modify_list": "Cannot modify the list during analysis.",
        "status_clearing_tags_busy": "Clearing tags in progress. Please wait before starting analysis.",
        "status_clearing_tags": "Status: Clearing tags ({count})...",
        "status_no_tagged_images": "Status: No images with existing tags in the list",
        "status_tags_cleared": "Status: Cleared tags for {count} images",
        "status_pending_analysis": "Pending analysis",
        "status_clear_tags_failed": "Failed to clear tags: {error}",
        "status_exiftool_missing": "ExifTool not found. Cannot clear tags.",
        "dialog_clear_tags_title": "Clear Tags",
        "dialog_clear_tags_message": "This will clear existing tags for {count} images and keep other metadata unchanged. Continue?",
        "dialog_clear_tags_confirm": "Clear Tags",
        "dialog_clear_tags_cancel": "Cancel",
        "status_preview_failed": "Preview failed: {name}",
        "status_please_select_images": "Please select images first.",
        "status_stopping_analysis": "Stopping analysis...",
        "status_analysis_started": "Analysis started: {count}",
        "status_analysis_completed": "Analysis completed",
        "status_selected_images": "Selected images: {count}",
        "status_loaded_folder": "Loaded folder: {folder} ({count})",
        "dialog_choose_folder": "Select image folder",
        "dialog_choose_images": "Select images (multiple)",
        "dialog_image_files_filter": "Image Files (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff)",
        "status_prefix": "Status",
        "status_analysis_in_progress": "Analyzing...",
        "status_analysis_stopped": "Analysis stopped",
        "status_exec_failed": "Execution failed",
        "status_no_obvious_features": "No obvious features detected",
        "section_character": "Character: ",
        "section_feature": "Features: ",
        "section_tags": "Tags: ",
        "character_page_title": "Character Library",
        "character_search_placeholder": "Search online by character or work name",
        "character_search_button": "Online Characters",
        "character_library_search_placeholder": "Search local library (character/work, multilingual)",
        "character_library_search_button": "Search Local Library",
        "character_import_button": "Import Selected",
        "character_delete_button": "Delete Selected",
        "character_add_refs_button": "Append References",
        "character_refresh_button": "Refresh List",
        "character_search_results_title": "Online Candidates",
        "character_library_title": "Local Library",
        "character_library_list_disabled_suffix": "(disabled)",
        "character_library_list_refs_label": "refs:",
        "character_work_search_button": "Search Work (Fandom)",
        "status_character_search_empty_keyword": "Please enter a character name before searching.",
        "status_character_searching": "Searching characters, please wait...",
        "status_character_search_done": "Character search completed: {count} candidates",
        "status_character_search_failed": "Character search failed: {error}",
        "status_character_library_searching": "Searching local library, please wait...",
        "status_character_library_search_running": "Local library search is already running.",
        "status_character_library_search_done": "Local library search completed: {count} items.",
        "status_character_library_search_failed": "Local library search failed: {error}",
        "status_character_work_searching": "Searching Fandom works...",
        "status_character_work_search_done": "Found {count} work candidates. Please choose one.",
        "status_character_work_no_result": "No Fandom work candidates found.",
        "status_character_work_search_failed": "Work search failed: {error}",
        "status_character_work_pick_cancelled": "Work selection cancelled.",
        "status_character_work_fetching": "Loading characters for {title} ({domain})...",
        "status_character_work_fetch_done": "Loaded {count} character candidates from {title}.",
        "status_character_work_fetch_failed": "Failed to load work characters: {error}",
        "status_character_import_batch_result": "Character import completed: success {success}, failed {failed}",
        "status_character_import_batch_result_with_skipped": "Character import completed: success {success}, failed {failed}, skipped {skipped}",
        "status_character_import_cancelled_all": "Character import cancelled.",
        "status_character_import_no_selection": "Please select online candidates first.",
        "status_character_import_success": "Character imported: {name}",
        "status_character_import_failed": "Character import failed: {error}",
        "dialog_character_merge_confirm_title": "Possible duplicate character",
        "dialog_character_merge_confirm_text": "The incoming character may be the same as an existing one. Choose how to handle it.",
        "dialog_character_merge_confirm_details": "Existing provider links: {links}",
        "dialog_character_merge_confirm_merge": "Merge",
        "dialog_character_merge_confirm_new": "Add as New",
        "dialog_character_merge_confirm_cancel": "Cancel",
        "dialog_character_merge_candidate_title": "Incoming Candidate",
        "dialog_character_merge_existing_title": "Existing Character",
        "dialog_character_merge_source_line": "Source: {source}",
        "dialog_character_merge_links_line": "Providers: {links}",
        "dialog_character_work_pick_title": "Pick Work",
        "dialog_character_work_pick_label": "Choose the correct Fandom work:",
        "character_bulk_count_label": "Per-Character Refs",
        "character_bulk_build_button": "Bulk Add Refs (Existing Only)",
        "status_character_bulk_recovered": "Detected an unfinished previous bulk reference run and marked it interrupted.",
        "status_character_bulk_running": "Bulk reference append is still running.",
        "status_character_bulk_no_existing": "Character library is empty. Add characters first.",
        "status_character_bulk_start": "Bulk reference append started: {count} existing characters (limit {limit} each). Keep the app open.",
        "status_character_bulk_progress_waiting": "Loading candidate characters...",
        "status_character_bulk_progress": "Appending refs: {processed}/{total} (updated {updated}, added refs {added}, skipped {skipped}) current: {name}",
        "status_character_bulk_done": "Bulk reference append completed: updated {updated}, added refs {added}, skipped {skipped}, failed {failed}",
        "status_character_bulk_failed": "Bulk reference append failed: {error}",
        "status_character_bulk_interrupted": "Bulk reference append interrupted.",
        "status_character_bulk_cancelled": "Bulk reference append cancelled.",
        "status_character_delete_busy": "Character delete is running. Please wait.",
        "status_character_delete_background_start": "Deleting characters in background ({count})...",
        "status_character_delete_progress": "Deleting: {processed}/{total} current: {name}",
        "status_character_delete_batch_done": "Delete completed: success {deleted}, missing {missing}, failed {failed}",
        "status_character_delete_interrupted": "Character delete interrupted.",
        "status_character_delete_no_selection": "Please select characters in the local library first.",
        "status_character_delete_success": "Character deleted: {name}",
        "status_character_delete_failed": "Character delete failed: {error}",
        "dialog_character_delete_confirm_title": "Confirm Character Delete",
        "dialog_character_delete_confirm_message": "Delete {count} selected character(s) and their references from local library. This cannot be undone. Continue?",
        "dialog_character_delete_confirm_confirm": "Delete",
        "dialog_character_delete_confirm_cancel": "Cancel",
        "dialog_character_bulk_first_title": "First Bulk Reference Append",
        "dialog_character_bulk_first_message": "This will only append references for existing characters and will not add new characters. First run may be slow (limit {count} each). Keep the app open. Continue?",
        "dialog_character_bulk_first_confirm": "Continue",
        "dialog_character_bulk_first_cancel": "Cancel",
        "dialog_character_bulk_interrupt_title": "Interrupt Bulk Build",
        "dialog_character_bulk_interrupt_message": "Bulk build is still running. Closing now will interrupt it. Exit anyway?",
        "dialog_character_bulk_interrupt_confirm": "Interrupt and Exit",
        "dialog_character_bulk_interrupt_cancel": "Keep Running",
        "dialog_character_delete_interrupt_title": "Interrupt Character Delete",
        "dialog_character_delete_interrupt_message": "Character delete is still running in background. Closing now will interrupt it. Exit anyway?",
        "dialog_character_delete_interrupt_confirm": "Interrupt and Exit",
        "dialog_character_delete_interrupt_cancel": "Keep Running",
        "status_character_refs_no_selection": "Please select a local character before appending references.",
        "status_character_refs_multi_selection": "Append references supports a single character only. Select one character.",
        "status_character_refs_added": "Added {count} references to {name}.",
        "status_character_refs_failed": "Failed to append references: {error}",
        "settings_title": "Settings",
        "settings_subtitle": "Do not change unless necessary to keep analysis stable.",
        "settings_range_hint": "Threshold range: min {min}, max {max}.",
        "settings_diff_hint": "Lower values are looser (more hits); higher values are stricter (fewer hits).",
        "settings_language_title": "Language",
        "settings_character_recognition_label": "Recognize Characters",
        "settings_threshold_title": "Thresholds",
        "settings_threshold_helper": "Saved thresholds will be used in the next analysis run.",
        "settings_threshold_notes": "Notes:\nCustom Character Threshold: minimum similarity for custom library matching.\nCustom Character Margin: minimum top1-top2 gap; larger values reduce mixed identities.\nCopyright Threshold: minimum score for copyright/work tags.",
        "settings_reset": "Reset to Default",
        "settings_save": "Save Changes",
        "settings_rebuild_correlation_profiles": "Force Rebuild Correlation Profiles",
        "settings_rebuild_correlation_profiles_hint": "After updating custom-library references or feature rules, click to force rebuild correlation_profiles.json (custom character matching only; tag recognition is unchanged).",
        "settings_project_github": "Project GitHub",
        "settings_version_text": "Version v{version}",
        "settings_saved_toast": "Saved successfully",
        "settings_saved_status": "Settings saved and will apply to the next run.",
        "settings_rebuild_correlation_profiles_done_toast": "Rebuild completed",
        "settings_rebuild_correlation_profiles_failed_toast": "Rebuild failed",
        "status_open_project_github_failed": "Unable to open the project GitHub link.",
        "status_rebuild_correlation_profiles_start": "Starting forced rebuild of custom correlation profiles. Please wait...",
        "status_rebuild_correlation_profiles_running": "Custom correlation profiles are rebuilding. Please wait.",
        "status_rebuild_correlation_profiles_done": "Forced rebuild completed: generated {count} character correlation profiles.",
        "status_rebuild_correlation_profiles_empty": "Rebuild completed: no custom character references are currently available.",
        "status_rebuild_correlation_profiles_failed": "Forced rebuild failed: {error}",
        "threshold_feature": "Feature Threshold",
        "threshold_adult_feature": "Adult Feature Threshold",
        "threshold_footwear_feature": "Footwear Threshold",
        "threshold_barefoot_feature": "Barefoot Threshold",
        "threshold_custom_character": "Custom Character Threshold",
        "threshold_custom_character_margin": "Custom Character Margin",
        "threshold_copyright": "Copyright Threshold",
        "settings_spin_hint": "Min {min} / Max {max}",
        "feature_edit_tags": "Edit Tags",
        "btn_tag_editor_tooltip": "Edit tags for current image",
        "tag_editor_dialog_title": "Tag Editor",
        "tag_editor_left_title": "Features and Characters",
        "tag_editor_right_title": "Selected Tags",
        "tag_editor_feature_group_prefix": "Feature / ",
        "tag_editor_character_group_prefix": "Character / ",
        "tag_editor_rules": "Rules: double-click or drag tags between both sides; grayed items on the left are already selected.",
        "tag_editor_apply": "Apply",
        "tag_editor_cancel": "Cancel",
        "status_tag_editor_no_selection": "Select an image from the list before editing tags.",
        "status_tag_editor_saved": "Tags updated ({count} total).",
        "status_tag_editor_multi_required": "Select at least two images before batch editing tags.",
        "status_tag_editor_batch_no_changes": "No tags selected. Batch edit was not applied.",
        "status_tag_editor_batch_saved": "Added tags to {count} images (features {feature_count}, characters {character_count}).",
        "worker_log_running_command": "Running command: {command}",
        "worker_status_script_failed": "Script execution failed (exit code {code})",
        "worker_status_exception": "Execution error: {error}",
        "status_unknown_error": "Unknown error",
    },
    "ja-JP": {
        "menu_analysis": "分析",
        "menu_settings": "設定",
        "btn_choose_folder": "フォルダ選択",
        "btn_choose_images": "画像選択（複数）",
        "btn_remove_all": "すべて削除",
        "btn_clear_tags": "タグをクリア",
        "btn_remove_tagged": "タグありを削除",
        "btn_start_analysis": "分析開始",
        "btn_stop_analysis": "分析停止",
        "selected_count": "選択済み: {count}",
        "preview_placeholder": "プレビュー領域\nリストの画像を選択してください",
        "status_waiting_select": "状態: 画像選択待ち",
        "status_busy_modify_list": "分析中はリストを変更できません。",
        "status_clearing_tags_busy": "タグをクリア中です。完了後に分析を開始してください。",
        "status_clearing_tags": "状態: タグをクリアしています（{count} 件）...",
        "status_no_tagged_images": "状態: 既存タグ付き画像はありません",
        "status_tags_cleared": "状態: {count} 件の画像タグをクリアしました",
        "status_pending_analysis": "分析待ち",
        "status_clear_tags_failed": "タグのクリアに失敗: {error}",
        "status_exiftool_missing": "ExifTool が見つからないため、タグをクリアできません。",
        "dialog_clear_tags_title": "タグをクリア",
        "dialog_clear_tags_message": "{count} 件の画像の既存タグを削除します。タグ以外の情報は変更しません。続行しますか？",
        "dialog_clear_tags_confirm": "クリアする",
        "dialog_clear_tags_cancel": "キャンセル",
        "status_preview_failed": "プレビュー失敗: {name}",
        "status_please_select_images": "先に画像を選択してください。",
        "status_stopping_analysis": "分析を停止しています...",
        "status_analysis_started": "分析開始: {count}",
        "status_analysis_completed": "分析完了",
        "status_selected_images": "画像を選択: {count}",
        "status_loaded_folder": "フォルダを読み込み: {folder} ({count})",
        "dialog_choose_folder": "画像フォルダを選択",
        "dialog_choose_images": "画像を選択（複数可）",
        "status_prefix": "状態",
        "status_analysis_in_progress": "分析中...",
        "status_analysis_stopped": "分析を停止しました",
        "status_exec_failed": "実行失敗",
        "status_no_obvious_features": "明確な特徴は検出されませんでした",
        "section_character": "キャラ: ",
        "section_feature": "特徴: ",
        "section_tags": "タグ: ",
        "settings_title": "設定",
        "settings_subtitle": "必要がない場合は変更しないでください。分析の安定性に影響します。",
        "settings_range_hint": "しきい値範囲: 最小 {min}、最大 {max}。",
        "settings_diff_hint": "最小値は緩め（検出されやすい）、最大値は厳しめ（検出されにくい）です。",
        "settings_language_title": "言語",
        "settings_threshold_title": "しきい値",
        "settings_threshold_helper": "保存したしきい値は次回の分析で適用されます。",
        "settings_threshold_notes": "注記:\nカスタムキャラしきい値: カスタムライブラリ照合の最小類似度。\nカスタムキャラ差分マージン: 1位と2位候補の最小差。大きいほど混在しにくいです。\n作品しきい値: 作品(著作権)タグの最小スコア。",
        "settings_reset": "デフォルトに戻す",
        "settings_save": "変更を保存",
        "settings_rebuild_correlation_profiles": "相関プロファイルを強制再構築",
        "settings_rebuild_correlation_profiles_hint": "カスタムライブラリの参照画像や特徴ルールを更新した後、このボタンで correlation_profiles.json を強制再構築できます（カスタムキャラ照合のみ対象、タグ認識には影響しません）。",
        "settings_project_github": "プロジェクト GitHub",
        "settings_version_text": "バージョン v{version}",
        "settings_saved_toast": "保存しました",
        "settings_saved_status": "設定を保存しました。次回分析から有効です。",
        "settings_rebuild_correlation_profiles_done_toast": "再構築が完了しました",
        "settings_rebuild_correlation_profiles_failed_toast": "再構築に失敗しました",
        "status_open_project_github_failed": "プロジェクトの GitHub リンクを開けませんでした。",
        "status_rebuild_correlation_profiles_start": "カスタム相関プロファイルの強制再構築を開始しました。しばらくお待ちください...",
        "status_rebuild_correlation_profiles_running": "カスタム相関プロファイルを再構築中です。しばらくお待ちください。",
        "status_rebuild_correlation_profiles_done": "強制再構築が完了しました：{count} 件の相関プロファイルを生成しました。",
        "status_rebuild_correlation_profiles_empty": "再構築が完了しました：利用可能なカスタムキャラ参照データがありません。",
        "status_rebuild_correlation_profiles_failed": "強制再構築に失敗しました：{error}",
        "threshold_feature": "特徴しきい値",
        "threshold_adult_feature": "成人特徴しきい値",
        "threshold_footwear_feature": "靴特徴しきい値",
        "threshold_barefoot_feature": "裸足特徴しきい値",
        "threshold_custom_character": "カスタムキャラしきい値",
        "threshold_custom_character_margin": "カスタムキャラ差分マージン",
        "threshold_copyright": "作品しきい値",
        "settings_spin_hint": "最小 {min} / 最大 {max}",
    },
    "ko-KR": {
        "menu_analysis": "분석",
        "menu_settings": "설정",
        "btn_choose_folder": "폴더 선택",
        "btn_choose_images": "이미지 선택(다중)",
        "btn_remove_all": "전체 삭제",
        "btn_clear_tags": "태그 지우기",
        "btn_remove_tagged": "태그 포함 삭제",
        "btn_start_analysis": "분석 시작",
        "btn_stop_analysis": "분석 중지",
        "selected_count": "선택됨: {count}",
        "preview_placeholder": "미리보기 영역\n목록에서 이미지를 선택하세요",
        "status_waiting_select": "상태: 이미지 선택 대기",
        "status_busy_modify_list": "분석 중에는 목록을 수정할 수 없습니다.",
        "status_clearing_tags_busy": "태그를 지우는 중입니다. 완료 후 분석을 시작하세요.",
        "status_clearing_tags": "상태: 태그를 지우는 중 ({count}개)...",
        "status_no_tagged_images": "상태: 기존 태그가 있는 이미지가 없습니다",
        "status_tags_cleared": "상태: {count}개 이미지의 태그를 지웠습니다",
        "status_pending_analysis": "분석 대기",
        "status_clear_tags_failed": "태그 지우기 실패: {error}",
        "status_exiftool_missing": "ExifTool을 찾을 수 없어 태그를 지울 수 없습니다.",
        "dialog_clear_tags_title": "태그 지우기",
        "dialog_clear_tags_message": "{count}개 이미지의 기존 태그를 지웁니다. 다른 정보는 변경하지 않습니다. 계속할까요?",
        "dialog_clear_tags_confirm": "지우기",
        "dialog_clear_tags_cancel": "취소",
        "status_preview_failed": "미리보기 실패: {name}",
        "status_please_select_images": "먼저 이미지를 선택하세요.",
        "status_stopping_analysis": "분석을 중지하는 중...",
        "status_analysis_started": "분석 시작: {count}",
        "status_analysis_completed": "분석 완료",
        "status_selected_images": "선택한 이미지: {count}",
        "status_loaded_folder": "폴더 불러옴: {folder} ({count})",
        "dialog_choose_folder": "이미지 폴더 선택",
        "dialog_choose_images": "이미지 선택(여러 개)",
        "status_prefix": "상태",
        "status_analysis_in_progress": "분석 중...",
        "status_analysis_stopped": "분석이 중지되었습니다",
        "status_exec_failed": "실행 실패",
        "status_no_obvious_features": "뚜렷한 특징을 찾지 못했습니다",
        "section_character": "캐릭터: ",
        "section_feature": "특징: ",
        "section_tags": "태그: ",
        "settings_title": "설정",
        "settings_subtitle": "필요하지 않다면 변경하지 마세요. 분석 안정성에 영향을 줄 수 있습니다.",
        "settings_range_hint": "임계값 범위: 최소 {min}, 최대 {max}.",
        "settings_diff_hint": "최소값은 느슨함(더 잘 감지), 최대값은 엄격함(덜 감지)입니다.",
        "settings_language_title": "언어",
        "settings_threshold_title": "임계값",
        "settings_threshold_helper": "저장한 임계값은 다음 분석부터 적용됩니다.",
        "settings_threshold_notes": "참고:\n커스텀 캐릭터 임계값: 커스텀 라이브러리 매칭 최소 유사도입니다.\n커스텀 캐릭터 마진: 1순위와 2순위의 최소 차이로, 클수록 혼입이 줄어듭니다.\n작품 임계값: 작품(저작권) 태그 최소 점수입니다.",
        "settings_reset": "기본값으로 재설정",
        "settings_save": "변경 저장",
        "settings_rebuild_correlation_profiles": "상관 프로필 강제 재구축",
        "settings_rebuild_correlation_profiles_hint": "커스텀 라이브러리 참고 이미지나 특징 규칙을 갱신한 뒤, 이 버튼으로 correlation_profiles.json을 강제로 재구축할 수 있습니다(커스텀 캐릭터 매칭에만 적용되며 태그 인식에는 영향 없음).",
        "settings_project_github": "프로젝트 GitHub",
        "settings_version_text": "버전 v{version}",
        "settings_saved_toast": "저장되었습니다",
        "settings_saved_status": "설정이 저장되었고 다음 실행부터 적용됩니다.",
        "settings_rebuild_correlation_profiles_done_toast": "재구축이 완료되었습니다",
        "settings_rebuild_correlation_profiles_failed_toast": "재구축에 실패했습니다",
        "status_open_project_github_failed": "프로젝트 GitHub 링크를 열 수 없습니다.",
        "status_rebuild_correlation_profiles_start": "커스텀 상관 프로필 강제 재구축을 시작합니다. 잠시만 기다려 주세요...",
        "status_rebuild_correlation_profiles_running": "커스텀 상관 프로필을 재구축하는 중입니다. 잠시만 기다려 주세요.",
        "status_rebuild_correlation_profiles_done": "강제 재구축 완료: 캐릭터 상관 프로필 {count}개를 생성했습니다.",
        "status_rebuild_correlation_profiles_empty": "재구축 완료: 현재 사용 가능한 커스텀 캐릭터 참고 데이터가 없습니다.",
        "status_rebuild_correlation_profiles_failed": "강제 재구축 실패: {error}",
        "threshold_feature": "특징 임계값",
        "threshold_adult_feature": "성인 특징 임계값",
        "threshold_footwear_feature": "신발 특징 임계값",
        "threshold_barefoot_feature": "맨발 특징 임계값",
        "threshold_custom_character": "커스텀 캐릭터 임계값",
        "threshold_custom_character_margin": "커스텀 캐릭터 마진",
        "threshold_copyright": "작품 임계값",
        "settings_spin_hint": "최소 {min} / 최대 {max}",
    },
}


CHARACTER_LIBRARY_TRANSLATION_OVERRIDES: dict[str, dict[str, str]] = {
    "ja-JP": {
        "menu_characters": "キャラライブラリ",
        "character_page_title": "キャラライブラリ管理",
        "character_search_placeholder": "キャラ名または作品名でオンライン検索",
        "character_search_button": "オンラインキャラ",
        "character_library_search_placeholder": "ローカルライブラリ検索（キャラ/作品、多言語対応）",
        "character_library_search_button": "ローカル検索",
        "dialog_image_files_filter": "画像ファイル (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff)",
        "character_work_search_button": "作品で検索（Fandom）",
        "character_bulk_count_label": "キャラごとの上限",
        "character_bulk_build_button": "一括補充（既存キャラのみ）",
        "character_import_button": "選択キャラを登録",
        "character_delete_button": "選択キャラを削除",
        "character_add_refs_button": "参照画像を追加",
        "character_refresh_button": "一覧を更新",
        "character_search_results_title": "オンライン候補",
        "character_library_title": "ローカルキャラライブラリ",
        "character_library_list_disabled_suffix": "（無効）",
        "character_library_list_refs_label": "参照画像:",
        "feature_edit_tags": "タグを編集",
        "worker_log_running_command": "コマンド実行: {command}",
        "worker_status_script_failed": "スクリプト実行に失敗しました（終了コード {code}）",
        "worker_status_exception": "実行中に例外が発生しました: {error}",
        "status_unknown_error": "不明なエラー",
        "status_character_search_empty_keyword": "検索前にキャラ名を入力してください。",
        "status_character_searching": "キャラを検索中です。しばらくお待ちください...",
        "status_character_search_done": "キャラ検索完了：候補 {count} 件",
        "status_character_search_failed": "キャラ検索に失敗しました：{error}",
        "status_character_library_searching": "ローカルライブラリを検索中です。しばらくお待ちください...",
        "status_character_library_search_running": "ローカルライブラリ検索が進行中です。しばらくお待ちください。",
        "status_character_library_search_done": "ローカルライブラリ検索完了：{count} 件。",
        "status_character_library_search_failed": "ローカルライブラリ検索に失敗しました：{error}",
        "status_character_work_searching": "Fandom作品を検索中です。しばらくお待ちください...",
        "status_character_work_search_done": "作品候補を取得しました：{count} 件。正しい作品を選択してください。",
        "status_character_work_no_result": "利用可能な Fandom 作品候補が見つかりませんでした。より具体的な作品名で再試行してください。",
        "status_character_work_search_failed": "作品検索に失敗しました：{error}",
        "status_character_work_pick_cancelled": "作品の選択をキャンセルしました。",
        "status_character_work_fetching": "作品キャラ候補を取得中：{title}（{domain}）...",
        "status_character_work_fetch_done": "作品キャラ候補を読み込みました：{title}、{count} 件。",
        "status_character_work_fetch_failed": "作品キャラの取得に失敗しました：{error}",
        "status_character_bulk_recovered": "前回の一括補充が正常終了していないため、中断として復旧しました。",
        "status_character_bulk_running": "キャラライブラリの一括補充を実行中です。しばらくお待ちください。",
        "status_character_bulk_no_existing": "ローカルキャラライブラリが空です。先にキャラを追加してください。",
        "status_character_bulk_start": "一括補充を開始：既存キャラ {count} 件（1キャラ上限 {limit} 枚）。アプリを閉じないでください。",
        "status_character_bulk_progress_waiting": "候補キャラを取得中...",
        "status_character_bulk_progress": "一括補充中：{processed}/{total}（更新 {updated}、参照画像追加 {added}、スキップ {skipped}）現在：{name}",
        "status_character_bulk_done": "一括補充が完了しました：更新 {updated}、参照画像追加 {added}、スキップ {skipped}、失敗 {failed}",
        "status_character_bulk_failed": "一括補充に失敗しました：{error}",
        "status_character_bulk_interrupted": "一括補充が中断されました。",
        "status_character_bulk_cancelled": "一括補充をキャンセルしました。",
        "status_character_import_no_selection": "先にオンライン候補キャラを選択してください。",
        "status_character_import_success": "キャラを登録しました：{name}",
        "status_character_import_failed": "キャラ登録に失敗しました：{error}",
        "status_character_import_batch_result": "キャラ登録完了：成功 {success}、失敗 {failed}",
        "status_character_import_batch_result_with_skipped": "キャラ登録完了：成功 {success}、失敗 {failed}、キャンセル {skipped}",
        "status_character_import_cancelled_all": "今回のキャラ登録をキャンセルしました。",
        "dialog_character_merge_confirm_title": "同一キャラの可能性を検出",
        "dialog_character_merge_confirm_text": "候補キャラは既存キャラと同一人物の可能性があります。処理方法を選択してください。",
        "dialog_character_merge_confirm_details": "既存プロバイダ紐付け：{links}",
        "dialog_character_merge_confirm_merge": "既存キャラに統合",
        "dialog_character_merge_confirm_new": "新規キャラとして追加",
        "dialog_character_merge_confirm_cancel": "キャンセル",
        "dialog_character_merge_candidate_title": "候補キャラ",
        "dialog_character_merge_existing_title": "既存キャラ",
        "dialog_character_merge_source_line": "作品：{source}",
        "dialog_character_merge_links_line": "プロバイダ：{links}",
        "status_character_delete_no_selection": "ローカルキャラライブラリで先にキャラを選択してください。",
        "status_character_delete_busy": "キャラ削除を実行中です。しばらくお待ちください。",
        "status_character_delete_background_start": "バックグラウンドでキャラを削除中（{count} 件）...",
        "status_character_delete_progress": "削除中：{processed}/{total}、現在：{name}",
        "status_character_delete_batch_done": "キャラ削除完了：成功 {deleted}、未存在 {missing}、失敗 {failed}",
        "status_character_delete_interrupted": "キャラ削除が中断されました。",
        "status_character_delete_success": "キャラを削除しました：{name}",
        "status_character_delete_failed": "キャラ削除に失敗しました：{error}",
        "dialog_character_delete_confirm_title": "キャラ削除の確認",
        "dialog_character_delete_confirm_message": "ローカルキャラライブラリから選択した {count} 件のキャラと参照画像を削除します。この操作は取り消せません。続行しますか？",
        "dialog_character_delete_confirm_confirm": "削除する",
        "dialog_character_delete_confirm_cancel": "キャンセル",
        "status_character_refs_no_selection": "先にローカルキャラを選択してから参照画像を追加してください。",
        "status_character_refs_multi_selection": "参照画像の追加は単一キャラのみ対応です。1件だけ選択してください。",
        "status_character_refs_added": "{name} に参照画像を {count} 枚追加しました。",
        "status_character_refs_failed": "参照画像の追加に失敗しました：{error}",
        "dialog_character_bulk_first_title": "初回一括補充の確認",
        "dialog_character_bulk_first_message": "既存キャラにのみ参照画像を追加し、新規キャラは追加しません。初回は時間がかかる場合があります（1キャラ上限 {count} 枚）。アプリを閉じないでください。続行しますか？",
        "dialog_character_bulk_first_confirm": "続行",
        "dialog_character_bulk_first_cancel": "キャンセル",
        "dialog_character_bulk_interrupt_title": "一括補充を中断",
        "dialog_character_bulk_interrupt_message": "一括補充がまだ実行中です。今閉じると処理が中断されます。終了しますか？",
        "dialog_character_bulk_interrupt_confirm": "中断して終了",
        "dialog_character_bulk_interrupt_cancel": "処理を継続",
        "dialog_character_delete_interrupt_title": "キャラ削除を中断",
        "dialog_character_delete_interrupt_message": "キャラ削除がバックグラウンドで実行中です。今閉じると処理が中断されます。終了しますか？",
        "dialog_character_delete_interrupt_confirm": "中断して終了",
        "dialog_character_delete_interrupt_cancel": "処理を継続",
        "dialog_character_work_pick_title": "作品を選択",
        "dialog_character_work_pick_label": "正しい Fandom 作品を選択してください：",
    },
    "ko-KR": {
        "menu_characters": "캐릭터 라이브러리",
        "character_page_title": "캐릭터 라이브러리 관리",
        "character_search_placeholder": "캐릭터명 또는 작품명으로 온라인 검색",
        "character_search_button": "온라인 캐릭터",
        "character_library_search_placeholder": "로컬 라이브러리 검색(캐릭터/작품, 다국어 지원)",
        "character_library_search_button": "로컬 검색",
        "dialog_image_files_filter": "이미지 파일 (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff)",
        "character_work_search_button": "작품으로 검색(Fandom)",
        "character_bulk_count_label": "캐릭터별 최대 수",
        "character_bulk_build_button": "일괄 보강(기존 캐릭터만)",
        "character_import_button": "선택 캐릭터 등록",
        "character_delete_button": "선택 캐릭터 삭제",
        "character_add_refs_button": "참고 이미지 추가",
        "character_refresh_button": "목록 새로고침",
        "character_search_results_title": "온라인 후보 결과",
        "character_library_title": "로컬 캐릭터 라이브러리",
        "character_library_list_disabled_suffix": "(비활성화)",
        "character_library_list_refs_label": "참고 이미지:",
        "feature_edit_tags": "태그 편집",
        "worker_log_running_command": "명령 실행: {command}",
        "worker_status_script_failed": "스크립트 실행 실패(종료 코드 {code})",
        "worker_status_exception": "실행 중 예외 발생: {error}",
        "status_unknown_error": "알 수 없는 오류",
        "status_character_search_empty_keyword": "검색 전에 캐릭터 이름을 입력하세요.",
        "status_character_searching": "캐릭터를 검색하는 중입니다. 잠시만 기다려 주세요...",
        "status_character_search_done": "캐릭터 검색 완료: 후보 {count}개",
        "status_character_search_failed": "캐릭터 검색 실패: {error}",
        "status_character_library_searching": "로컬 라이브러리를 검색하는 중입니다. 잠시만 기다려 주세요...",
        "status_character_library_search_running": "로컬 라이브러리 검색이 이미 진행 중입니다.",
        "status_character_library_search_done": "로컬 라이브러리 검색 완료: {count}개.",
        "status_character_library_search_failed": "로컬 라이브러리 검색 실패: {error}",
        "status_character_work_searching": "Fandom 작품을 검색하는 중입니다. 잠시만 기다려 주세요...",
        "status_character_work_search_done": "작품 후보 {count}개를 가져왔습니다. 올바른 작품을 선택하세요.",
        "status_character_work_no_result": "사용 가능한 Fandom 작품 후보를 찾지 못했습니다. 더 구체적인 작품명으로 다시 시도하세요.",
        "status_character_work_search_failed": "작품 검색 실패: {error}",
        "status_character_work_pick_cancelled": "작품 선택을 취소했습니다.",
        "status_character_work_fetching": "작품 캐릭터 후보를 불러오는 중: {title}({domain})...",
        "status_character_work_fetch_done": "작품 캐릭터 후보 로드 완료: {title}, 총 {count}개.",
        "status_character_work_fetch_failed": "작품 캐릭터 불러오기 실패: {error}",
        "status_character_bulk_recovered": "이전 일괄 보강이 정상 종료되지 않아 중단 상태로 복구했습니다.",
        "status_character_bulk_running": "캐릭터 라이브러리 일괄 보강이 진행 중입니다. 잠시만 기다려 주세요.",
        "status_character_bulk_no_existing": "로컬 캐릭터 라이브러리가 비어 있습니다. 먼저 캐릭터를 추가해 주세요.",
        "status_character_bulk_start": "일괄 보강 시작: 기존 캐릭터 {count}개(캐릭터당 최대 {limit}장). 앱을 종료하지 마세요.",
        "status_character_bulk_progress_waiting": "후보 캐릭터를 불러오는 중...",
        "status_character_bulk_progress": "일괄 보강 중: {processed}/{total}(업데이트 {updated}, 참고 이미지 추가 {added}, 건너뜀 {skipped}) 현재: {name}",
        "status_character_bulk_done": "일괄 보강 완료: 업데이트 {updated}, 참고 이미지 추가 {added}, 건너뜀 {skipped}, 실패 {failed}",
        "status_character_bulk_failed": "일괄 보강 실패: {error}",
        "status_character_bulk_interrupted": "일괄 보강이 중단되었습니다.",
        "status_character_bulk_cancelled": "일괄 보강을 취소했습니다.",
        "status_character_import_no_selection": "먼저 온라인 후보 캐릭터를 선택하세요.",
        "status_character_import_success": "캐릭터 등록 완료: {name}",
        "status_character_import_failed": "캐릭터 등록 실패: {error}",
        "status_character_import_batch_result": "캐릭터 등록 완료: 성공 {success}, 실패 {failed}",
        "status_character_import_batch_result_with_skipped": "캐릭터 등록 완료: 성공 {success}, 실패 {failed}, 취소 {skipped}",
        "status_character_import_cancelled_all": "이번 캐릭터 등록을 취소했습니다.",
        "dialog_character_merge_confirm_title": "동일 캐릭터 가능성 감지",
        "dialog_character_merge_confirm_text": "후보 캐릭터가 기존 캐릭터와 동일 인물일 수 있습니다. 처리 방식을 선택하세요.",
        "dialog_character_merge_confirm_details": "기존 제공처 링크: {links}",
        "dialog_character_merge_confirm_merge": "기존 캐릭터에 병합",
        "dialog_character_merge_confirm_new": "새 캐릭터로 추가",
        "dialog_character_merge_confirm_cancel": "취소",
        "dialog_character_merge_candidate_title": "후보 캐릭터",
        "dialog_character_merge_existing_title": "기존 캐릭터",
        "dialog_character_merge_source_line": "작품: {source}",
        "dialog_character_merge_links_line": "제공처: {links}",
        "status_character_delete_no_selection": "로컬 캐릭터 라이브러리에서 먼저 캐릭터를 선택하세요.",
        "status_character_delete_busy": "캐릭터 삭제가 진행 중입니다. 잠시만 기다려 주세요.",
        "status_character_delete_background_start": "백그라운드에서 캐릭터 삭제 중({count}개)...",
        "status_character_delete_progress": "삭제 진행: {processed}/{total}, 현재: {name}",
        "status_character_delete_batch_done": "캐릭터 삭제 완료: 성공 {deleted}, 없음 {missing}, 실패 {failed}",
        "status_character_delete_interrupted": "캐릭터 삭제가 중단되었습니다.",
        "status_character_delete_success": "캐릭터 삭제 완료: {name}",
        "status_character_delete_failed": "캐릭터 삭제 실패: {error}",
        "dialog_character_delete_confirm_title": "캐릭터 삭제 확인",
        "dialog_character_delete_confirm_message": "로컬 캐릭터 라이브러리에서 선택한 캐릭터 {count}개와 참고 이미지를 삭제합니다. 이 작업은 되돌릴 수 없습니다. 계속할까요?",
        "dialog_character_delete_confirm_confirm": "삭제",
        "dialog_character_delete_confirm_cancel": "취소",
        "status_character_refs_no_selection": "먼저 로컬 캐릭터를 선택한 뒤 참고 이미지를 추가하세요.",
        "status_character_refs_multi_selection": "참고 이미지 추가는 단일 캐릭터만 지원합니다. 한 캐릭터만 선택하세요.",
        "status_character_refs_added": "{name}에 참고 이미지 {count}장을 추가했습니다.",
        "status_character_refs_failed": "참고 이미지 추가 실패: {error}",
        "dialog_character_bulk_first_title": "첫 일괄 보강 안내",
        "dialog_character_bulk_first_message": "기존 캐릭터에만 참고 이미지를 추가하며 새 캐릭터는 생성하지 않습니다. 첫 실행은 시간이 오래 걸릴 수 있습니다(캐릭터당 최대 {count}장). 앱을 종료하지 마세요. 계속할까요?",
        "dialog_character_bulk_first_confirm": "계속",
        "dialog_character_bulk_first_cancel": "취소",
        "dialog_character_bulk_interrupt_title": "일괄 보강 중단",
        "dialog_character_bulk_interrupt_message": "일괄 보강이 아직 진행 중입니다. 지금 닫으면 작업이 중단됩니다. 종료할까요?",
        "dialog_character_bulk_interrupt_confirm": "중단하고 종료",
        "dialog_character_bulk_interrupt_cancel": "계속 실행",
        "dialog_character_delete_interrupt_title": "캐릭터 삭제 중단",
        "dialog_character_delete_interrupt_message": "캐릭터 삭제가 백그라운드에서 진행 중입니다. 지금 닫으면 작업이 중단됩니다. 종료할까요?",
        "dialog_character_delete_interrupt_confirm": "중단하고 종료",
        "dialog_character_delete_interrupt_cancel": "계속 실행",
        "dialog_character_work_pick_title": "작품 선택",
        "dialog_character_work_pick_label": "올바른 Fandom 작품을 선택하세요:",
    },
}


def _apply_character_library_translation_overrides() -> None:
    """Apply manual localization overrides for character-library management texts."""
    for language_code, entries in CHARACTER_LIBRARY_TRANSLATION_OVERRIDES.items():
        TRANSLATIONS.setdefault(language_code, {}).update(entries)


def _humanize_tag_id(tag_id: str) -> str:
    """Convert canonical tag id into a readable title text."""
    text = re.sub(r"[_\-\s]+", " ", str(tag_id or "").strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text.title() if text else ""


def _language_candidates(language_code: str) -> tuple[str, ...]:
    """Return normalized language key candidates for i18n lookup."""
    normalized = normalize_language_code(language_code)
    mapping = {
        "zh-CN": ("zh-CN", "zh_CN", "zh-Hans", "zh", "zh-hans"),
        "en-US": ("en-US", "en_US", "en", "en-us"),
        "ja-JP": ("ja-JP", "ja_JP", "ja", "ja-jp"),
        "ko-KR": ("ko-KR", "ko_KR", "ko", "ko-kr"),
    }
    return mapping.get(normalized, (normalized,))


def _tag_name_field_candidates(language_code: str) -> tuple[str, ...]:
    """Return fallback field names for localized tag lookup."""
    normalized = normalize_language_code(language_code)
    if normalized == "zh-CN":
        return ("name_zh_cn", "name_zh")
    if normalized == "en-US":
        return ("name_en_us", "name_en")
    if normalized == "ja-JP":
        return ("name_ja_jp", "name_ja", "name_en")
    if normalized == "ko-KR":
        return ("name_ko_kr", "name_ko", "name_en")
    return ("name_en", "name_zh")


def _resolve_localized_tag_name(tag: dict, language_code: str, tag_id: str) -> str:
    """Resolve localized display name from one taxonomy tag payload."""
    i18n_payload = tag.get("name_i18n", {})
    if isinstance(i18n_payload, dict):
        for candidate in _language_candidates(language_code):
            value = str(i18n_payload.get(candidate, "")).strip()
            if value:
                return value

    for field_name in _tag_name_field_candidates(language_code):
        value = str(tag.get(field_name, "")).strip()
        if value:
            return value

    normalized = normalize_language_code(language_code)
    zh_name = str(tag.get("name_zh", "")).strip()
    if zh_name and normalized == "zh-CN":
        return zh_name

    en_name = str(tag.get("name_en", "")).strip()
    if en_name:
        return en_name

    if zh_name:
        return zh_name if normalized == "zh-CN" else _humanize_tag_id(tag_id)

    return _humanize_tag_id(tag_id) or str(tag_id).strip()


def _complete_translation_maps() -> None:
    """Backfill missing translation keys to avoid accidental default-language leakage."""
    default_map = TRANSLATIONS.get(DEFAULT_LANGUAGE, {})
    english_map = TRANSLATIONS.get("en-US", {})
    for language_code, language_map in TRANSLATIONS.items():
        for key, default_value in default_map.items():
            if key in language_map:
                continue
            fallback = ""
            if language_code in {"ja-JP", "ko-KR"}:
                fallback = english_map.get(key, "")
            elif language_code == "en-US":
                fallback = english_map.get(key, "")
            language_map[key] = fallback or default_value


_apply_character_library_translation_overrides()
_complete_translation_maps()

def compute_row_rect(item_rect: QRect) -> QRect:
    """Compute inner row rect used for custom painting."""
    return item_rect.adjusted(ROW_MARGIN_X, ROW_MARGIN_Y, -ROW_MARGIN_X, -ROW_MARGIN_Y)


def compute_delete_button_rect(item_rect: QRect) -> QRect:
    """Compute delete button rect in item coordinates."""
    row_rect = compute_row_rect(item_rect)
    x = row_rect.right() - DELETE_BUTTON_MARGIN - DELETE_BUTTON_SIZE
    y = row_rect.top() + DELETE_BUTTON_MARGIN
    return QRect(x, y, DELETE_BUTTON_SIZE, DELETE_BUTTON_SIZE)


def compute_delete_hit_rect(item_rect: QRect) -> QRect:
    """Compute clickable hit rect for delete action."""
    delete_rect = compute_delete_button_rect(item_rect)
    # UX tuning: shift hit area slightly to the left and keep right side tight.
    return delete_rect.adjusted(-18, -10, 2, 10)


def compute_tag_edit_button_rect(item_rect: QRect) -> QRect:
    """Compute tag-edit button rect in item coordinates."""
    row_rect = compute_row_rect(item_rect)
    x = row_rect.right() - TAG_EDIT_BUTTON_MARGIN - TAG_EDIT_BUTTON_SIZE
    y = row_rect.bottom() - TAG_EDIT_BUTTON_MARGIN - TAG_EDIT_BUTTON_SIZE
    return QRect(x, y, TAG_EDIT_BUTTON_SIZE, TAG_EDIT_BUTTON_SIZE)


def compute_tag_edit_hit_rect(item_rect: QRect) -> QRect:
    """Compute clickable hit rect for tag-edit action."""
    tag_rect = compute_tag_edit_button_rect(item_rect)
    return tag_rect.adjusted(-18, -10, 2, 10)

def normalize_path_key(path: Path) -> str:
    """Normalize path key for cross-platform matching.

    Args:
        path: Image path.

    Returns:
        Lower-cased absolute path string with slash separators.
    """
    return str(path.resolve()).replace("\\", "/").lower()


def collect_images_from_folder(folder: Path) -> list[Path]:
    """Collect supported images recursively from folder.

    Args:
        folder: Root folder.

    Returns:
        Sorted image path list.
    """
    if not folder.exists():
        return []
    images = [path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS]
    return sorted(images)


def load_app_icon() -> QIcon | None:
    """Load application icon from local assets.

    Returns:
        Loaded icon when file exists, otherwise None.
    """
    if not APP_ICON_PATH.exists():
        return None
    return QIcon(str(APP_ICON_PATH))


def load_window_close_icon() -> QIcon | None:
    """Load close button icon from local assets."""
    if not WINDOW_CLOSE_ICON_PATH.exists():
        return None
    return QIcon(str(WINDOW_CLOSE_ICON_PATH))


def load_list_delete_icon() -> QIcon | None:
    """Load image-list delete button icon from local assets."""
    if not LIST_DELETE_ICON_PATH.exists():
        return None
    return QIcon(str(LIST_DELETE_ICON_PATH))


def load_tag_editor_icon() -> QIcon | None:
    """Load image-list tag-editor button icon from local assets."""
    if not TAG_EDITOR_ICON_PATH.exists():
        return None
    return QIcon(str(TAG_EDITOR_ICON_PATH))


def load_taxonomy_name_map(
    taxonomy_path: Path,
    sensitive_terms_path: Path | None = None,
    language_code: str = DEFAULT_LANGUAGE,
) -> dict[str, str]:
    """Load tag id -> localized display name map.

    Args:
        taxonomy_path: Taxonomy JSON path.
        sensitive_terms_path: Optional sensitive terms extension path.
        language_code: Target UI language code.

    Returns:
        Mapping from tag id to localized name.
    """
    if not taxonomy_path.exists():
        return {}
    with taxonomy_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        return {}

    extension_path = sensitive_terms_path if sensitive_terms_path else taxonomy_path.parent / "sensitive_terms.json"
    if extension_path.exists():
        with extension_path.open("r", encoding="utf-8") as file:
            extension_payload = json.load(file)
        extension_taxonomy = extension_payload.get("taxonomy", {}) if isinstance(extension_payload, dict) else {}
        if isinstance(extension_taxonomy, dict):
            extra_categories = extension_taxonomy.get("categories", [])
            if isinstance(extra_categories, list):
                payload.setdefault("categories", [])
                payload["categories"].extend(extra_categories)

    result: dict[str, str] = {}
    for category in payload.get("categories", []):
        for tag in category.get("tags", []):
            tag_id = str(tag.get("id", "")).strip()
            if not tag_id:
                continue
            localized_name = _resolve_localized_tag_name(tag, language_code=language_code, tag_id=tag_id)
            if localized_name:
                result[tag_id] = localized_name
    return result


def clamp_threshold(value: float) -> float:
    """Clamp threshold value into accepted range."""
    return min(THRESHOLD_MAX_VALUE, max(THRESHOLD_MIN_VALUE, float(value)))


def parse_settings_bool(value: object, default: bool = False) -> bool:
    """Parse a QSettings boolean-like value with fallback."""
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return bool(default)
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def normalize_language_code(value: str) -> str:
    """Resolve language code fallback."""
    candidate = str(value or "").strip()
    lowered = candidate.lower().replace("_", "-")
    if lowered in {"zh-tw", "zh-hant"}:
        return DEFAULT_LANGUAGE
    valid_codes = {code for code, _ in LANGUAGE_OPTIONS}
    if candidate in valid_codes:
        return candidate
    if lowered in {"zh-cn", "zh-hans"}:
        return DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE
