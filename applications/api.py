from django.conf import settings
from django.core.mail import send_mail
from rest_framework import permissions, viewsets

from .models import Application
from .serializers import ApplicationCreateSerializer, ApplicationSerializer


class ApplicationViewSet(viewsets.ModelViewSet):
    """
    POST /api/applications/      누구나 신청
    GET/PATCH/DELETE ...         관리자만
    """

    queryset = Application.objects.all()

    def get_permissions(self):
        if self.action == "create":
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    def get_serializer_class(self):
        if self.action == "create":
            return ApplicationCreateSerializer
        return ApplicationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def perform_create(self, serializer):
        application = serializer.save()
        send_mail(
            subject=f"[히어로스쿨] {application.course.title} 신청이 접수되었습니다",
            message=(
                f"{application.name}님, 신청해 주셔서 감사합니다.\n"
                f"연락 가능 날짜({application.contact_date:%Y-%m-%d})에 담당자가 연락드리겠습니다."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[application.email],
        )
