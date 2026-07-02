#!/usr/bin/env python
# coding=utf-8
"""MaxKB RAG Benchmark — recall, latency, and cache hit rate."""
import json, os, sys, time, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maxkb.settings")
os.environ["MAXKB_CONFIG_TYPE"] = "ENV"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
logging.disable(logging.CRITICAL)

import django; django.setup()
from knowledge.models import Knowledge, Paragraph, SearchMode
from models_provider.tools import get_model_by_id, get_model_default_params, get_model
from common.config.embedding_config import VectorStore, ModelManage
from common.semantic_cache.cache_manager import SemanticCacheManager

BENCHMARK_APP = "benchmark_test"

QUESTIONS = [
    ("奖学金如何申请", ["奖学金","申请","评审","助学金"]),
    ("违纪处分有哪些类型", ["处分","警告","记过","留校察看"]),
    ("论文抄袭后果", ["论文","抄袭","学位","学术"]),
    ("助学金申请条件", ["助学金","困难","家庭","经济"]),
    ("宿舍管理规定", ["宿舍","住宿","管理","安全"]),
    ("休学手续怎么办", ["休学","手续","学籍","办理"]),
    ("考试作弊怎么处理", ["作弊","处分","违纪","考试"]),
    ("勤工助学怎么申请", ["勤工助学","岗位","申请"]),
    ("学生证丢了怎么办", ["学生证","补办","丢失","挂失"]),
    ("转专业有什么条件", ["转专业","条件","申请"]),
    ("国家奖学金评选标准", ["国家","奖学金","评选","成绩"]),
    ("毕业论文有什么要求", ["毕业","论文","答辩","学分"]),
    ("学费减免怎么办理", ["学费","减免","困难","申请"]),
    ("校园卡怎么充值", ["一卡通","充值","校园卡","食堂"]),
    ("学位论文作假处理办法", ["学位","论文","作假","学术不端"]),
]

def recall_at_10(results, keywords):
    for r in (results or [])[:10]:
        if any(kw in (r.get("content","")) for kw in keywords):
            return 1
    return 0

def mrr(results, keywords):
    for i, r in enumerate(results or []):
        if any(kw in (r.get("content","")) for kw in keywords):
            return 1.0/(i+1)
    return 0.0

# Setup embedding model
kb = Knowledge.objects.first()
mid = kb.embedding_model_id
model = get_model_by_id(mid, "default")
dp = get_model_default_params(model)
emb = ModelManage.get_model(mid, lambda _id: get_model(model, **{**dp}))
vec = VectorStore.get_embedding_vector()
kids = [str(kb.id)]

print(f"KB: {kb.name} | Model: {str(mid)[:8]}... | Queries: {len(QUESTIONS)}")
print()

# ==== PART 1: Search mode comparison ====
print("=== 1. Search Mode Comparison ===")
results = {}
for mode in ["embedding", "keywords", "blend", "hybrid"]:
    recall_vals, mrr_vals, times = [], [], []
    for q, kws in QUESTIONS:
        t0 = time.time()
        hits = vec.query(q, emb.embed_query(q), kids, None,None,None, True, 10, 0.3, SearchMode(mode))
        dt = (time.time()-t0)*1000
        if hits:
            pids = [h["paragraph_id"] for h in hits[:10] if h.get("paragraph_id")]
            pmap = {p["id"]: p.get("content","") for p in Paragraph.objects.filter(id__in=pids).values("id","content")}
            for h in hits: h["content"] = pmap.get(h.get("paragraph_id"),"")
        recall_vals.append(recall_at_10(hits, kws))
        mrr_vals.append(mrr(hits, kws))
        times.append(dt)
    n = len(recall_vals)
    results[mode] = {"recall@10": round(sum(recall_vals)/n,3), "mrr": round(sum(mrr_vals)/n,3), "avg_ms": round(sum(times)/n,1)}
    print(f"  {mode:<12} recall@10={results[mode]['recall@10']:.3f}  mrr={results[mode]['mrr']:.3f}  avg={results[mode]['avg_ms']:.0f}ms")

hyb = results.get("hybrid",{})
emb_r = results.get("embedding",{})
if hyb and emb_r and emb_r["recall@10"] > 0:
    gain = (hyb["recall@10"]-emb_r["recall@10"])/emb_r["recall@10"]*100
    print(f"  Hybrid vs Embedding recall: {gain:+.0f}%")
print()

# ==== PART 2: Semantic Cache Test ====
print("=== 2. Semantic Cache Hit Rate ===")
SemanticCacheManager.invalidate(BENCHMARK_APP)
cache_hits_1st, cache_hits_2nd = 0, 0
cache_times = []

for round_num, desc in [(1, "Cold"), (2, "Warm")]:
    for q, _ in QUESTIONS:
        t0 = time.time()
        hit = SemanticCacheManager.search(q, BENCHMARK_APP, emb, 0.92)
        dt = (time.time()-t0)*1000
        if hit:
            if round_num == 1: cache_hits_1st += 1
            else: cache_hits_2nd += 1
        else:
            emb_vec = emb.embed_query(q)
            SemanticCacheManager.cache(q, f"Mock answer for: {q}", 100, 200, emb_vec, BENCHMARK_APP)
        cache_times.append(dt)

SemanticCacheManager.invalidate(BENCHMARK_APP)

total = len(QUESTIONS)
cold_rate = round(cache_hits_1st/total*100, 1)
warm_rate = round(cache_hits_2nd/total*100, 1)
avg_cache_ms = round(sum(cache_times)/len(cache_times), 1)
print(f"  Cold (1st pass): {cache_hits_1st}/{total} = {cold_rate}% hit")
print(f"  Warm (2nd pass): {cache_hits_2nd}/{total} = {warm_rate}% hit")
print(f"  LLM calls avoided (warm): {cache_hits_2nd}/{total} = {warm_rate}%")
print(f"  Avg cache lookup: {avg_cache_ms}ms")
print()

# ==== PART 3: Summary ====
print("=== 3. Summary ===")
best = max(results, key=lambda m: results[m]["recall@10"])
print(f"  Best search mode: {best} (recall@10={results[best]['recall@10']})")
print(f"  Cache: cold {cache_hits_1st}/{total} hits, warm {cache_hits_2nd}/{total} hits")
print(f"  LLM call reduction on repeat queries: {warm_rate}%")

out = {
    "kb": kb.name, "embedding_model": str(mid), "queries": len(QUESTIONS),
    "search_results": results,
    "cache": {"cold_hits": cache_hits_1st, "warm_hits": cache_hits_2nd, "total": total,
              "cold_rate": cold_rate, "warm_rate": warm_rate, "avg_lookup_ms": avg_cache_ms},
}
with open(os.path.join(os.path.dirname(__file__), "benchmark_results.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nSaved: benchmark_results.json")
