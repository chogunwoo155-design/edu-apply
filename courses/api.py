from rest_framework import permissions, viewsets

from .models import Course
from .serializers import CourseSerializer


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    """교육 목록·상세 (누구나 조회)."""

    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"
