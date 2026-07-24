# MaxKB v2 — 企业级 RAG 知识库平台

基于 MaxKB v2.0.0 深度二次开发，全面增强 RAG 管线，补全生产级 PDF 处理、权限管控、检索优化、实时反馈能力。

---

## 架构总览

```
┌────────────────────────────────────────────────────────────┐
│                    前端 (Vue 3 + Vite)                      │
│         管理后台 :3000/admin    聊天界面 :3001/chat          │
│    WebSocket 实时进度 | ECharts 评测 | SSE 流式对话          │
└──────────────────────────┬─────────────────────────────────┘
                           │ HTTP + WebSocket
┌──────────────────────────▼─────────────────────────────────┐
│                 Django API Server (:8080)                    │
│  ┌──────────────────────────────────────────────────┐      │
│  │         RAG Pipeline (rag/)                        │      │
│  │  问题优化 → 缓存查询 → 混合检索 → Reranker → LLM   │      │
│  └──────────────────────────────────────────────────┘      │
│  ┌────────────────────┐  ┌──────────────────────────┐     │
│  │  Document Ingestion │  │  Multi-Strategy Retrieval │     │
│  │  (ingestion/)       │  │  (retrieval/)             │     │
│  │  Parse→OCR→Extract   │  │  Vector|Keyword|Hybrid    │     │
│  │  →Chunk→Embed       │  │  + Reranker              │     │
│  └────────────────────┘  └──────────────────────────┘     │
│  ┌────────────────────┐  ┌──────────────────────────┐     │
│  │  Event Bus          │  │  Domain Models            │     │
│  │  (events/)          │  │  (domain/)                │     │
│  │  publish/subscribe   │  │  Pure Python, no ORM      │     │
│  └────────────────────┘  └──────────────────────────┘     │
└──────┬───────────────┬──────────────┬──────────────────────┘
       │               │              │
┌──────▼──────┐ ┌──────▼──────┐ ┌─────▼──────────┐ ┌──────────┐
│ PostgreSQL   │ │   Redis     │ │  DeepSeek API   │ │ 本地模型  │
│ + pgvector   │ │  缓存/队列   │ │  (LLM 对话)    │ │ :11636  │
└──────┬──────┘ └──────┬──────┘ └────────────────┘ └────┬─────┘
       │               │                               │
┌──────▼───────────────▼───────────────────────────────▼─────┐
│                     Worker (Celery)                         │
│  文档解析 → 切片 → Embedding → 向量入库 → WS 推送进度       │
└────────────────────────────────────────────────────────────┘
```

---

## 分层架构

```
apps/
├── domain/          领域模型 (纯 Python dataclass)
│   ├── document.py      ParsedDocument, Chunk, DocumentStatus
│   ├── embedding.py     SearchQuery, SearchHit, EmbeddedChunk
│   └── conversation.py  Message, Question, Answer, ChatContext
│
├── events/          事件总线 (Django signal 驱动)
│   ├── event_types.py   7 种领域事件
│   ├── bus.py           EventBus.publish/subscribe
│   └── handlers.py      默认处理器
│
├── ingestion/       文档处理流水线
│   ├── parser/pdf.py          PDF 解析 (pypdf→pdfplumber→OCR)
│   ├── ocr/baidu.py           百度 OCR API
│   ├── extractor/table.py     PDF 表格提取
│   ├── chunker.py             智能分段
│   └── services/pipeline.py   流水线编排
│
├── retrieval/       多策略检索
│   ├── vector/pgvector.py     EmbeddingSearch/KeywordsSearch/BlendSearch/HybridSearch
│   ├── reranker.py            Cross-Encoder + embedding fallback
│   └── services/search_service.py  统一检索接口
│
├── rag/             RAG 管线
│   ├── pipeline.py            PipelineManage 编排器
│   └── services/chat_service.py  聊天服务
│
├── worker/          异步任务
│   ├── __init__.py            Celery app
│   ├── heartbeat.py           心跳检测
│   └── signal_handler.py      信号处理
│
├── knowledge/       知识库 (Document, Paragraph, Embedding 模型)
├── application/     智能体/应用 (Chat, Evaluation 模型)
├── common/          公共模块 (认证/中间件/缓存/工具)
└── maxkb/           Django 项目配置
```

---

## 核心功能

### RAG 全链路

```
用户问题
  │
  ├── ResetProblemStep      问题优化 (可选)
  ├── SearchDatasetStep     多策略检索
  │   ├── EmbeddingSearch   pgvector 余弦相似度
  │   ├── KeywordsSearch    PostgreSQL ts_rank 全文检索
  │   ├── BlendSearch       向量+关键词融合
  │   ├── HybridSearch      RRF 融合 (k=60)
  │   └── RerankerManager   Cross-Encoder 重排序 Top-20→Top-5
  ├── PermissionFilter      文档级权限过滤
  ├── GenerateHumanMessage  构建 Prompt
  ├── SemanticCacheManager  Redis 语义缓存 (cos≥0.92)
  └── ChatStep              LLM 流式生成 (DeepSeek)
```

### 文档处理流水线

```
PDF 上传
  │
  ├── pypdf 提取文本
  ├── _has_cjk_encoding_issues()  检测 CJK 编码问题 → pdfplumber 回退
  ├── is_ocr_needed()             检测扫描件 → 百度 OCR 回退
  ├── TableExtractor              PDF 表格→JSON 存入 meta
  ├── SplitModel.parse()          智能分段
  └── Celery → 本地模型 Embedding → pgvector 入库 → WebSocket 推送
```

### 检索策略对比

| 模式 | 技术 | 精度 | 适用场景 |
|------|------|------|----------|
| `embedding` | pgvector 余弦相似度 | 语义匹配 | 自然语言问答 |
| `keywords` | ts_rank 全文检索 | 精确匹配 | 条款编号/产品型号 |
| `blend` | 向量+关键词直接加和 | 兼顾 | 通用 |
| `hybrid` | RRF 融合 | 最优 | 生产推荐 |

### 评测体系

> 环境：Windows 11, Python 3.11, PostgreSQL 17+pgvector, Redis 7, text2vec-base-chinese (CPU 推理)
> 知识库：太原理工大学学生手册（132 段落，1528 条向量）
> 测试集：50 条分层问题（easy:20 / medium:15 / hard:10 / adversarial:5），Bootstrap CI=95%, n=1000

#### 离线 Benchmark（`benchmark/run_benchmark_win.py`）

##### 1. 多策略检索对比

| 指标 | embedding | keywords | blend | hybrid |
|------|:---------:|:--------:|:-----:|:------:|
| **Recall@3** | 0.960 | 0.800 | 0.920 | 0.940 |
| **Recall@5** | **1.000** | 0.800 | 0.940 | 0.960 |
| **Recall@10** | **1.000** | 0.800 | 0.960 | **1.000** |
| **NDCG@5** | **0.963** | 0.777 | 0.928 | 0.948 |
| **MRR** | **0.956** | 0.770 | 0.928 | 0.951 |
| **平均延迟** | **80ms** | 112ms | 81ms | 104ms |

`embedding` 模式以 100% Recall@5 和 80ms 平均延迟双项最优；`keywords` 独立检索最弱（80% Recall@5），应与向量检索融合使用。

##### 2. 检索延迟分布

| 模式 | P50 | P95 | P99 | 平均 |
|------|:---:|:---:|:---:|:---:|
| embedding | 78.3ms | 102.1ms | 116.5ms | 79.7ms |
| keywords | 99.8ms | 199.1ms | 254.9ms | 111.5ms |
| blend | 82.2ms | 108.0ms | 132.4ms | 81.1ms |
| hybrid | 98.7ms | 163.3ms | 228.8ms | 103.9ms |

`keywords` 和 `hybrid` 的 P99 延迟显著偏高，源于 PostgreSQL ts_rank 全文检索在大结果集上的计算开销。

##### 3. Reranker A/B 对比（Cross-Encoder）

| 配置 | NDCG@5 | 95% CI |
|------|:------:|:------:|
| 不使用 Reranker | **0.975** | [0.925, 1.000] |
| 使用 Reranker (bge-reranker-v2-m3) | 0.944 | [0.858, 1.000] |

在 recall 已达上限的数据集上，Reranker 未能带来增益（-3.2%）。Reranker 更适合检索结果噪音大、需要二次精排的场景。

##### 4. 语义缓存命中率与延迟

| 阶段 | 命中率 | 平均延迟 | P50 | P95 | P99 |
|------|:-----:|:-------:|:---:|:---:|:---:|
| **冷启动** (1st pass) | 0.0% | 95.6ms | 94.6ms | 137.3ms | 164.0ms |
| **热启动** (2nd pass) | **100.0%** | 133.8ms | 135.7ms | 165.9ms | 170.3ms |

热启动可避免 **100%** 的 LLM 调用（50/50 查询走缓存）。热启动延迟略高于冷启动（+40%），原因是语义缓存需对每条查询计算 embedding（CPU）并与缓存向量比对余弦相似度。

##### 5. 融合策略增益

| 对比 | R@5 增益 |
|------|:-------:|
| Blend vs Keywords | **+17.5%** |
| Hybrid vs Embedding | -4.0% |

`blend` 相比纯关键词检索提升显著。`hybrid`（RRF）在召回已达 100% 时对比纯 embedding 无提升空间，但在召回不满的场景下通常表现更好。

运行命令：

```bash
cd D:\落地项目\MaxKB-v2
.venv\Scripts\python.exe benchmark\run_benchmark_win.py
```

#### 在线评测（`application/task/evaluation.py`）

基于 RAGAS 框架，通过 Celery 定时任务自动评估生产对话质量：

| 指标 | 方法 | 评估对象 |
|------|------|----------|
| Faithfulness | LLM-as-judge | 答案是否忠实于检索上下文 |
| Answer Relevancy | Embedding 余弦相似度 | 答案是否切题 |
| Context Recall | LLM-as-judge | 检索上下文是否覆盖回答所需信息 |

每日自动评估最近 24 小时对话记录（最多 50 条），结果存入 `evaluation_result` 表。

#### 评测样本挖掘（`benchmark/mine_eval_samples.py`）

从历史 ChatRecord 中自动提取评测样本：

```bash
# 从生产对话挖掘评测样本
python benchmark/mine_eval_samples.py --limit 200 --output eval_dataset.json
```

- 优先采集用户点赞（thumbs up）的高质量记录
- 自动提取关键词（jieba TF-IDF）、估算难度、分类别
- 输出 JSON 可直接补充到 Benchmark 测试集中

---

## 快速启动

### 前置依赖

- PostgreSQL 17 + pgvector 扩展
- Redis 7
- Python 3.11
- Node.js 18+

### 快速安装依赖

```bash
# 安装 Python 依赖（需要 Python 3.11）
cd D:\落地项目\MaxKB-v2
uv sync --python 3.11

# 安装前端依赖
cd D:\落地项目\MaxKB-v2\ui
npm install
```

### 启动命令（5 个终端）

```bash
# 终端 1：后端 API
cd /d D:\落地项目\MaxKB-v2
.venv\Scripts\activate
python main.py dev web

# 终端 2：Worker (异步任务)
cd /d D:\落地项目\MaxKB-v2\apps
..\.venv\Scripts\python.exe -m celery -A worker:app worker -l info -P solo --concurrency=1 -n worker1

# 终端 3：本地模型服务 (Embedding)
cd /d D:\落地项目\MaxKB-v2
.venv\Scripts\activate
python main.py dev local_model

# 终端 4：管理后台
cd /d D:\落地项目\MaxKB-v2\ui
npm run dev

# 终端 5：聊天界面
cd /d D:\落地项目\MaxKB-v2\ui
npm run chat
```

### 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| Django API | `http://localhost:8080` | REST API（`/admin/api/...`） |
| 管理后台 | `http://localhost:3000/admin` | 登录账号 `admin` / `LaLaLa123%%%` |
| 聊天界面 | `http://localhost:3001/chat/{access_token}` | 通过应用发布获得 token |
| Embedding 模型 | `http://localhost:11636` | 本地向量化服务 |

---

## 环境变量 (.env)

```bash
MAXKB_CONFIG_TYPE=ENV
MAXKB_DB_NAME=maxkb
MAXKB_DB_HOST=127.0.0.1
MAXKB_DB_PORT=5432
MAXKB_DB_USER=root
MAXKB_DB_PASSWORD=123456
MAXKB_DB_ENGINE=dj_db_conn_pool.backends.postgresql
MAXKB_REDIS_HOST=127.0.0.1
MAXKB_REDIS_PORT=6379
MAXKB_REDIS_PASSWORD=
MAXKB_REDIS_DB=0
MAXKB_EMBEDDING_MODEL_PATH=D:/APP/models/embedding
MAXKB_EMBEDDING_MODEL_NAME=D:/APP/models/embedding/shibing624_text2vec-base-chinese
MAXKB_DEBUG=true
MAXKB_TIME_ZONE=Asia/Shanghai
MAXKB_BAIDU_OCR_API_KEY=***
MAXKB_BAIDU_OCR_SECRET_KEY=***
```





---

## 已知限制

| 限制 | 说明 |
|------|------|
| DeepSeek V4 Pro 推理泄漏 | reasoning 模式下可能在回答中暴露 prompt 模板 |
| 关键词检索阈值 | ts_rank_cd 分数与 cosine 不在同一量级，共用阈值需调低 |
| Windows 开发环境 | `pwd`/`resource` 模块需要兼容桩 |
| pgvector 扩展 | 需要手动编译 MSVC 版本安装到 PostgreSQL |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Django 5.2 + DRF 3.17 |
| 异步任务 | Celery 5 + Redis |
| 实时通信 | Django Channels 4 + WebSocket |
| 向量数据库 | PostgreSQL + pgvector (HNSW) |
| 全文检索 | PostgreSQL tsvector/tsquery + jieba |
| 缓存 | Redis (django-redis) |
| 前端 | Vue 3 + TypeScript + Vite + Pinia + Element Plus |
| LLM | DeepSeek V4 Pro (API) |
| Embedding | shibing624/text2vec-base-chinese (本地 768d) |
| OCR | 百度 OCR API |
| PDF | pypdf + pdfplumber |

---

## 许可

基于 MaxKB 开源项目二次开发，遵循原项目许可协议。
