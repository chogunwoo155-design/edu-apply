from django.urls import path

from . import views

app_name = "applications"

urlpatterns = [
    path("courses/<slug:slug>/apply/", views.apply, name="apply"),
    path("applications/receipt/<str:token>/", views.receipt, name="receipt"),
]
