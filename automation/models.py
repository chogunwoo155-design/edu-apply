from django.db import models


class NotificationLog(models.Model):
    """
    신청자에게 보낸(보내려 한) 메일 한 통 = 한 줄.

    (신청, 종류)에 유니크 제약을 걸어서, 배치를 몇 번 다시 돌려도
    같은 사람에게 같은 메일이 두 번 가지 않는다. 실패한 줄은 다음 배치가 다시 시도한다.
    """

    class Kind(models.TextChoices):
        CONFIRMATION = "confirmation", "접수 확인"
        CONTACT_REMINDER = "contact_reminder", "연락 하루 전 안내"

    class Status(models.TextChoices):
        PENDING = "pending", "보내는 중"
        SENT = "sent", "보냄"
        FAILED = "failed", "실패"

    application = models.ForeignKey(
        "applications.Application", on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField("종류", max_length=30, choices=Kind.choices)
    status = models.CharField("상태", max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField("시도 횟수", default=0)
    last_error = models.TextField("마지막 오류", blank=True)
    sent_at = models.DateTimeField("보낸 시각", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "발송 기록"
        verbose_name_plural = "발송 기록"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["application", "kind"], name="uniq_notification_per_kind"),
        ]
        indexes = [models.Index(fields=["status", "kind"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.application_id} · {self.get_status_display()}"


class JobRun(models.Model):
    """배치 한 번 실행 = 한 줄. 관리 화면의 '배치 실행 이력'에 보인다."""

    class Status(models.TextChoices):
        RUNNING = "running", "실행 중"
        SUCCESS = "success", "성공"
        FAILED = "failed", "실패"

    class Trigger(models.TextChoices):
        SCHEDULE = "schedule", "예약 실행"
        MANUAL = "manual", "수동 실행"

    job = models.CharField("작업", max_length=50)
    status = models.CharField("결과", max_length=10, choices=Status.choices, default=Status.RUNNING)
    trigger = models.CharField("실행 방식", max_length=10, choices=Trigger.choices, default=Trigger.SCHEDULE)
    dry_run = models.BooleanField("시험 실행", default=False)
    target_date = models.DateField("기준 날짜")
    stats = models.JSONField("처리 결과", default=dict, blank=True)
    error = models.TextField("오류", blank=True)
    started_at = models.DateTimeField("시작", auto_now_add=True)
    finished_at = models.DateTimeField("끝", null=True, blank=True)

    class Meta:
        verbose_name = "배치 실행 이력"
        verbose_name_plural = "배치 실행 이력"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.job} {self.target_date} {self.get_status_display()}"

    @property
    def duration_seconds(self) -> float | None:
        if not self.finished_at:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 2)
