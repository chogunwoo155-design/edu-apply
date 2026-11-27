from django.urls import path

from . import views

app_name = "manage"

urlpatterns = [
    path("", views.manage_list, name="list"),
    path("<int:pk>/status/", views.manage_change_status, name="change_status"),
    path("export.csv", views.manage_export_csv, name="export_csv"),
    path("export-sheet/", views.manage_export_sheet, name="export_sheet"),
    path("jobs/", views.manage_jobs, name="jobs"),
]
