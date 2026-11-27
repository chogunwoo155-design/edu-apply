from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def healthz(request):
    """ALB 헬스 체크: 앱과 DB 연결이 살아 있는지."""
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
    return JsonResponse({"ok": True})


urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path("api/", include("config.api_urls")),
    path("manage/", include("applications.manage_urls")),
    path("", include("applications.urls")),
    path("", include("courses.urls")),
]
