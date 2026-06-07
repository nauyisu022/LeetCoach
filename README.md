# LeetCoach

LeetCoach 是一个本地运行的 LeetCode 练习平台。它包含 React 前端、FastAPI 后端、本地 Python 判题器、SQLite 练习状态、可选的 Claude AI 教练、题目笔记和 CodeTop 高频题元数据。

## 功能

- 按难度、考点、状态、关键词和 CodeTop 热度筛选题目。
- 在 Monaco 编辑器里编写 Python 解法。
- 使用 `运行` 执行自定义输入，支持实际输出和期望输出对比。
- 使用 `提交` 跑题目保存的完整测试集。
- 查看提交记录、失败断言和运行耗时。
- 自动保存每道题的本地草稿解法。
- 配置 Anthropic 后，可以让 AI 解释题目、诊断失败原因、起草复习笔记。
- 为每道题保存 Markdown 笔记，并沉淀考点记忆。
- 同步 CodeTop 公开元数据，用公司高频信号辅助刷题排序。

## 环境要求

- Node.js 18+
- npm
- Python 3.11+
- 本地 LeetCode 数据集目录，或通过 `LEETCODE_DATASET_PATH` 指定数据集路径

可选：

- Anthropic API 凭据，用于 AI 教练和 AI 生成笔记。
- Judge0 服务，用于替代默认的本地 Python 判题器。

## 安装

```bash
npm install
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

## 导入题库

默认数据集路径是：

```text
/Users/admin/Downloads/leetcode-dataset-check/LeetCodeDataset
```

如果你的数据集在其他位置：

```bash
export LEETCODE_DATASET_PATH=/path/to/LeetCodeDataset
```

导入题目到本地 SQLite：

```bash
backend/.venv/bin/python -m app.importer
```

默认数据库路径是 `data/app.db`。如需改到其他位置：

```bash
export LEETCOACH_DB_PATH=/path/to/leetcoach.db
```

## 启动

启动后端：

```bash
backend/.venv/bin/uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

另开一个终端启动前端：

```bash
npm run dev -- --port 5173
```

浏览器打开：

```text
http://127.0.0.1:5173
```

后端健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

## 基本使用流程

1. 在左侧题单里选择一道题。
2. 在编辑器里编写或修改 Python 解法。
3. 在底部测试区填写自定义输入。
4. 点击 `运行`，只执行当前自定义用例。
5. 点击 `提交`，执行该题保存的完整测试集。
6. 打开 `记录`，查看历史提交和失败信息。
7. 解完或调试完后，在 `Notes` 面板保存复习笔记。

`运行` 和 `提交` 的语义不同：

- `运行` 使用测试区里的自定义输入。
- `提交` 忽略自定义输入，使用题目保存的完整测试集。

## AI 教练

AI 是可选功能。不配置 API 凭据时，题库浏览、编辑器、本地判题、提交记录和笔记仍然可以正常使用。

配置 Anthropic：

```bash
export ANTHROPIC_API_KEY=...
export ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

也支持 auth token：

```bash
export ANTHROPIC_AUTH_TOKEN=...
```

如果使用 Anthropic 兼容网关：

```bash
export ANTHROPIC_BASE_URL=https://your-endpoint.example.com
```

AI 辅助增强测试：

```bash
cd backend
python -m app.ai_test_enhancer --task lru-cache --print-prompt
python -m app.ai_test_enhancer --task lru-cache --strength medium
python -m app.ai_test_enhancer --task lru-cache --strength medium --apply
```

AI 生成的测试会先经过校验再写入。题目会记录 `test_source` 和 `test_strength`，方便区分原始样例、弱测试和增强测试。

## 判题后端

默认使用本地 Python 判题：

```bash
export LEETCOACH_JUDGE_BACKEND=local
```

如果要接入 Judge0：

```bash
export LEETCOACH_JUDGE_BACKEND=judge0
export LEETCOACH_JUDGE0_ENDPOINT=http://127.0.0.1:2358
export LEETCOACH_JUDGE0_PYTHON_LANGUAGE_ID=71
```

如果 Judge0 需要认证：

```bash
export LEETCOACH_JUDGE0_AUTH_TOKEN=...
```

也兼容 `JUDGE0_ENDPOINT` 和 `JUDGE0_AUTH_TOKEN` 这两个环境变量名。

## CodeTop 元数据

同步 CodeTop 公开元数据：

```bash
backend/.venv/bin/python -m app.codetop --max-pages 1
```

去掉 `--max-pages` 可以做更完整的同步：

```bash
backend/.venv/bin/python -m app.codetop
```

默认会保存题目元数据、公司、部门、岗位、标签和频次信号。返回 `403` 的可选 taxonomy 接口会自动跳过。除非显式传入 `--include-content`，否则不会保存题面正文。

查看和导入 CodeTop 高频缺口：

```bash
cd backend
python -m app.codetop_gap --report --top 10
python -m app.codetop_gap --import-top 20 --dry-run
python -m app.codetop_gap --import-top 20
```

## 测试和检查

前端 lint：

```bash
npm run lint
```

前端构建：

```bash
npm run build
```

后端测试：

```bash
backend/.venv/bin/python -m pytest backend
```

## 本地文件

这些内容不会提交到 Git：

- `data/`
- `backend/.venv/`
- `node_modules/`
- `dist/`
- Python 缓存和 pytest 缓存
- TypeScript build info 文件
- `.env`

不要提交本地 SQLite 数据库、生成报告、私有凭据或临时开发草稿。

## 常用 API

- `GET /api/health`
- `GET /api/problems`
- `GET /api/problems/{task_id}`
- `PUT /api/problems/{task_id}/solution`
- `POST /api/runs`
- `POST /api/submissions`
- `GET /api/problems/{task_id}/submissions`
- `GET /api/practice/queue`
- `GET /api/practice/insights`
- `GET /api/topic-memories`
- `GET /api/problems/{task_id}/note`
- `PUT /api/problems/{task_id}/note`
- `POST /api/problems/{task_id}/note/draft`
