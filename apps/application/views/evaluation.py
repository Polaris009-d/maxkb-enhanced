# coding=utf-8
"""
Views for evaluation configuration and results.
"""
import json

from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from application.models.evaluation import EvaluationConfig, EvaluationResult
from application.serializers.evaluation import (
    EvaluationConfigSerializer,
    EvaluationResultSerializer,
    EvaluationStatsSerializer,
)
from common.auth.authenticate import TokenAuth
from common.exception.app_exception import AppApiException


class EvaluationConfigView(APIView):
    """CRUD for evaluation configurations."""
    authentication_classes = [TokenAuth]

    def get(self, request, application_id: str):
        configs = EvaluationConfig.objects.filter(application_id=application_id)
        serializer = EvaluationConfigSerializer(configs, many=True)
        return Response({"code": 200, "message": "Success", "data": serializer.data})

    def post(self, request, application_id: str):
        data = request.data.copy()
        data["application_id"] = application_id
        serializer = EvaluationConfigSerializer(data=data)
        if serializer.is_valid():
            config = serializer.save()
            return Response({"code": 200, "message": "Success", "data": {"id": str(config.id)}})
        raise AppApiException(
            code=status.HTTP_400_BAD_REQUEST, message=json.dumps(serializer.errors)
        )

    class Operate(APIView):
        authentication_classes = [TokenAuth]

        def get_object(self, config_id: str) -> EvaluationConfig:
            try:
                return EvaluationConfig.objects.get(id=config_id)
            except EvaluationConfig.DoesNotExist:
                raise AppApiException(code=404, message=_("Evaluation config not found"))

        def put(self, request, application_id: str, config_id: str):
            config = self.get_object(config_id)
            serializer = EvaluationConfigSerializer(config, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({"code": 200, "message": "Success"})
            raise AppApiException(
                code=status.HTTP_400_BAD_REQUEST, message=json.dumps(serializer.errors)
            )

        def delete(self, request, application_id: str, config_id: str):
            config = self.get_object(config_id)
            config.delete()
            return Response({"code": 200, "message": "Success"})

    class Trigger(APIView):
        authentication_classes = [TokenAuth]

        def post(self, request, application_id: str, config_id: str):
            """Manually trigger an evaluation run."""
            from application.task.evaluation import run_evaluation

            try:
                config = EvaluationConfig.objects.get(id=config_id, application_id=application_id)
            except EvaluationConfig.DoesNotExist:
                raise AppApiException(code=404, message=_("Evaluation config not found"))

            task = run_evaluation.delay(str(config.id))
            return Response({
                "code": 200,
                "message": "Evaluation triggered",
                "data": {"task_id": task.id},
            })


class EvaluationResultView(APIView):
    """List evaluation results with pagination."""
    authentication_classes = [TokenAuth]

    def get(self, request, application_id: str):
        config_id = request.query_params.get("config_id")
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))

        if config_id:
            qs = EvaluationResult.objects.filter(evaluation_config_id=config_id)
        else:
            configs = EvaluationConfig.objects.filter(application_id=application_id)
            qs = EvaluationResult.objects.filter(evaluation_config__in=configs)

        total = qs.count()
        results = qs[(page - 1) * page_size : page * page_size]
        serializer = EvaluationResultSerializer(results, many=True)

        return Response({
            "code": 200,
            "message": "Success",
            "data": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "results": serializer.data,
            },
        })


class EvaluationStatsView(APIView):
    """Aggregated evaluation statistics for dashboard charts."""
    authentication_classes = [TokenAuth]

    def get(self, request, application_id: str):
        days = int(request.query_params.get("days", 30))
        stats = EvaluationStatsSerializer.compute(application_id, days)
        return Response({"code": 200, "message": "Success", "data": stats})
