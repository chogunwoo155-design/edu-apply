from django.contrib import admin

from .models import Course, CurriculumItem


class CurriculumInline(admin.TabularInline):
    model = CurriculumItem
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "starts_on", "apply_deadline", "capacity", "is_open"]
    list_filter = ["category", "is_open"]
    search_fields = ["title", "tagline"]
    prepopulated_fields = {"slug": ["title"]}
    inlines = [CurriculumInline]
