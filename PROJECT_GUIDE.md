# 企业智能知识库平台 — 基于 MaxKB 深度二次开发

## 一、项目背景

MaxKB 是 GitHub 上 12k+ star 的开源知识库问答平台，功能完整但存在三个工程痛点：

- **大模型调用成本高**：用户每次提问都调 LLM，重复问题也不例外
- **检索召回率不足**：纯向量检索对精确关键词（如产品型号、条款编号）不敏感
- **异步处理反馈弱**：文档索引进度靠前端 6 秒轮询，体验割裂

我基于 MaxKB v2.0.0 做了**架构重构 + RAG 增强 + 生产就绪**三维改造。独立设计并实现了语义缓存、BM25 混合检索、Reranker 重排序、WebSocket 实时进度、RAGAS 评测面板、百度 OCR、文档权限过滤、PDF 表格提取、模型自动重 embedding、版本管理、**事件总线**、**领域模型层**等模块。新增 20+ 文件，修改 16 文件，约 2500 行新代码。修复启动阻塞 Bug 20+ 项，重构应用分层架构。

> 一句话：保留原项目多租户和知识库管理，全面重构为分层可扩展架构，增强 RAG 管线，补全生产级 PDF 处理和实时反馈。

---

## 二、系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                    前端 (Vue 3 + Vite)                         │
│         管理后台 :3000/admin    聊天界面 :3001/chat             │
│    WebSocket 实时进度 | ECharts 评测面板 | SSE 流式对话         │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP + WebSocket
┌──────────────────────────▼───────────────────────────────────┐
│                  Django API Server (:8080)                     │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           RAG Pipeline (rag/)                          │    │
│  │  问题优化 → 缓存查询 → 混合检索 → Reranker → LLM生成  │    │
│  │     │           │          │          │         │       │    │
│  │     │     Redis缓存   BM25+Dense  Cross-Encoder DeepSeek│    │
│  │     │     cos≥0.92    +RRF融合    重排序    Stream    │    │
│  └──────────────────────────────────────────────────────┘    │
│  ┌──────────────────┐  ┌──────────────────────────────┐     │
│  │ Document Pipeline │  │  Multi-Strategy Retrieval    │     │
│  │ (ingestion/)      │  │  (retrieval/)                │     │
│  │ Parse→OCR→Chunk    │  │  Vector|Keyword|Hybrid|Blend │     │
│  └──────────────────┘  └──────────────────────────────┘     │
│  ┌──────────────────┐  ┌──────────────────────────────┐     │
│  │ Event Bus         │  │  Domain Models                │     │
│  │ (events/)         │  │  (domain/) 纯Python,无ORM依赖  │     │
│  └──────────────────┘  └──────────────────────────────┘     │
└──────┬──────────────────┬──────────────────┬─────────────────┘
       │                  │                  │
┌──────▼──────┐  ┌────────▼──────┐  ┌───────▼─────────┐  ┌──────────────┐
│ PostgreSQL   │  │    Redis      │  │   DeepSeek API   │  │ 本地模型服务   │
│ + pgvector   │  │  缓存+队列     │  │   (LLM 对话)     │  │ :11636       │
│ 文档/段落/向量│  │  WS Channel   │  │                  │  │ Embedding推理 │
└──────┬──────┘  └────────┬──────┘  └─────────────────┘  └──────┬───────┘
       │                  │                                     │
┌──────▼──────────────────▼─────────────────────────────────────▼──────┐
│                       Worker (Celery)                                  │
│  文档解析 → 切片 → 调用本地模型 Embedding → 向量入库 → WS推送进度     │
└──────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────┐
│       RAGAS 评测 (定时)         │
│  Faithfulness + AnswerRelevancy │
│  → ECharts 趋势面板             │
└────────────────────────────────┘
```

### 分层架构

```
apps/
├── domain/          领域模型 (纯Python dataclass, 零ORM依赖)
│   ├── document.py      ParsedDocument, Chunk, DocumentStatus
│   ├── embedding.py     SearchQuery, SearchHit, EmbeddedChunk
│   └── conversation.py  Message, Question, Answer, ChatContext
│
├── events/          事件总线 (Django signal驱动)
│   ├── event_types.py   7种领域事件
│   ├── bus.py           EventBus.publish/subscribe
│   └── handlers.py      默认处理器
│
├── ingestion/       文档处理流水线 ★
│   ├── parser/pdf.py          PDF解析 (pypdf→pdfplumber→OCR三级回退)
│   ├── ocr/baidu.py           百度OCR API
│   ├── extractor/table.py     PDF表格结构化提取
│   ├── chunker.py             智能分段
│   └── services/pipeline.py   流水线编排服务
│
├── retrieval/       多策略检索 ★
│   ├── vector/pgvector.py     4种搜索策略 (Strategy模式)
│   ├── reranker.py            Cross-Encoder重排序
│   └── services/search_service.py  统一检索接口
│
├── rag/             RAG管线 ★
│   ├── pipeline.py            四步Pipeline编排器
│   └── services/chat_service.py  聊天服务封装
│
├── worker/          异步任务 (替代 ops/celery/)
│   ├── __init__.py            Celery app配置
│   ├── heartbeat.py           跨平台心跳检测
│   └── signal_handler.py      信号处理
│
├── knowledge/       知识库 (Document, Paragraph, Embedding模型)
├── application/     智能体 (Application, Chat, Evaluation模型)
├── common/          公共模块 (认证/中间件/缓存/WebSocket/语义缓存)
└── maxkb/           Django项目配置
```

---

## 三、我具体做了什么

### 1. 架构重构 — 从单体到分层

原始 MaxKB 所有代码混在 `common/` 和 `application/` 中。我按 DDD 思想拆分为 7 个独立 app：

| 新 app | 职责 | 来源 |
|--------|------|------|
| `ingestion/` | 文档解析→OCR→表格→分段 | 从 `common/handle/` + `common/utils/` 抽出 |
| `retrieval/` | 向量/关键词/混合检索 + Reranker | 从 `knowledge/vector/` + `common/reranker/` 抽出 |
| `rag/` | RAG 管线编排 | 从 `application/chat_pipeline/` 抽出 |
| `worker/` | 异步任务 | 从 `ops/celery/` 重命名 |
| `domain/` | 纯 Python 领域模型 | 新建，零 ORM 依赖 |
| `events/` | 事件总线 | 新建，Django signal 驱动 |

### 2. RAG 全链路（自研 Chat Pipeline）

原始 MaxKB 只用 LangChain 默认链，我重构成了四步 Pipeline：

```
问题优化 → 检索 → Reranker → LLM 生成
```

每一步可独立配置、替换模型。Pipeline 通过 `PipelineManage.builder().append_step(...)` 链式组装。

**检索环节**支持 4 种策略可切换：`embedding`（pgvector 余弦相似度）、`keywords`（ts_rank 全文检索）、`blend`（直接融合）、`hybrid`（RRF k=60 融合，生产推荐）。

**重排序环节**：Cross-Encoder（BAAI/bge-reranker-base）对 Top-20 候选逐对精排，不可用时自动回退 embedding 相似度排序。

> 一句话：自研四步 Pipeline，每步可替换，所有新增模块通过实现接口插入管线。

### 3. 语义缓存

不是简单的 key-value 缓存。流程是：

```
用户问题 → 计算 embedding（768维）→ Redis 查所有缓存条目
→ 逐条计算余弦相似度 → 找到 ≥0.92 的 → 直接返回，跳过 LLM
→ 没找到 → 正常调 LLM → 异步回写缓存
```

关键设计点：
- 按 application_id 做命名空间隔离
- 用 Redis Hash 存 answer + embedding + token 统计
- 24 小时 TTL 自动过期
- 缓存失败不阻塞主流程（try/except 兜底）

> 一句话：用 Redis 存问题 embedding，查余弦相似度≥0.92 直接返回不调 LLM，重复提问缓存命中率 100%。

### 4. BM25 混合检索 + RRF 融合

在原有 EmbeddingSearch / KeywordsSearch 基础上新增 HybridSearch：

```
EmbeddingSearch 返回 Top-20（稠密向量）
KeywordsSearch 返回 Top-20（稀疏 BM25）
    ↓
RRF 算法融合：score = 1/(60+rank_dense) + 1/(60+rank_sparse)
    ↓
按融合分重排，取 Top-5
```

放在 `search_handle_list` 策略注册表里，前端选 "hybrid" 模式即可切换。

> 一句话：用 RRF 算法把 dense 向量和 sparse BM25 两路结果融合，解决纯向量对精确关键词不敏感的问题。

### 5. Reranker 重排序

```
检索返回 Top-20 → Cross-Encoder (BAAI/bge-reranker-base) 重打分 → 取 Top-5 → 送 LLM
```

优先用 Cross-Encoder，不可用时回退 embedding 相似度重排，不影响主流程。

### 6. WebSocket 实时索引进度

原来是前端每 6 秒轮询一次状态接口。我改成：

```
Celery 任务 → Channel Layer (Redis) → WebSocket → 前端实时更新
```

- 后端：`apps/common/websocket/` 封装了 Consumer + Publisher
- ASGI 用 ProtocolTypeRouter 同时支持 HTTP 和 WebSocket
- 前端：`document/index.vue` 用 WebSocket 连接替代 setInterval，失败自动回退轮询
- 四阶段展示：解析 → 切片 → 嵌入 → 入库

### 7. RAGAS 评测面板

不依赖 ragas 包，自研实现：
- Faithfulness：LLM-as-judge，用应用模型打分
- AnswerRelevancy：问题与答案各句 embedding 的余弦相似度均值
- 支持 Celery 定时执行 + ECharts 趋势图 + 5 个 REST API

### 8. PDF 扫描件 OCR 识别 + CJK 编码修复

三级回退链：

```
PDF 页 → pypdf 提取文本 → CJK 编码检测（如 〔〕 丢失）→ pdfplumber 回退
       → 扫描件检测（内容 < 50 字符或图片占位符）→ 百度 OCR API → 结构化文本
```

> 一句话：扫描件 PDF 自动识别，CJK 特殊字符编码问题已修复。

### 9. PDF 表格结构化提取

```
PDF → pdfplumber.extract_tables() → [{headers, rows, data}] → 存入 paragraph.meta
```

检索到含表格段落时返回结构化表数据而非纯文本。已接入 `pdf_split_handle.py` 提取流程。

> 一句话：PDF 中的表格不再丢失，以结构化 JSON 形式存储和检索。

### 10. 文档权限过滤

在 Workspace 级隔离基础上，增加文档级 user_id 过滤：

```
搜索结果 → PermissionFilter.filter_paragraphs() → 过滤掉非授权文档 → 返回
admin: 全量 / 普通用户: 自己的文档 + 公共文档 / 匿名: 仅公共文档
```

已接入 `BaseSearchDatasetStep.execute()` 检索管线。

> 一句话：同一知识库下的多个用户只能看到被授权的文档。

### 11. 模型升级自动重 embedding

Django 双信号监听 Knowledge.embedding_model 变更：

```
用户改 embedding 模型 → pre_save 缓存旧值 → post_save 比对差异
→ 标记所有段落 PENDING → 自动触发 Celery 批量重向量化
```

修复了原始 `post_save` 重读数据库导致永远检测不到变更的 Bug。

> 一句话：换 embedding 模型后全库自动重新向量化，零人工介入。

### 12. PDF 版本管理

基于 Document.meta JSON 字段记录上传历史：

```
每次更新文档 → add_version() → meta.__versions__ 追加版本记录 → 保留最近 10 版
```

已接入文档新建（`save()`）和替换（`replace()`）两个入口。

> 一句话：文档更新保留版本历史，支持回溯审计。

### 13. 事件总线

```python
from events import EventBus, DocumentUploadedEvent

@EventBus.on(DocumentUploadedEvent)
def handle_upload(event):
    # 解耦后续处理逻辑
    pass
```

7 种事件覆盖完整文档生命周期：`DocumentUploaded` → `DocumentParsed` → `DocumentChunked` → `EmbeddingCompleted` → `IndexReady` + `ModelChanged` + `IngestionProgress`。基于 Django signal 实现，支持同步/异步处理。

### 14. 领域模型层

```python
from domain import ParsedDocument, Chunk, SearchQuery, ChatContext, Message
```

纯 Python dataclass，零 Django ORM 依赖。`domain/document.py`（文档生命周期状态机）、`domain/embedding.py`（检索模型）、`domain/conversation.py`（对话模型）。可在 Django Views、Celery Tasks、测试之间共享。

### 15. Windows 工程适配

| 适配项 | 方案 |
|--------|------|
| `pwd`/`resource` Unix 专属模块 | 条件导入 + stub 类 |
| Celery heartbeat 硬编码 Linux 路径 | `tempfile.gettempdir()` 跨平台方案 |
| pgvector 扩展 Windows 不可用 | VS Build Tools MSVC 编译 `vector.dll` |
| `main.py` 硬编码 `/opt/maxkb-app/...` | 基于 `BASE_DIR` 的动态路径 |
| `const.py` 默认配置路径 | `.env` + `MAXKB_CONFIG_TYPE=ENV` 环境变量模式 |
| `to_query()` tsquery 语法错误 | jieba 分词后过滤特殊字符 token |
| `filter_special_char` 误删合法 `#` | 正则从 `#+` 修正为 `(?m)^#{1,6}\s` |
| `dev()` elif 多服务无法并行 | 改为独立 `if` 分支 |
| Django 模型缺失导致迁移失败 | 补全 `__init__.py` 和模型注册 |

---

## 四、生产就绪对照

| 生产需求 | 状态 | 实现 | 文件 |
|----------|------|------|------|
| PDF解析差 | ✅ | pypdf→pdfplumber→OCR 三级回退 | `ingestion/parser/pdf.py` |
| 上传慢 | ✅ | Celery 异步任务队列 | `worker/` |
| 文档太大 | ✅ | RecursiveCharacterTextSplitter + 分页 | `ingestion/chunker.py` |
| 权限泄露 | ✅ | 文档级 user_id 权限过滤器 | `common/utils/permission_filter.py` |
| 模型升级 | ✅ | pre_save+post_save 双信号自动重 embedding | `knowledge/signals.py` |
| PDF更新 | ✅ | meta JSON 版本历史管理 | `knowledge/document_version.py` |
| 表格丢失 | ✅ | pdfplumber 提取结构化表格存入 meta | `ingestion/extractor/table.py` |
| 搜索效果差 | ✅ | HybridSearch(RRF) + Reranker(Cross-Encoder) | `retrieval/vector/pgvector.py` |
| 架构可维护 | ✅ | 分层架构 + 领域模型 + 事件总线 | `domain/` `events/` |

---

## 五、我具体做了什么

| 层级 | 工作 |
|------|------|
| **架构层** | 从单体 common/ 拆分为 ingestion/retrieval/rag/worker/domain/events 七独立 app |
| **Pipeline 层** | 在 ChatStep 嵌入缓存查询/回写逻辑；在 SearchStep 插入 Reranker + PermissionFilter |
| **检索层** | 新增 HybridSearch 策略类 + RRF 融合算法；注册到搜索策略表；统一 SearchService 接口 |
| **通信层** | 新增 WebSocket 消费者/发布者；重写 ASGI 配置；前端替换轮询 |
| **评测层** | 新增 EvaluationConfig/Result 两个 Django Model + 6 个 API + Celery 评测任务 + ECharts 面板 |
| **领域层** | domain/ 纯 Python dataclass（文档/检索/对话模型）；events/ 事件总线（7 种事件 + EventBus 发布订阅） |
| **通用层** | 语义缓存管理类（余弦相似度、Redis 存取、失效策略）；Reranker 工具类 |
| **服务层** | ingestion/retrieval/rag 三级 service 封装（pipeline/search/chat 统一入口） |
| **适配层** | Windows 兼容（pwd/resource 模块桩、Celery heartbeat 路径修复、pgvector MSVC 编译）；20+ 启动 Bug 修复 |

---

## 六、Benchmark 评测说明

Benchmark 体现在三个层面：

**1. 代码层面**：`benchmark/run_benchmark.py` — 一个独立脚本，可以随时跑。定义 15 道测试题 + 关键词，遍历 4 种搜索模式，计算 Recall@10、MRR、平均延迟，输出对比表格和 JSON 文件。

**2. 数据层面**：运行结果在 README 里的 Benchmark 表格，15 道校园场景问题跑了 4 种搜索模式横向对比，embedding 和 hybrid 都是满分，keywords 0.933（15 道题命中 14 道）。证明当前小规模文档纯向量已够用，BM25 为关键词兜底，扩展后优势更明显。

**3. 工程意义**：体现你不是盲目加功能，而是量化验证改动效果——这恰好是 RAGAS 评测面板的设计思路："先评测，再优化，数据说话"。

---

## 七、检索策略对比表格解释

### 各列含义

- **Recall@10**：15 道题中，有多少道题在搜出来的前 10 条结果里找到了正确答案。1.000 = 100%，全部找到。
- **MRR（Mean Reciprocal Rank）**：第一个正确答案排在第几位的倒数。排第 1 名得 1.0 分，排第 5 名得 0.2 分，越接近 1 说明正确答案越靠前。1.000 = 全部排在第 1 名。
- **平均延迟**：单次搜索从发请求到拿到结果的时间。

### 四行结果解读

| 模式 | 解读 |
|------|------|
| **embedding（纯向量）** | 15 道题全对，延迟 151ms。当前 132 段的小规模文档纯向量就够用 |
| **keywords（关键词）** | recall 0.933，15 道题对 14 道。关键词检索对精确词匹配有效，但"校园卡怎么充值"这类需要语义理解的题较弱 |
| **blend（向量+关键词）** | 与 embedding 相同满分，关键词路补强了精确匹配 |
| **hybrid（RRF 融合）** | 满分，91ms。当前规模与 blend 无区别，但文档增大后精确关键词匹配优势显著 |

> 四个搜索模式横向对比说明，当前文档量较小时纯向量检索就够用了。新增的 hybrid 模式的核心价值在于扩展性——文档量上去之后，遇到精确关键词查询时，BM25 稀疏搜索 + RRF 融合能保证精确匹配不被余弦相似度淹没。

---

## 八、语义缓存实测数据

### 测试方法

1. 准备 15 道问题，分两轮跑
2. 第一轮（冷启动）：正常查缓存 → 未命中 → 写入缓存
3. 第二轮（热启动）：重复相同问题 → 全部命中

### 实测结果

| 指标 | 冷启动（首次提问） | 热启动（重复提问） |
|------|-------------------|-------------------|
| 缓存命中率 | 0% | **100%**（15/15 全部命中） |
| LLM API 调用 | 15 次 | **0 次**（全部走缓存） |
| 缓存查询延迟 | — | 50.3ms |

> 实测结论：重复提问场景下，LLM 调用降为 0，响应延迟从秒级降至 50ms 内。
