# Third-Party Notices

本项目可能会在本地使用或下载以下第三方组件。  
请在分发、商用或公开发布时，按对应许可证要求保留声明并遵守条款。

## 1) WD14 Tagger Model

- 名称: `wd-v1-4-convnextv2-tagger-v2`
- 来源: Hugging Face / SmilingWolf
- 链接: https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2
- 许可证: Apache License 2.0
- 用途: 图片标签识别（本地 ONNX 推理）

## 2) ExifTool

- 名称: ExifTool by Phil Harvey
- 来源: https://exiftool.org/
- 链接: https://github.com/exiftool/exiftool
- 许可证: Artistic License 2.0 (或 GPL，按上游说明)
- 用途: 将标签写入图片元数据（如 `XMP-dc:Subject` / `XPKeywords`）

## 3) Python 依赖（按环境安装）

以下依赖通常通过 `pip` 安装，请以你实际 `requirements` 和锁定版本为准：

- `requests`
- `beautifulsoup4`
- `numpy`
- `onnxruntime`
- `Pillow`

这些依赖各自遵循其官方仓库声明的开源许可证。

---

## 合规建议

- 仓库中默认不提交原始图片、模型权重和本地工具二进制。  
- 仅提交脚本与配置文件，第三方资源在用户本地按需下载。  
- 若你计划公开发布，请在发布前再次核对：
  - 第三方许可证兼容性
  - 图片素材版权归属与授权范围
  - 平台内容政策（尤其是成人内容相关规则）
