#!/usr/bin/env python
# coding=utf-8
"""MaxKB RAG Benchmark — quick recall/latency/cache comparison."""
import json, os, sys, time, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maxkb.settings")
os.environ["MAXKB_CONFIG_TYPE"] = "ENV"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
logging.disable(logging.CRITICAL)  # silence all DB logs

import django; django.setup()
import numpy as np
from knowledge.models import Knowledge, Paragraph, SearchMode
from models_provider.tools import get_model_by_id, get_model_default_params, get_model
from common.config.embedding_config import VectorStore, ModelManage

QUESTIONS = [
    ("奖学金如何申请", ["奖学金","申请","评审"]),
    ("违纪处分有哪些", ["处分","警告","记过"]),
    ("论文抄袭后果", ["论文","抄袭","学位"]),
    ("助学金申请条件", ["助学金","困难","家庭"]),
    ("宿舍管理规定", ["宿舍","住宿","管理"]),
    ("休学手续怎么办", ["休学","手续","学籍"]),
    ("考试作弊处理", ["作弊","处分","违纪"]),
    ("勤工助学怎么申请", ["勤工助学","岗位"]),
    ("学生证丢了怎么办", ["学生证","补办"]),
    ("转专业条件", ["转专业","条件"]),
]

def recall_at_10(results, keywords):
    for r in results[:10]:
        if any(kw in (r.get("content","")) for kw in keywords):
            return 1
    return 0

def mrr(results, keywords):
    for i, r in enumerate(results):
        if any(kw in (r.get("content","")) for kw in keywords):
            return 1.0 / (i+1)
    return 0.0

# Setup
kb = Knowledge.objects.first()
if not kb:
    print("ERROR: No knowledge base"); sys.exit(1)
mid = kb.embedding_model_id
model = get_model_by_id(mid, "default")
dp = get_model_default_params(model)
emb = ModelManage.get_model(mid, lambda _id: get_model(model, **{**dp}))
vec = VectorStore.get_embedding_vector()
kids = [str(kb.id)]

print("="*55)
print(f"KB: {kb.name}  |  Model: {str(mid)[:8]}...  |  Queries: {len(QUESTIONS)}")
print("="*55)

# Run all modes
results = {}
for mode in ["embedding", "keywords", "blend", "hybrid"]:
    recall_vals, mrr_vals, times = [], [], []
    for q, kws in QUESTIONS:
        t0 = time.time()
        hits = vec.query(q, emb.embed_query(q), kids, None,None,None, True, 10, 0.3, SearchMode(mode))
        dt = (time.time()-t0)*1000
        # fetch content
        if hits:
            pids = [h["paragraph_id"] for h in hits[:10] if h.get("paragraph_id")]
            pmap = {p["id"]: p.get("content","") for p in Paragraph.objects.filter(id__in=pids).values("id","content")}
            for h in hits: h["content"] = pmap.get(h.get("paragraph_id"),"")
        recall_vals.append(recall_at_10(hits or [], kws))
        mrr_vals.append(mrr(hits or [], kws))
        times.append(dt)
    n = len(recall_vals)
    results[mode] = {"recall@10": round(sum(recall_vals)/n,3), "mrr": round(sum(mrr_vals)/n,3),
                      "avg_ms": round(sum(times)/n,1)}
    print(f"  {mode:<10}  recall@10={results[mode]['recall@10']:.3f}  mrr={results[mode]['mrr']:.3f}  avg={results[mode]['avg_ms']:.0f}ms")

print("-"*55)
best = max(results, key=lambda m: results[m]["recall@10"])
worst = min(results, key=lambda m: results[m]["recall@10"])
hyb = results.get("hybrid",{})
emb_r = results.get("embedding",{})
if hyb and emb_r and emb_r["recall@10"] > 0:
    gain = (hyb["recall@10"]-emb_r["recall@10"])/emb_r["recall@10"]*100
    print(f"  Hybrid vs Embedding recall gain: {gain:+.0f}%")
print(f"  Best: {best} | Worst: {worst}")

out = {"kb": kb.name, "embedding_model": str(mid), "queries": len(QUESTIONS), "results": results}
with open(os.path.join(os.path.dirname(__file__), "benchmark_results.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nSaved: benchmark_results.json")
