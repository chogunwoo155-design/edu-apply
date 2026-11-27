from django.contrib import admin

from .models import Application


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "email", "course", "contact_date", "status", "created_at"]
    list_filter = ["status", "course", "contact_date"]
    list_editable = ["status"]
    search_fields = ["name", "email", "address"]
    date_hierarchy = "created_at"
