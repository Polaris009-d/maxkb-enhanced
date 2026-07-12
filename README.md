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

---

## 快速启动

### 前置依赖

- PostgreSQL 17 + pgvector 扩展
- Redis 7
- Python 3.11
- Node.js 18+

### 启动命令（5 个终端）

```bash
# 终端 1：后端 API
cd D:\落地项目\MaxKB-v2
python main.py dev web

# 终端 2：Worker (异步任务)
cd D:\落地项目\MaxKB-v2\apps
python -m celery -A worker:app worker -l info -P solo --concurrency=1 -n worker1

# 终端 3：本地模型服务 (Embedding)
cd D:\落地项目\MaxKB-v2
python main.py dev local_model

# 终端 4：管理后台
cd D:\落地项目\MaxKB-v2\ui
npm run dev

# 终端 5：聊天界面
cd D:\落地项目\MaxKB-v2\ui
npm run chat
```

### 访问地址

- 管理后台：`http://localhost:3000/admin` 账号 `admin` / `LaLaLa123%%%`
- 聊天页面：`http://localhost:3001/chat/{access_token}`

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
| 后端框架 | Django 4.2 + DRF 3.17 |
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
