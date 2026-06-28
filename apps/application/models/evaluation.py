# coding=utf-8
"""
Evaluation models for RAGAS-style metrics (Faithfulness, AnswerRelevancy).
"""
import uuid_utils.compat as uuid
from django.db import models


class EvaluationConfig(models.Model):
    """Configuration for automated RAG evaluation on an application."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, verbose_name="主键id")
    application = models.ForeignKey("application.Application", on_delete=models.CASCADE, verbose_name="应用")
    name = models.CharField(max_length=128, verbose_name="评测名称")
    metrics = models.JSONField(default=list, verbose_name="评测指标")
    schedule_crontab = models.CharField(max_length=64, null=True, blank=True, verbose_name="定时任务cron表达式")
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name="上次运行时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        db_table = "evaluation_config"
        ordering = ["-created_at"]


class EvaluationResult(models.Model):
    """Single evaluation result for a chat record."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, verbose_name="主键id")
    evaluation_config = models.ForeignKey(
        EvaluationConfig, on_delete=models.CASCADE, related_name="results", verbose_name="评测配置"
    )
    chat_record_id = models.UUIDField(verbose_name="对话记录ID")
    question = models.TextField(verbose_name="用户问题")
    answer = models.TextField(verbose_name="模型回答")
    contexts = models.JSONField(default=list, verbose_name="检索上下文")
    faithfulness_score = models.FloatField(null=True, blank=True, verbose_name="忠实度评分")
    answer_relevancy_score = models.FloatField(null=True, blank=True, verbose_name="答案相关性评分")
    run_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="评测时间")

    class Meta:
        db_table = "evaluation_result"
        ordering = ["-run_at"]
        indexes = [
            models.Index(fields=["evaluation_config", "run_at"]),
        ]
