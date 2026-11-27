from django.db import models

from courses.models import Course


class Application(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "접수"
        REVIEWING = "reviewing", "확인중"
        DONE = "done", "완료"

    course = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name="applications", verbose_name="교육"
    )
    name = models.CharField("이름", max_length=30)
    email = models.EmailField("이메일")
    postcode = models.CharField("우편번호", max_length=5, blank=True)
    address = models.CharField("주소", max_length=200)
    address_detail = models.CharField("상세 주소", max_length=100, blank=True)
    contact_date = models.DateField("연락 가능 날짜")
    status = models.CharField(
        "상태", max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    admin_memo = models.TextField("담당자 메모", blank=True)
    created_at = models.DateTimeField("신청 일시", auto_now_add=True)
    updated_at = models.DateTimeField("수정 일시", auto_now=True)

    class Meta:
        verbose_name = "신청"
        verbose_name_plural = "신청"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["contact_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} · {self.course}"

    @property
    def full_address(self) -> str:
        return " ".join(p for p in [self.address, self.address_detail] if p)
