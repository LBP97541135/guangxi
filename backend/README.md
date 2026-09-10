# 光隙后端

## 本地启动

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

启动后访问：

- 健康检查：http://127.0.0.1:8000/api/health
- OpenAPI 文档：http://127.0.0.1:8000/docs

## 运行测试

```bash
cd backend
uv run pytest -q
```

## 环境变量

复制 `.env.example` 为 `.env` 后按需修改。`MODEL_PROVIDER=fake` 时不联网即可跑通全部流程；接入真实模型时改为 `real` 并填写 `MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME`（任何 OpenAI 协议兼容服务均可）。
