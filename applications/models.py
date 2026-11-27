from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from courses.models import Course


class Application(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "접수"
        REVIEWING = "reviewing", "확인중"
        DONE = "done", "완료"

    class ContactTime(models.TextChoices):
        ANY = "any", "언제든"
        MORNING = "morning", "오전 (9~12시)"
        AFTERNOON = "afternoon", "오후 (13~18시)"

    course = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name="applications", verbose_name="교육"
    )
    name = models.CharField("이름", max_length=30)
    email = models.EmailField("이메일")
    postcode = models.CharField("우편번호", max_length=5, blank=True)
    address = models.CharField("주소", max_length=200)
    address_detail = models.CharField("상세 주소", max_length=100, blank=True)
    contact_date = models.DateField("연락 가능 날짜")
    contact_time = models.CharField(
        "연락 시간대", max_length=10, choices=ContactTime.choices, default=ContactTime.ANY
    )
    status = models.CharField(
        "상태", max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    admin_memo = models.TextField("담당자 메모", blank=True)
    privacy_agreed_at = models.DateTimeField("개인정보 수집·이용 동의 시각", null=True, blank=True)
    created_at = models.DateTimeField("신청 일시", auto_now_add=True)
    updated_at = models.DateTimeField("수정 일시", auto_now=True)

    class Meta:
        verbose_name = "신청"
        verbose_name_plural = "신청"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["contact_date"]),
        ]
        constraints = [
            # 같은 교육에 같은 이메일로 두 번 신청할 수 없다 (대소문자 무시). 서비스 검사의 마지막 방어선.
            models.UniqueConstraint(Lower("email"), "course", name="uniq_application_email_per_course"),
            models.CheckConstraint(
                condition=models.Q(status__in=["received", "reviewing", "done"]),
                name="application_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reference} {self.name}"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def reference(self) -> str:
        """신청자에게 보여 주는 신청번호. 예: HS261127-0042"""
        created = timezone.localtime(self.created_at) if self.created_at else timezone.localtime()
        return f"HS{created:%y%m%d}-{self.pk or 0:04d}"

    @property
    def full_address(self) -> str:
        return " ".join(p for p in [self.address, self.address_detail] if p)


class ApplicationStatusLog(models.Model):
    """상태가 누구에 의해 언제 바뀌었는지. 개인정보를 다루는 화면이라 처리 이력을 남긴다."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="status_logs")
    from_status = models.CharField(max_length=20, choices=Application.Status.choices)
    to_status = models.CharField(max_length=20, choices=Application.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "상태 변경 이력"
        verbose_name_plural = "상태 변경 이력"
        ordering = ["-changed_at"]

    def __str__(self) -> str:
        return f"{self.application_id}: {self.from_status} → {self.to_status}"
