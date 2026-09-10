# 光隙后端

三轮对话 + 金句生成的 Demo 后端。架构与任务拆分见 [docs/](../docs/)。

## 接口一览

统一前缀 `/api`，字段为 camelCase：

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/sessions` | 创建匿名会话，返回第一问（201） |
| `GET` | `/api/sessions/{session_id}` | 查询当前进度或最终金句（刷新恢复） |
| `POST` | `/api/sessions/{session_id}/answers` | 提交当前轮答案；第三轮后生成金句 |
| `POST` | `/api/sessions/{session_id}/retry` | 生成失败后重新生成 |
| `GET` | `/api/health` | 健康检查 |

会话状态机：`QUESTION_1 → QUESTION_2 → QUESTION_3 → GENERATING → COMPLETED / FAILED`。
错误统一返回 `{"error": {"code", "message", "retryable"}}`，错误码见 `app/error_codes.py`。

## 本地启动

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

- 健康检查：http://127.0.0.1:8000/api/health
- OpenAPI 文档：http://127.0.0.1:8000/docs

## 运行测试

```bash
cd backend
uv run pytest -q
```

测试使用内存 SQLite，不需要真实模型 Key，不联网。

## 环境变量

复制 `.env.example` 为 `.env` 后按需修改：

| 变量 | 默认 | 说明 |
|---|---|---|
| `ENV` | `dev` | 运行环境标识 |
| `DATABASE_URL` | `sqlite:///./guangxi.db` | 本地 SQLite；公网部署可换 `postgresql://...` |
| `MODEL_PROVIDER` | `fake` | `fake` 不联网跑通全流程；`real` 走 OpenAI 协议 |
| `MODEL_API_KEY` | 空 | 仅 `real` 需要 |
| `MODEL_BASE_URL` | `https://api.openai.com/v1` | 任何 OpenAI 协议兼容服务 |
| `MODEL_NAME` | 空 | 仅 `real` 需要 |
| `MODEL_TIMEOUT_SECONDS` | `15` | 单次模型调用超时 |
| `QUOTE_MAX_CHARS` | `50` | 金句最大字数（含标点） |
| `ANSWER_MAX_CHARS` | `500` | 自由回答最大字数 |
| `ALLOW_CORS_ORIGINS` | `*` | 允许的前端来源，逗号分隔 |

## Fake / 真实模型切换

- **Fake 模式**（默认）：`MODEL_PROVIDER=fake`，不联网即可完整跑通三轮与金句返回（固定文案），适合前端联调和演示兜底。
- **真实模式**：`MODEL_PROVIDER=real`，配置 `MODEL_API_KEY`、`MODEL_BASE_URL`、`MODEL_NAME` 即可，不改代码。模型输出不合格或超时会自动重试一次，仍失败则返回 `GENERATION_FAILED`（`retryable=true`），三轮回答保留，用户可点重试。

## 内容配置

- 三问与快捷选项：`config/questions.json`（策划终稿直接替换此文件，轮次 Key、选项 Key 不得重复）。
- 金句写作规则：`config/prompt.txt`（前缀、字数、禁词要求需与 `app/llm/validator.py` 保持一致）。

## 部署（SQLite 单机）

1. 服务器安装 Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)。
2. 上传仓库，`cd backend && uv sync --no-dev`。
3. 配置 `.env`（真实模型时填 Key；公网建议收紧 `ALLOW_CORS_ORIGINS`）。
4. 启动：`uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`。
5. 如需公网多人体验，把 `DATABASE_URL` 换成 PostgreSQL 地址即可，代码无需改动。

## 演示前检查清单

- [ ] `/api/health` 返回 `{"status":"ok"}`。
- [ ] 数据库文件可写（或 PostgreSQL 连接正常）。
- [ ] 模型 Key 与额度有效（真实模式）。
- [ ] `MODEL_PROVIDER=fake` 备用模式可用，可随时切换兜底。
- [ ] 完整三轮真实请求至少成功一次。
- [ ] 前端使用的 API 地址与 `ALLOW_CORS_ORIGINS` 正确。
- [ ] 演示录屏已准备，不依赖现场网络必然稳定。

## 演示故障预案

- 模型服务不可用或超时：会话进入 `FAILED`，前端出现重试入口；连续失败可临时把 `.env` 改为 `MODEL_PROVIDER=fake` 重启，用固定金句完成演示。
- 数据库损坏：删除 SQLite 文件重启即可重建表结构（演示数据可丢弃）。
- 接口异常：所有错误为统一 JSON 结构，`retryable=true` 时前端展示重试按钮。
