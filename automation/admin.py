from django.contrib import admin

from .models import JobRun, NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["application", "kind", "status", "attempts", "sent_at", "created_at"]
    list_filter = ["kind", "status"]
    search_fields = ["application__name", "application__email"]
    raw_id_fields = ["application"]
    readonly_fields = ["created_at"]


@admin.register(JobRun)
class JobRunAdmin(admin.ModelAdmin):
    list_display = ["job", "target_date", "status", "trigger", "dry_run", "started_at", "duration_seconds"]
    list_filter = ["job", "status", "trigger", "dry_run"]
    readonly_fields = [f.name for f in JobRun._meta.fields]
