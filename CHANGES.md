# MaxKB 二次开发修改清单

> 基于 MaxKB v2.0.0，新增语义缓存、BM25混合检索、WebSocket索引进度、RAGAS评测面板四项功能。

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

## 二、语义缓存层

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

## 三、WebSocket 索引进度

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

## 四、RAGAS 评测面板

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

## 五、环境适配（Windows）

| 文件 | 修改内容 |
|------|----------|
| `apps/common/utils/tool_code.py:8-27` | `pwd`/`resource` 模块的 Windows 兼容桩（Unix 专有模块） |
| `ui/vite.config.ts:100-116,76-80` | SPA 路由回退中间件（`/admin/*`→`admin.html`）；移除 Vite 自循环代理规则；WebSocket 代理 |
| `ui/index.html` | 新建：根路径重定向到 admin.html |
| `.env` | 新建：`MAXKB_CONFIG_TYPE=ENV` + 数据库/Redis/Embedding 配置 |

### 额外编译
- **pgvector 0.7.2**：从 GitHub 下载源码，用 VS Build Tools 2022（MSVC）编译为 `vector.dll`，安装到 `D:\APP\PostgreSQL\lib\` 和 `share\extension\`

---

## 启动方式

```bash
# 终端 1：后端 API（端口 8080）
cd D:\落地项目\MaxKB-v2
C:\Users\forev\AppData\Local\Programs\Python\Python311\python.exe main.py dev web

# 终端 2：前端（端口 3000，热更新）
cd D:\落地项目\MaxKB-v2\ui
npm run dev
```

访问 `http://localhost:3000/admin`，账号 `admin` / `LaLaLa123%%%`
