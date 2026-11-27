from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.home, name="home"),
    path("courses/<slug:slug>/", views.detail, name="detail"),
    path("privacy/", views.privacy, name="privacy"),
]
