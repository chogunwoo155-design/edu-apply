from django.utils import timezone
from rest_framework import serializers

from courses.models import Course

from .models import Application


class ApplicationCreateSerializer(serializers.ModelSerializer):
    course = serializers.SlugRelatedField(slug_field="slug", queryset=Course.objects.all())

    class Meta:
        model = Application
        fields = [
            "id",
            "course",
            "name",
            "email",
            "postcode",
            "address",
            "address_detail",
            "contact_date",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "status", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("이름을 두 글자 이상 입력해 주세요.")
        return value

    def validate_contact_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("오늘 이후 날짜를 골라 주세요.")
        return value

    def validate_course(self, value):
        if not value.is_open:
            raise serializers.ValidationError("신청이 마감된 교육입니다.")
        return value


class ApplicationSerializer(serializers.ModelSerializer):
    course = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "course",
            "course_title",
            "name",
            "email",
            "postcode",
            "address",
            "address_detail",
            "contact_date",
            "status",
            "status_label",
            "admin_memo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "course", "created_at", "updated_at"]
