# coding=utf-8
"""
Celery task for running RAGAS-style evaluations on chat history.
"""
import logging
from datetime import timedelta

import numpy as np
from celery import shared_task
from django.utils import timezone

from application.models.evaluation import EvaluationConfig, EvaluationResult
from common.utils.logger import maxkb_logger
from models_provider.tools import get_model_instance_by_model_workspace_id

logger = logging.getLogger("maxkb.evaluation")


def _compute_faithfulness(question: str, answer: str, contexts: list, chat_model) -> float:
    """Evaluate faithfulness: does the answer stay true to the provided context?

    Uses LLM-as-judge with a structured prompt. Returns a score between 0 and 1.
    """
    if not contexts or not answer:
        return 0.0

    context_text = "\n\n".join([f"[{i+1}] {c}" for i, c in enumerate(contexts[:5])])
    prompt = (
        "You are an evaluation judge for RAG answer quality. "
        "Your task is to rate the FAITHFULNESS of an answer given the provided context.\n\n"
        f"Question: {question}\n\n"
        f"Context:\n{context_text}\n\n"
        f"Answer: {answer}\n\n"
        "Faithfulness measures whether each claim in the answer can be inferred from the context. "
        "Rate on a scale of 0 to 1, where:\n"
        "- 1.0: All claims in the answer are directly supported by the context.\n"
        "- 0.5: Some claims are supported, some are not or are hallucinations.\n"
        "- 0.0: The answer is completely unrelated to the context or contradicted by it.\n\n"
        "Output ONLY a number between 0 and 1, nothing else."
    )
    try:
        from langchain_core.messages import HumanMessage
        response = chat_model.invoke([HumanMessage(content=prompt)])
        score_text = response.content.strip() if hasattr(response, "content") else str(response).strip()
        # Extract the first float from the response
        import re
        match = re.search(r"(\d+\.?\d*)", score_text)
        if match:
            return min(1.0, max(0.0, float(match.group(1))))
    except Exception as e:
        logger.warning(f"Faithfulness evaluation failed: {e}")
    return 0.0


def _compute_answer_relevancy(question: str, answer: str, embedding_model) -> float:
    """Evaluate answer relevancy using embedding cosine similarity.

    Computes average cosine similarity between question embedding and each
    sentence in the answer. Returns a score between 0 and 1.
    """
    if not answer or not embedding_model:
        return 0.0

    try:
        # Split answer into sentences
        sentences = [s.strip() for s in answer.replace("！", "。").replace("？", "。").split("。") if s.strip()]

        if not sentences:
            return 0.0

        question_emb = embedding_model.embed_query(question)
        if question_emb is None:
            return 0.0

        sentence_embs = embedding_model.embed_documents(sentences)
        if not sentence_embs:
            return 0.0

        # Average cosine similarity
        question_arr = np.array(question_emb, dtype=np.float64)
        similarities = []
        for s_emb in sentence_embs:
            s_arr = np.array(s_emb, dtype=np.float64)
            dot = np.dot(question_arr, s_arr)
            norm_q = np.linalg.norm(question_arr)
            norm_s = np.linalg.norm(s_arr)
            if norm_q > 0 and norm_s > 0:
                similarities.append(float(dot / (norm_q * norm_s)))

        if not similarities:
            return 0.0

        return round(float(np.mean(similarities)), 4)
    except Exception as e:
        logger.warning(f"AnswerRelevancy evaluation failed: {e}")
    return 0.0


@shared_task(name="run_evaluation", max_retries=2, default_retry_delay=60)
def run_evaluation(config_id: str):
    """Celery task: run evaluation for a given config.

    Fetches recent chat records, computes faithfulness and answer relevancy
    metrics, and stores results.
    """
    try:
        config = EvaluationConfig.objects.select_related("application").get(id=config_id)
    except EvaluationConfig.DoesNotExist:
        logger.error(f"EvaluationConfig {config_id} not found")
        return

    if not config.is_active:
        return

    application = config.application
    metrics = config.metrics or ["faithfulness", "answer_relevancy"]
    workspace_id = str(application.workspace_id)

    # Fetch recent chat records for this application
    from chat.models import ChatRecord
    from django.db.models import Q

    since = timezone.now() - timedelta(hours=24)
    records = ChatRecord.objects.filter(
        application_id=application.id,
        create_time__gte=since,
    ).exclude(
        Q(answer_text="") | Q(answer_text__isnull=True)
    ).order_by("-create_time")[:50]

    if not records:
        logger.info(f"No recent chat records for application {application.id}")
        config.last_run_at = timezone.now()
        config.save(update_fields=["last_run_at"])
        return

    # Get evaluation models
    chat_model = None
    embedding_model = None
    if "faithfulness" in metrics:
        try:
            chat_model = get_model_instance_by_model_workspace_id(
                application.model_id, workspace_id
            )
        except Exception as e:
            logger.warning(f"Failed to get chat model for evaluation: {e}")

    if "answer_relevancy" in metrics:
        try:
            # Use application's knowledge base embedding model
            from application.models import ApplicationKnowLedgeMapping

            mapping = ApplicationKnowLedgeMapping.objects.filter(
                application_id=application.id
            ).select_related("knowledge").first()
            if mapping:
                from models_provider.tools import get_model_by_id, get_model_default_params
                from common.config.embedding_config import ModelManage

                kb = mapping.knowledge
                model = get_model_by_id(kb.embedding_model_id, workspace_id)
                default_params = get_model_default_params(model)
                embedding_model = ModelManage.get_model(
                    kb.embedding_model_id,
                    lambda _id: get_model_by_id(kb.embedding_model_id, workspace_id)
                )
                # Actually get the proper instance via the provider
                from models_provider.tools import get_model
                embedding_model = ModelManage.get_model(
                    kb.embedding_model_id,
                    lambda _id: get_model(model, **{**default_params}),
                )
        except Exception as e:
            logger.warning(f"Failed to get embedding model for evaluation: {e}")

    # Evaluate each record
    results = []
    for record in records:
        question = record.problem_text or ""
        answer = record.answer_text or ""

        # Extract contexts from chat details
        contexts = []
        try:
            details = record.details or {}
            if isinstance(details, str):
                import json
                details = json.loads(details)
            paragraph_list = details.get("search_step", {}).get("paragraph_list", [])
            contexts = [p.get("content", "") for p in paragraph_list if p.get("content")]
        except Exception:
            pass

        # Compute scores
        faith_score = None
        ar_score = None

        if "faithfulness" in metrics and chat_model:
            faith_score = _compute_faithfulness(question, answer, contexts, chat_model)

        if "answer_relevancy" in metrics and embedding_model:
            ar_score = _compute_answer_relevancy(question, answer, embedding_model)

        result = EvaluationResult(
            evaluation_config=config,
            chat_record_id=record.id,
            question=question,
            answer=answer,
            contexts=contexts[:10],  # Keep max 10 contexts
            faithfulness_score=faith_score,
            answer_relevancy_score=ar_score,
        )
        results.append(result)

    if results:
        EvaluationResult.objects.bulk_create(results)
        logger.info(
            f"Evaluation completed for config {config_id}: {len(results)} records evaluated"
        )

    config.last_run_at = timezone.now()
    config.save(update_fields=["last_run_at"])
