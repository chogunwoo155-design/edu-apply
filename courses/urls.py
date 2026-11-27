from django.urls import path

from . import views
from applications import views as application_views

app_name = "courses"

urlpatterns = [
    path("", views.home, name="home"),
    path("courses/<slug:slug>/", views.detail, name="detail"),
    path("courses/<slug:slug>/apply/", application_views.apply, name="apply"),
]
