from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("config.api_urls")),
    path("manage/", include("applications.manage_urls")),
    path("", include("courses.urls")),
]
