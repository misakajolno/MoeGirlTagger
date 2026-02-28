# Docker API 最小骨架

## 启动

```bash
docker compose -f docker/docker-compose.api.yml up --build
```

服务默认监听 `http://localhost:8000`。

## 接口

- 健康检查：`GET /health`
- 执行打标：`POST /v1/tagging/run`

## 示例请求

```json
{
  "image_dir": "image",
  "queue_output": "data/annotation_queue/pending_annotations.jsonl",
  "feature_threshold": 0.68,
  "copyright_threshold": 0.8
}
```

## 目录挂载

- `../data` → `/app/data`
- `../tools` → `/app/tools`
- `../image` → `/app/image`
- `../image_high_precision` → `/app/image_high_precision`
