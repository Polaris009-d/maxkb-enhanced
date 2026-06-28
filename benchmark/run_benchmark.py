# coding=utf-8
"""
Benchmark script for MaxKB RAG pipeline.

Evaluates:
- Recall@10: % of questions where relevant paragraphs appear in top-10
- MRR (Mean Reciprocal Rank): average of 1/rank of first relevant result
- Latency: end-to-end time per query
- Cache hit rate: % of queries answered from semantic cache
- Search mode comparison: embedding vs keywords vs blend vs hybrid

Usage:
    cd D:\落地项目\MaxKB-v2\apps
    python ../benchmark/run_benchmark.py
"""
import json
import os
import sys
import time
from typing import List, Dict

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maxkb.settings")
os.environ["MAXKB_CONFIG_TYPE"] = "ENV"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import django

django.setup()

from knowledge.models import Knowledge, Paragraph, SearchMode, Document
from knowledge.vector.pg_vector import PGVector, VectorStore
from knowledge.vector.base_vector import BaseVectorStore
from models_provider.tools import get_model_by_id, get_model_default_params
from common.config.embedding_config import VectorStore, ModelManage
from common.semantic_cache.cache_manager import SemanticCacheManager
from common.reranker.reranker import RerankerManager


# ── Test Questions (simulated campus Q&A) ──
TEST_QUESTIONS = [
    {
        "question": "奖学金如何申请？",
        "relevant_keywords": ["奖学金", "申请", "条件", "评审"],
    },
    {
        "question": "学生违纪处分有哪些类型？",
        "relevant_keywords": ["处分", "警告", "严重警告", "记过", "留校察看"],
    },
    {
        "question": "毕业论文抄袭会有什么后果？",
        "relevant_keywords": ["论文", "抄袭", "作弊", "学位"],
    },
    {
        "question": "助学金的申请条件是什么？",
        "relevant_keywords": ["助学金", "申请", "困难", "家庭"],
    },
    {
        "question": "宿舍管理规定有哪些？",
        "relevant_keywords": ["宿舍", "住宿", "管理", "安全"],
    },
    {
        "question": "如何办理休学手续？",
        "relevant_keywords": ["休学", "手续", "学籍"],
    },
    {
        "question": "学生考试作弊怎么处理？",
        "relevant_keywords": ["考试", "作弊", "处分", "违纪"],
    },
    {
        "question": "国家励志奖学金评选标准？",
        "relevant_keywords": ["国家励志", "奖学金", "评选", "贫困"],
    },
    {
        "question": "学生可以校外租房吗？",
        "relevant_keywords": ["租房", "住宿", "校外"],
    },
    {
        "question": "毕业要求修满多少学分？",
        "relevant_keywords": ["毕业", "学分", "要求"],
    },
    {
        "question": "勤工助学岗位怎么申请？",
        "relevant_keywords": ["勤工助学", "岗位", "申请"],
    },
    {
        "question": "学生证丢失怎么补办？",
        "relevant_keywords": ["学生证", "补办", "丢失"],
    },
    {
        "question": "转专业有什么条件？",
        "relevant_keywords": ["转专业", "条件", "申请"],
    },
    {
        "question": "校园一卡通怎么充值？",
        "relevant_keywords": ["一卡通", "充值", "校园卡"],
    },
    {
        "question": "学位论文作假怎么处理？",
        "relevant_keywords": ["学位", "论文", "作假", "处分"],
    },
]


def is_relevant(paragraph_text: str, keywords: List[str]) -> bool:
    """Check if paragraph contains at least one relevant keyword."""
    return any(kw in paragraph_text for kw in keywords)


def compute_recall_at_k(results: List[Dict], keywords: List[str], k: int = 10) -> bool:
    """Check if any result in top-K contains relevant keywords."""
    top_k = results[:k]
    for r in top_k:
        text = r.get("content", "")
        if is_relevant(text, keywords):
            return True
    return False


def compute_mrr(results: List[Dict], keywords: List[str]) -> float:
    """Compute Mean Reciprocal Rank: 1 / rank_of_first_relevant."""
    for i, r in enumerate(results):
        text = r.get("content", "")
        if is_relevant(text, keywords):
            return 1.0 / (i + 1)
    return 0.0


def run_benchmark():
    """Main benchmark runner."""
    print("=" * 60)
    print("MaxKB RAG Pipeline Benchmark")
    print("=" * 60)

    # Get knowledge base and model
    kb = Knowledge.objects.first()
    if not kb:
        print("ERROR: No knowledge base found. Please create one first.")
        return

    embedding_model_id = kb.embedding_model_id
    print(f"Knowledge Base: {kb.name}")
    print(f"Embedding Model: {embedding_model_id}")
    print(f"Test Questions: {len(TEST_QUESTIONS)}")
    print()

    # Get embedding model
    model = get_model_by_id(embedding_model_id, "default")
    default_params = get_model_default_params(model)
    embedding_model = ModelManage.get_model(
        embedding_model_id,
        lambda _id: get_model_by_id(embedding_model_id, "default")
        if hasattr(default_params, '__iter__') else None
    )

    # Get embedding instance via the proper factory method
    from models_provider.tools import get_model
    embedding_model = ModelManage.get_model(
        embedding_model_id,
        lambda _id: get_model(model, **{**default_params}),
    )

    vector = VectorStore.get_embedding_vector()
    knowledge_id_list = [str(kb.id)]

    # ── Benchmark per search mode ──
    modes = ["embedding", "keywords", "blend", "hybrid"]
    results_by_mode = {}

    for mode in modes:
        print(f"\n── {mode.upper()} Search ──")
        recall_scores = []
        mrr_scores = []
        latencies = []
        reranker_latencies = []

        for i, q in enumerate(TEST_QUESTIONS):
            query_text = q["question"]
            keywords = q["relevant_keywords"]

            # Measure search latency
            t0 = time.time()
            try:
                search_results = vector.query(
                    query_text,
                    embedding_model.embed_query(query_text),
                    knowledge_id_list,
                    None, None, None,
                    True, 20, 0.3,
                    SearchMode(mode),
                )
            except Exception as e:
                print(f"  [{i+1:2d}] ERROR: {e}")
                continue
            t1 = time.time()
            search_time = (t1 - t0) * 1000

            # Fetch paragraph content
            if search_results:
                para_ids = [r["paragraph_id"] for r in search_results[:20] if r.get("paragraph_id")]
                paragraphs = Paragraph.objects.filter(id__in=para_ids).values("id", "content")
                id_to_content = {p["id"]: p["content"] or "" for p in paragraphs}
                for r in search_results:
                    r["content"] = id_to_content.get(r.get("paragraph_id"), "")

            # Apply Reranker
            t2 = time.time()
            search_results = RerankerManager.rerank(
                query_text=query_text,
                candidates=search_results,
                top_k=5,
                embedding_model=embedding_model,
            )
            t3 = time.time()
            rerank_time = (t3 - t2) * 1000

            recall = compute_recall_at_k(search_results, keywords, k=10)
            mrr = compute_mrr(search_results, keywords)

            recall_scores.append(1 if recall else 0)
            mrr_scores.append(mrr)
            latencies.append(search_time)
            reranker_latencies.append(rerank_time)

            status = "✓" if recall else "✗"
            print(f"  [{i+1:2d}] {status} recall={recall} mrr={mrr:.3f} search={search_time:.0f}ms rerank={rerank_time:.0f}ms | {query_text}")

        valid = len(recall_scores)
        results_by_mode[mode] = {
            "recall@10": round(sum(recall_scores) / valid, 3) if valid else 0,
            "mrr": round(sum(mrr_scores) / valid, 3) if valid else 0,
            "avg_search_ms": round(sum(latencies) / valid, 1) if valid else 0,
            "avg_rerank_ms": round(sum(reranker_latencies) / valid, 1) if valid else 0,
            "total_ms": round(sum(latencies) / valid + sum(reranker_latencies) / valid, 1) if valid else 0,
            "valid_queries": valid,
        }

    # ── Cache hit rate ──
    print(f"\n── Semantic Cache Benchmark ──")
    cache_hits = 0
    cache_total = len(TEST_QUESTIONS)
    for q in TEST_QUESTIONS:
        hit = SemanticCacheManager.search(
            q["question"],
            "benchmark",
            embedding_model,
            similarity_threshold=0.92,
        )
        if hit:
            cache_hits += 1
        else:
            # Store for future hits
            SemanticCacheManager.cache(
                q["question"], f"Mock answer for: {q['question']}",
                100, 200, embedding_model.embed_query(q["question"]),
                "benchmark",
            )
    # Second pass: all should be cached now
    cache_hits_2nd = 0
    for q in TEST_QUESTIONS:
        hit = SemanticCacheManager.search(
            q["question"], "benchmark", embedding_model, similarity_threshold=0.92
        )
        if hit:
            cache_hits_2nd += 1

    # Clean up benchmark cache
    SemanticCacheManager.invalidate("benchmark")

    print(f"  First pass (cold): {cache_hits}/{cache_total} hits")
    print(f"  Second pass (warm): {cache_hits_2nd}/{cache_total} hits")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'Mode':<12} {'Recall@10':>10} {'MRR':>8} {'Search(ms)':>10} {'Rerank(ms)':>11} {'Total(ms)':>10}")
    print("-" * 60)
    for mode, r in results_by_mode.items():
        print(f"{mode:<12} {r['recall@10']:>10.3f} {r['mrr']:>8.3f} {r['avg_search_ms']:>10.1f} {r['avg_rerank_ms']:>11.1f} {r['total_ms']:>10.1f}")

    # Find best mode
    best = max(results_by_mode.items(), key=lambda x: x[1]["recall@10"])
    worst = min(results_by_mode.items(), key=lambda x: x[1]["recall@10"])
    print(f"\nBest search mode: {best[0]} (Recall@10={best[1]['recall@10']})")
    print(f"Worst search mode: {worst[0]} (Recall@10={worst[1]['recall@10']})")
    if results_by_mode.get("hybrid") and results_by_mode.get("embedding"):
        recall_improvement = (results_by_mode["hybrid"]["recall@10"] - results_by_mode["embedding"]["recall@10"]) / max(results_by_mode["embedding"]["recall@10"], 0.001) * 100
        print(f"Hybrid vs Embedding recall improvement: {recall_improvement:.1f}%")
    print(f"\nCache: first pass {cache_hits}/{cache_total}, second pass {cache_hits_2nd}/{cache_total}")
    print(f"LLM call reduction: {(cache_hits_2nd - cache_hits) / max(cache_total, 1) * 100:.0f}%")

    # ── Output JSON for CI / dashboard ──
    output = {
        "config": {
            "knowledge_base": kb.name,
            "embedding_model": str(embedding_model_id),
            "num_questions": len(TEST_QUESTIONS),
        },
        "results": results_by_mode,
        "cache": {
            "first_pass_hits": cache_hits,
            "second_pass_hits": cache_hits_2nd,
            "total": cache_total,
        },
    }
    json_path = os.path.join(os.path.dirname(__file__), "benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {json_path}")


if __name__ == "__main__":
    run_benchmark()
