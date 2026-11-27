from django.contrib import admin

from . import services
from .models import Application, ApplicationStatusLog

admin.site.site_header = "히어로스쿨 관리"
admin.site.site_title = "히어로스쿨 관리"
admin.site.index_title = "관리 메뉴"


class StatusLogInline(admin.TabularInline):
    model = ApplicationStatusLog
    extra = 0
    can_delete = False
    readonly_fields = ["from_status", "to_status", "changed_by", "changed_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["reference", "name", "email", "course", "contact_date", "status", "created_at"]
    list_filter = ["status", "course", "contact_date"]
    list_editable = ["status"]
    list_select_related = ["course"]
    search_fields = ["name", "email", "address"]
    date_hierarchy = "created_at"
    readonly_fields = ["privacy_agreed_at", "created_at", "updated_at"]
    inlines = [StatusLogInline]

    def save_model(self, request, obj, form, change):
        """admin에서 바꿔도 상태 변경은 서비스를 거쳐 이력이 남는다."""
        if change and "status" in form.changed_data:
            new_status = obj.status
            obj.status = form.initial["status"]
            super().save_model(request, obj, form, change)
            services.change_status(obj, new_status, by=request.user)
        else:
            super().save_model(request, obj, form, change)


@admin.register(ApplicationStatusLog)
class ApplicationStatusLogAdmin(admin.ModelAdmin):
    list_display = ["application", "from_status", "to_status", "changed_by", "changed_at"]
    list_filter = ["to_status"]
    readonly_fields = [f.name for f in ApplicationStatusLog._meta.fields]

    def has_add_permission(self, request):
        return False
