# coding=utf-8
"""
Serializers for evaluation configuration and results.
"""
from django.db.models import Avg, Count
from django.utils import timezone
from rest_framework import serializers

from application.models.evaluation import EvaluationConfig, EvaluationResult


class EvaluationConfigSerializer(serializers.ModelSerializer):
    """Serializer for evaluation configuration CRUD."""

    metrics_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = EvaluationConfig
        fields = [
            "id",
            "application_id",
            "name",
            "metrics",
            "metrics_display",
            "schedule_crontab",
            "is_active",
            "last_run_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_run_at", "created_at", "updated_at"]

    def get_metrics_display(self, obj):
        labels = {
            "faithfulness": "忠实度 (Faithfulness)",
            "answer_relevancy": "答案相关性 (AnswerRelevancy)",
        }
        return [labels.get(m, m) for m in (obj.metrics or [])]


class EvaluationResultSerializer(serializers.ModelSerializer):
    """Serializer for individual evaluation results."""

    class Meta:
        model = EvaluationResult
        fields = [
            "id",
            "evaluation_config_id",
            "chat_record_id",
            "question",
            "answer",
            "contexts",
            "faithfulness_score",
            "answer_relevancy_score",
            "run_at",
        ]


class EvaluationStatsSerializer(serializers.Serializer):
    """Aggregated statistics for evaluation dashboard."""

    avg_faithfulness = serializers.FloatField()
    avg_answer_relevancy = serializers.FloatField()
    total_count = serializers.IntegerField()
    trend_data = serializers.ListField()  # [{date, avg_faithfulness, avg_answer_relevancy, count}, ...]

    @staticmethod
    def compute(application_id: str, days: int = 30):
        """Compute aggregated stats and time-series trend data."""
        from django.db.models.functions import TruncDate

        since = timezone.now() - timezone.timedelta(days=days)
        configs = EvaluationConfig.objects.filter(application_id=application_id)
        results = EvaluationResult.objects.filter(
            evaluation_config__in=configs, run_at__gte=since
        )

        agg = results.aggregate(
            avg_f=Avg("faithfulness_score"),
            avg_ar=Avg("answer_relevancy_score"),
            total=Count("id"),
        )

        # Time-series: group by date
        trend_qs = (
            results.annotate(date=TruncDate("run_at"))
            .values("date")
            .annotate(
                avg_f=Avg("faithfulness_score"),
                avg_ar=Avg("answer_relevancy_score"),
                count=Count("id"),
            )
            .order_by("date")
        )
        trend_data = [
            {
                "date": str(item["date"]),
                "avg_faithfulness": round(item["avg_f"] or 0, 4),
                "avg_answer_relevancy": round(item["avg_ar"] or 0, 4),
                "count": item["count"],
            }
            for item in trend_qs
        ]

        return {
            "avg_faithfulness": round(agg["avg_f"] or 0, 4),
            "avg_answer_relevancy": round(agg["avg_ar"] or 0, 4),
            "total_count": agg["total"] or 0,
            "trend_data": trend_data,
        }
