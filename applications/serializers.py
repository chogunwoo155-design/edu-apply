import re

from rest_framework import serializers

from courses.models import Course

from . import receipts, rules, services
from .models import Application

CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def msgs(required: str, **extra) -> dict:
    """DRF 기본 번역('이 필드는 blank일 수 없습니다') 대신 칸마다 사람이 쓴 문장."""
    return {"required": required, "blank": required, "null": required, **extra}


def clean_text(value: str, label: str, *, min_len: int = 0) -> str:
    value = (value or "").strip()
    if CONTROL_CHARS.search(value):
        raise serializers.ValidationError(f"{label}에 줄바꿈이나 특수 제어 문자는 쓸 수 없어요.")
    if len(value) < min_len:
        raise serializers.ValidationError(f"{label}을(를) {min_len}글자 이상 입력해 주세요.")
    return value


class ApplicationCreateSerializer(serializers.Serializer):
    """공개 신청 API 입력. 형식만 여기서 보고, 신청 가능 여부·중복은 서비스가 판단한다."""

    course = serializers.SlugRelatedField(
        slug_field="slug", queryset=Course.objects.all(),
        error_messages=msgs("교육을 골라 주세요", does_not_exist="없는 교육이에요."),
    )
    name = serializers.CharField(max_length=30, error_messages=msgs("학생 이름을 적어 주세요", max_length="이름은 30자까지 적을 수 있어요."))
    email = serializers.EmailField(max_length=254, error_messages=msgs("연락받을 이메일을 적어 주세요", invalid="이메일 주소 형식을 확인해 주세요."))
    postcode = serializers.RegexField(r"^\d{5}$", required=False, allow_blank=True,
                                      error_messages={"invalid": "우편번호는 숫자 5자리예요."})
    address = serializers.CharField(max_length=200, error_messages=msgs("주소를 찾아 주세요"))
    address_detail = serializers.CharField(max_length=100, required=False, allow_blank=True)
    contact_date = serializers.DateField(error_messages=msgs("연락받을 날짜를 골라 주세요", invalid="연락받을 날짜를 골라 주세요"))
    contact_time = serializers.ChoiceField(choices=Application.ContactTime.choices,
                                           default=Application.ContactTime.ANY,
                                           error_messages={"invalid_choice": "연락 시간대를 다시 골라 주세요."})
    privacy_agreed = serializers.BooleanField(error_messages=msgs("개인정보 수집·이용에 동의해 주세요"))
    website = serializers.CharField(required=False, allow_blank=True)  # 봇 걸러내기용 숨은 칸

    def validate_name(self, value):
        return clean_text(value, "이름", min_len=2)

    def validate_address(self, value):
        return clean_text(value, "주소", min_len=4)

    def validate_address_detail(self, value):
        return clean_text(value, "상세 주소")

    def validate_privacy_agreed(self, value):
        if not value:
            raise serializers.ValidationError("개인정보 수집·이용에 동의해야 신청할 수 있어요.")
        return value

    def validate_website(self, value):
        if value:
            raise serializers.ValidationError("잘못된 요청이에요.")
        return value

    def create(self, validated_data):
        data = services.ApplicantInput(
            name=validated_data["name"],
            email=validated_data["email"],
            address=validated_data["address"],
            contact_date=validated_data["contact_date"],
            postcode=validated_data.get("postcode", ""),
            address_detail=validated_data.get("address_detail", ""),
            contact_time=validated_data["contact_time"],
        )
        try:
            return services.submit_application(validated_data["course"].pk, data)
        except services.ApplicationError as e:
            raise serializers.ValidationError({e.field or "non_field_errors": [e.message]})

    def to_representation(self, instance):
        return ApplicationReceiptSerializer(instance).data


class ApplicationReceiptSerializer(serializers.ModelSerializer):
    """신청자에게 돌려주는 접수증. 주소 등은 다시 내보내지 않는다."""

    course_title = serializers.CharField(source="course.title")
    contact_time_label = serializers.CharField(source="get_contact_time_display")
    receipt_url = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = ["reference", "course_title", "name", "email", "contact_date", "contact_time",
                  "contact_time_label", "status", "receipt_url"]

    def get_receipt_url(self, obj) -> str:
        return receipts.make_url(obj)


class ApplicationSerializer(serializers.ModelSerializer):
    """관리자용 조회·수정."""

    course = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    contact_time_label = serializers.CharField(source="get_contact_time_display", read_only=True)

    class Meta:
        model = Application
        fields = [
            "id", "reference", "course", "course_title", "name", "email", "postcode", "address",
            "address_detail", "contact_date", "contact_time", "contact_time_label", "status",
            "status_label", "admin_memo", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reference", "course", "created_at", "updated_at"]

    def validate_name(self, value):
        return clean_text(value, "이름", min_len=2)

    def validate_contact_date(self, value):
        # 담당자는 일정을 오늘로 당길 수 있다. 과거·주말은 막는다.
        if value < rules.today():
            raise serializers.ValidationError("지난 날짜로는 바꿀 수 없어요.")
        if not rules.is_contact_day(value):
            raise serializers.ValidationError("평일을 골라 주세요.")
        return value

    def update(self, instance, validated_data):
        new_status = validated_data.pop("status", None)
        instance = super().update(instance, validated_data)
        if new_status:
            services.change_status(instance, new_status, by=self.context["request"].user)
        return instance
