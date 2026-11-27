from rest_framework import serializers

from .models import Course, CurriculumItem


class CurriculumItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurriculumItem
        fields = ["order", "title", "summary"]


class CourseSerializer(serializers.ModelSerializer):
    curriculum = CurriculumItemSerializer(many=True, read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = Course
        fields = [
            "slug",
            "title",
            "tagline",
            "category",
            "category_label",
            "description",
            "target",
            "schedule",
            "location",
            "capacity",
            "fee",
            "starts_on",
            "apply_deadline",
            "is_open",
            "curriculum",
        ]
