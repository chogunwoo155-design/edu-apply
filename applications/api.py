from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from . import selectors
from .serializers import ApplicationCreateSerializer, ApplicationSerializer


class ApplicationViewSet(viewsets.ModelViewSet):
    """
    POST   /api/applications/             누구나 신청 (IP당 시간당 횟수 제한)
    GET    /api/applications/?status=&course=&q=   관리자: 목록·검색
    GET/PATCH/DELETE /api/applications/{id}/       관리자
    GET    /api/applications/summary/     관리자: 상태별 건수
    """

    throttle_scope = "applications"

    def get_permissions(self):
        if self.action == "create":
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    def get_throttles(self):
        return [ScopedRateThrottle()] if self.action == "create" else []

    def get_serializer_class(self):
        return ApplicationCreateSerializer if self.action == "create" else ApplicationSerializer

    def get_queryset(self):
        p = self.request.query_params
        return selectors.application_list(status=p.get("status"), course=p.get("course"), q=p.get("q"))

    @action(detail=False)
    def summary(self, request):
        return Response(selectors.status_counts())
