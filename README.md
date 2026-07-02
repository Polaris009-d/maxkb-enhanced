# MaxKB 二次开发修改清单

> 基于 MaxKB v2.0.0，新增语义缓存、BM25混合检索、Reranker重排序、WebSocket索引进度、RAGAS评测面板、Benchmark评测脚本等能力。共 15 个新文件，14 个修改文件，~1500 行代码。

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                    前端 (Vue 3 + Vite)                         │
│         管理后台 :3000/admin    聊天界面 :3000/chat             │
│    WebSocket 实时进度 | ECharts 评测面板 | SSE 流式对话         │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP + WebSocket
┌──────────────────────────▼───────────────────────────────────┐
│                  Django API Server (:8080)                     │
│  ┌──────────────────────────────────────────────────────┐    │
│  │               Chat Pipeline (RAG全链路)                │    │
│  │  问题优化 → 缓存查询 → 混合检索 → Reranker → LLM生成  │    │
│  │     │           │          │          │         │       │    │
│  │     │     Redis缓存   BM25+Dense  BGE-Cross    GPT     │    │
│  │     │     cos≥0.92    +RRF融合    Encoder    Stream    │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │               Agent Workflow (工作流引擎)              │    │
│  │  开始 → 知识检索 → 判断器 → AI对话 / 工具调用 / 回复  │    │
│  └──────────────────────────────────────────────────────┘    │
└──────┬──────────────────┬──────────────────┬─────────────────┘
       │                  │                  │
┌──────▼──────┐  ┌────────▼──────┐  ┌───────▼─────────┐
│ PostgreSQL   │  │    Redis      │  │   LLM APIs      │
│ + pgvector   │  │  缓存+队列     │  │ DeepSeek/OpenAI │
│ 文档/段落/向量│  │  WS Channel   │  │ 兼容接口        │
└──────┬──────┘  └────────┬──────┘  └─────────────────┘
       │                  │
┌──────▼──────────────────▼──────┐
│         Celery Worker           │
│  文档解析 → 切片 → Embedding    │
│  → 向量入库 → WebSocket推送进度 │
└────────────────────────────────┘
┌────────────────────────────────┐
│       RAGAS 评测 (定时)         │
│  Faithfulness + AnswerRelevancy │
│  → ECharts 趋势面板             │
└────────────────────────────────┘
```

---

## Benchmark 评测结果（实测）

> 测试环境：Windows 11 / Python 3.11 / PostgreSQL 17+pgvector / shibing624/text2vec-base-chinese (768d)
> 测试数据：太原理工大学学生手册（132段，1528条向量），15 道校园场景问答

### 检索策略对比

| 模式 | Recall@10 | MRR | 平均延迟 | 说明 |
|------|-----------|-----|---------|------|
| embedding (纯向量) | 1.000 | 1.000 | 151ms | 余弦相似度搜索 |
| keywords (关键词) | 0.000 | 0.000 | 94ms | ts_rank 分词索引未建 |
| blend (向量+关键词) | 1.000 | 1.000 | 90ms | 直接加和融合 |
| hybrid (RRF融合) | 1.000 | 1.000 | 91ms | **本次新增** RRF k=60 |

### 语义缓存实测

| 指标 | 冷启动（首次提问） | 热启动（重复提问） |
|------|-------------------|-------------------|
| 缓存命中率 | 0% | **100%**（15/15 全部命中） |
| LLM API 调用 | 15 次 | **0 次**（全部走缓存） |
| 缓存查询延迟 | — | 89.5ms |

> 实测结论：重复提问场景下，LLM 调用为 0，响应延迟从秒级降至 90ms 内。

### WebSocket 进度反馈

| 指标 | 原方式 | 改进后 |
|------|--------|--------|
| 进度更新方式 | 6s 前端轮询 | WebSocket 实时推送 |
| 反馈粒度 | 仅成功/失败 | 4 阶段：解析→切片→嵌入→入库 |
| 延迟感知 | 3-9s | <500ms |

---

---

## 项目文件结构

★ 标记为本次新增或修改的文件



---

---

## 项目文件结构

(*) 标记为本次新增或修改的文件

```
MaxKB-v2/
|-- .env                          (*) 开发环境配置
|-- main.py                       (*) 项目入口
|-- README.md                     (*) 本文件
|-- benchmark/                    (*) 新增：评测脚本
|   |-- run_benchmark.py
|-- apps/                         # Django 后端
|   |-- config.yml
|   |-- manage.py
|   |-- common/                   # 公共模块
|   |   |-- semantic_cache/       (*) 语义缓存
|   |   |   |-- cache_manager.py
|   |   |-- reranker/             (*) Reranker 重排序
|   |   |   |-- reranker.py
|   |   |-- websocket/            (*) WebSocket 进度
|   |   |   |-- consumers.py
|   |   |   |-- routing.py
|   |   |   |-- progress_publisher.py
|   |   |-- event/
|   |   |   |-- listener_manage.py (*) 嵌入进度推送
|   |   |-- utils/
|   |       |-- tool_code.py      (*) Windows 兼容修复
|   |-- maxkb/                    # Django 项目配置
|   |   |-- asgi.py               (*) Channels WebSocket
|   |   |-- settings/             (*) Channels 配置
|   |   |-- urls/
|   |-- application/              # 应用/智能体
|   |   |-- chat_pipeline/        # RAG 管线
|   |   |   |-- step/
|   |   |       |-- search_dataset_step/ (*) Reranker 集成
|   |   |       |-- chat_step/         (*) 语义缓存集成
|   |   |-- models/
|   |   |   |-- evaluation.py     (*) RAGAS 评测模型
|   |   |-- serializers/
|   |   |   |-- application.py    (*) 自动绑定 LLM
|   |   |   |-- evaluation.py     (*) RAGAS 评测
|   |   |-- views/
|   |   |   |-- evaluation.py     (*) 评测 API
|   |   |-- task/
|   |   |   |-- evaluation.py     (*) 评测 Celery 任务
|   |   |-- urls.py               (*) 评测路由
|   |-- knowledge/                # 知识库
|   |   |-- models/
|   |   |   |-- knowledge.py      (*) hybrid 搜索模式
|   |   |-- vector/
|   |   |   |-- pg_vector.py      (*) HybridSearch 类
|   |   |-- sql/                  # 搜索 SQL
|   |-- chat/                     # 聊天接口
|   |-- models_provider/          # 模型供应商
|   |-- tools/                    # 工具库
|   |-- ops/                      # Celery
|   |   |-- celery/
|   |       |-- heartbeat.py      (*) Windows 兼容
|   |-- users/                    # 用户管理
|-- ui/                           # Vue 3 前端
|   |-- vite.config.ts            (*) SPA 路由 + WS 代理
|   |-- chat.html                 # 聊天入口
|   |-- admin.html                # 管理后台入口
|   |-- index.html                (*) 根路由重定向
|   |-- env/                      # 环境变量
|   |-- src/
|       |-- api/application/
|       |   |-- evaluation.ts     (*) 评测 API 客户端
|       |-- views/
|       |   |-- application/
|       |   |   |-- ApplicationSetting.vue (*) AI 生成+自动模型
|       |   |   |-- component/GeneratePromptDialog.vue
|       |   |-- application-overview/ (*) 对话端口修正
|       |   |-- application-workflow/ (*) 对话端口修正
|       |   |-- application-evaluation/ (*) 评测面板
|       |   |-- document/
|       |       |-- index.vue     (*) WebSocket 替换轮询
|       |-- stores/modules/
|       |   |-- application.ts    (*) 对话端口修正
|       |-- router/modules/
|       |   |-- application-detail.ts (*) 评测路由
|       |-- request/              # HTTP 客户端
|       |-- components/           # 全局组件
|-- installer/                    # Docker 部署文件
```

---

## 一、BM25 混合检索（RRF 融合）

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `apps/knowledge/models/knowledge.py:316` | `SearchMode` 枚举新增 `hybrid = "hybrid"` |
| `apps/knowledge/vector/pg_vector.py:349-415` | 新增 `HybridSearch(ISearch)` 类，RRF k=60 融合稠密+稀疏搜索结果，追加到 `search_handle_list` |

### 原理
同时运行 EmbeddingSearch（余弦距离）和 KeywordsSearch（PostgreSQL ts_rank），用 RRF 算法融合双路结果排序。解决纯向量检索对精确关键词不敏感的问题。

---

## 二、Reranker 重排序

### 新增文件

| 文件 | 说明 |
|------|------|
| `apps/common/reranker/__init__.py` | 包标记 |
| `apps/common/reranker/reranker.py` | `RerankerManager`：Cross-Encoder（BAAI/bge-reranker-base）精排 + embedding 相似度回退 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `apps/application/chat_pipeline/step/search_dataset_step/impl/base_search_dataset_step.py:78,85-138` | 检索后插入 `_apply_reranker()`，取 Top-20 → Cross-Encoder 重打分 → 返回 Top-5 |

### 原理
检索阶段返回 Top-20 候选段落，用 Cross-Encoder 模型对每个 (query, paragraph) 对做精细语义打分，重排后取 Top-5 送入 LLM。Cross-Encoder 比双塔 Embedding 的余弦相似度更精准。若模型不可用则回退到 embedding 相似度排序。

```
检索 Top-20 → Cross-Encoder 重打分 → 取 Top-5 → LLM 生成
```

---

## 三、语义缓存层

### 新增文件

| 文件 | 说明 |
|------|------|
| `apps/common/semantic_cache/__init__.py` | 包标记 |
| `apps/common/semantic_cache/cache_manager.py` | 核心类 `SemanticCacheManager`：`search()` 查询缓存、`cache()` 写入缓存、`invalidate()` 清空缓存、`cosine_similarity()` 余弦相似度计算 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `apps/application/chat_pipeline/step/search_dataset_step/impl/base_search_dataset_step.py:68` | 将 embedding_model 存入 `manage.context['_embedding_model']` |
| `apps/application/chat_pipeline/step/chat_step/impl/base_chat_step.py:1,552-566,186-208` | 导入 SemanticCacheManager；LLM调用前插入缓存查询；流输出完成后回写缓存 |

### 原理
在 ChatStep 的 LLM 调用前，用问题 embedding 在 Redis 中搜索余弦相似度 ≥0.92 的缓存答案。命中直接返回，未命中则调用 LLM 后将结果缓存。目标：LLM API 调用量降低约 40%，QPS 提升 3 倍。

### Redis 数据结构
```
semantic_cache:{app_id}:{md5_hash}  → Hash {embedding, answer_text, message_tokens, answer_tokens, problem_text}
semantic_cache:index:{app_id}       → Set of hash_ids
TTL: 86400s (24小时)
```

---

## 四、WebSocket 索引进度

### 新增依赖
```
channels==4.3.2, channels-redis==4.3.0, msgpack==1.2.1
```

### 新增文件

| 文件 | 说明 |
|------|------|
| `apps/common/websocket/__init__.py` | 包标记 |
| `apps/common/websocket/consumers.py` | `DocumentProgressConsumer`：加入 `document_progress_{id}` group，转发进度到 WebSocket 客户端 |
| `apps/common/websocket/routing.py` | WS URL 路由：`ws/document/<id>/progress/` |
| `apps/common/websocket/progress_publisher.py` | `IndexProgressPublisher.publish_progress()` 通过 Channel Layer 发布进度消息 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `apps/maxkb/asgi.py` | 重写为 `ProtocolTypeRouter`（HTTP + WebSocket），添加 Windows asyncio 兼容 |
| `apps/maxkb/settings/base/web.py:30,133-148` | INSTALLED_APPS 添加 `channels`；新增 `CHANNEL_LAYERS`（Redis 后端）和 `ASGI_APPLICATION` 配置 |
| `apps/common/event/listener_manage.py:43,381,411,122-152` | 导入 `IndexProgressPublisher`；在 `embedding_by_document()` 和 `embedding_by_paragraph_data_list()` 中插入进度推送 |
| `ui/vite.config.ts:38-48` | 代理规则添加 `ws: true`，新增 `/ws` 代理 |
| `ui/src/views/document/index.vue:917,1033,1179-1215` | 导入 `socket`；新增 `initWsConnection()` 连接 WebSocket，失败回退轮询 |

### 原理
用 Django Channels（Redis 后端）替换前端 6 秒轮询。Celery 任务在文档索引的 解析→切片→嵌入→入库 四阶段实时推送 WebSocket 消息，前端即时更新进度。

---

## 五、RAGAS 评测面板

### 新增文件

| 文件 | 说明 |
|------|------|
| `apps/application/models/evaluation.py` | `EvaluationConfig`（评测配置）和 `EvaluationResult`（评测结果）两个 Django Model |
| `apps/application/serializers/evaluation.py` | DRF 序列化器：配置 CRUD、结果列表、统计聚合 |
| `apps/application/views/evaluation.py` | 5 个 API View：配置 CRUD、手动触发、结果分页查询、统计仪表盘 |
| `apps/application/task/evaluation.py` | Celery 任务 `run_evaluation()`：LLM-as-judge 计算 Faithfulness + embedding 相似度计算 AnswerRelevancy |
| `ui/src/api/application/evaluation.ts` | 前端 API 客户端 |
| `ui/src/views/application-evaluation/index.vue` | 评测面板主页：统计卡片 + ECharts 趋势图 + 配置/结果表格 |
| `ui/src/views/application-evaluation/component/EvaluationFormDialog.vue` | 配置创建/编辑对话框 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `apps/application/urls.py:47-52` | 添加 5 条评测 API 路由 |
| `apps/application/views/__init__.py:17` | 导入 evaluation 视图 |
| `ui/src/router/modules/application-detail.ts:245-257` | 添加 `/evaluation` 子路由 |

### 原理
自实现轻量级 RAGAS（不依赖 ragas 包）：
- **Faithfulness**：LLM-as-judge，判断答案是否忠于上下文，输出 0-1 分数
- **AnswerRelevancy**：问题 embedding 与答案各句 embedding 的余弦相似度均值

支持手动触发或 CRON 定时执行，结果用 ECharts 折线图展示趋势。

### API 端点
```
GET    /admin/api/workspace/{wid}/application/{aid}/evaluation/config     # 配置列表
POST   /admin/api/workspace/{wid}/application/{aid}/evaluation/config     # 创建配置
PUT    /admin/api/workspace/{wid}/application/{aid}/evaluation/config/{cid}  # 更新配置
DELETE /admin/api/workspace/{wid}/application/{aid}/evaluation/config/{cid}  # 删除配置
POST   /admin/api/workspace/{wid}/application/{aid}/evaluation/config/{cid}/trigger  # 手动触发
GET    /admin/api/workspace/{wid}/application/{aid}/evaluation/result      # 查询结果
GET    /admin/api/workspace/{wid}/application/{aid}/evaluation/stats       # 统计仪表盘
```

---

---

## 六、Benchmark 评测脚本

### 新增文件

| 文件 | 说明 |
|------|------|
| `benchmark/__init__.py` | 包标记 |
| `benchmark/run_benchmark.py` | 完整 RAG 评测脚本：Recall@10 / MRR / 延迟 / 缓存命中率 / 搜索模式对比 |

### 运行方式
```bash
cd D:\落地项目\MaxKB-v2\apps
python ../benchmark/run_benchmark.py
```

### 评测维度
- **Recall@10**：Top-10 结果中包含相关段落的查询比例
- **MRR**：第一个相关结果排名的倒数均值
- **搜索延迟**：向量检索 + Reranker 的端到端耗时
- **缓存命中率**：语义缓存的首次和二次命中统计
- **模式对比**：embedding vs keywords vs blend vs hybrid 四模式横向对比

### 输出
- 终端打印所有指标的详细对比表格
- 生成 `benchmark/benchmark_results.json` 供 CI 集成

---

## 七、环境适配（Windows）

| 文件 | 修改内容 |
|------|----------|
| `apps/common/utils/tool_code.py:8-27` | `pwd`/`resource` 模块的 Windows 兼容桩（Unix 专有模块） |
| `ui/vite.config.ts:100-116,76-80` | SPA 路由回退中间件（`/admin/*`→`admin.html`）；移除 Vite 自循环代理规则；WebSocket 代理 |
| `ui/index.html` | 新建：根路径重定向到 admin.html |
| `.env` | 新建：`MAXKB_CONFIG_TYPE=ENV` + 数据库/Redis/Embedding 配置 |
| `apps/ops/celery/heartbeat.py` | 修复 Windows 路径兼容（硬编码 Linux 路径 → `tempfile.gettempdir()`） |

### 额外编译
- **pgvector 0.7.2**：从 GitHub 下载源码，用 VS Build Tools 2022（MSVC）编译为 `vector.dll`，安装到 `D:\APP\PostgreSQL\lib\` 和 `share\extension\`

---

## 文件统计

| 类别 | 数量 |
|------|------|
| 新增文件 | 15 |
| 修改文件 | 14 |
| 新增代码行 | ~1500 |

---

## 启动方式

**必须同时启动 5 个终端**：

```bash
# 终端 1：后端 API（端口 8080）
cd D:\落地项目\MaxKB-v2
C:\Users\forev\AppData\Local\Programs\Python\Python311\python.exe main.py dev web

# 终端 2：Celery 异步任务（文档向量化）
cd D:\落地项目\MaxKB-v2\apps
C:\Users\forev\AppData\Local\Programs\Python\Python311\python.exe -m celery -A ops.celery:app worker -l info -P solo --concurrency=1 -n worker1

# 终端 3：本地模型服务（端口 11636，提供 Embedding）
cd D:\落地项目\MaxKB-v2
C:\Users\forev\AppData\Local\Programs\Python\Python311\python.exe main.py dev local_model

# 终端 4：管理后台前端（端口 3000，热更新）
cd D:\落地项目\MaxKB-v2\ui
npm run dev

# 终端 5：聊天界面前端（端口 3001，热更新）
cd D:\落地项目\MaxKB-v2\ui
npm run chat
```

> **重要**：
> - 如果文档索引一直"排队中"，检查终端 2（Celery）和终端 3（本地模型）是否都在运行
> - 终端 5 是聊天对话的入口，端口 3001，不启动则无法打开聊天页面

- 管理后台：`http://localhost:3000/admin`，账号 `admin` / `LaLaLa123%%%`
- 聊天页面：`http://localhost:3001/chat/{access_token}`
