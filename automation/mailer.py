"""
신청자 메일 발송. 모든 신청자 메일은 이 함수 하나를 거친다.

- (신청, 종류)마다 NotificationLog 한 줄 → 같은 메일 두 번 안 감
- 실패하면 FAILED로 남기고, 다음 배치(retry_failed_notifications)가 다시 보냄
- 동시에 두 프로세스가 같은 메일을 보내려 하면, 상태를 조건부 UPDATE로 먼저 잡은 쪽만 보냄
"""

from __future__ import annotations

import logging
from datetime import timedelta
from enum import Enum

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import NotificationLog

logger = logging.getLogger(__name__)

SUBJECTS = {
    NotificationLog.Kind.CONFIRMATION: "[히어로스쿨] {course} 신청이 접수됐어요",
    NotificationLog.Kind.CONTACT_REMINDER: "[히어로스쿨] 내일 {course} 담당자가 연락드려요",
}

# 다른 프로세스가 PENDING으로 잡은 지 이 시간이 지나도 끝나지 않았으면 죽은 것으로 보고 다시 잡는다.
STALE_PENDING = timedelta(minutes=10)
MAX_ATTEMPTS = 5


class Outcome(str, Enum):
    SENT = "sent"
    SKIPPED = "skipped"  # 이미 보냈거나 다른 프로세스가 보내는 중
    FAILED = "failed"
    WOULD_SEND = "would_send"  # dry-run


def build_message(application, kind: str) -> EmailMultiAlternatives:
    context = {"a": application, "course": application.course}
    subject = SUBJECTS[kind].format(course=application.course.title)
    text = render_to_string(f"emails/{kind}.txt", context)
    html = render_to_string(f"emails/{kind}.html", context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[application.email],
    )
    message.attach_alternative(html, "text/html")
    return message


def _claim(application, kind: str) -> NotificationLog | None:
    """보낼 권리를 잡는다. 이미 보냈거나 남이 보내는 중이면 None."""
    try:
        with transaction.atomic():
            log, created = NotificationLog.objects.get_or_create(application=application, kind=kind)
    except IntegrityError:  # 동시에 만들려다 진 쪽
        return None
    if created:
        return log
    if log.status == NotificationLog.Status.SENT or log.attempts >= MAX_ATTEMPTS:
        return None
    claimable = NotificationLog.objects.filter(pk=log.pk, status=NotificationLog.Status.FAILED)
    stale_pending = NotificationLog.objects.filter(
        pk=log.pk,
        status=NotificationLog.Status.PENDING,
        created_at__lt=timezone.now() - STALE_PENDING,
    )
    if claimable.update(status=NotificationLog.Status.PENDING) or stale_pending.update(
        status=NotificationLog.Status.PENDING
    ):
        log.refresh_from_db()
        return log
    return None


def deliver(application, kind: str, *, dry_run: bool = False) -> Outcome:
    if dry_run:
        already = NotificationLog.objects.filter(
            application=application, kind=kind, status=NotificationLog.Status.SENT
        ).exists()
        return Outcome.SKIPPED if already else Outcome.WOULD_SEND

    log = _claim(application, kind)
    if log is None:
        return Outcome.SKIPPED

    log.attempts += 1
    try:
        build_message(application, kind).send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - 어떤 메일 오류든 기록하고 다음 배치에 넘긴다
        logger.warning("메일 실패 application=%s kind=%s: %s", application.pk, kind, exc)
        log.status = NotificationLog.Status.FAILED
        log.last_error = f"{type(exc).__name__}: {exc}"[:1000]
        log.save(update_fields=["status", "attempts", "last_error"])
        return Outcome.FAILED

    log.status = NotificationLog.Status.SENT
    log.sent_at = timezone.now()
    log.last_error = ""
    log.save(update_fields=["status", "attempts", "sent_at", "last_error"])
    return Outcome.SENT
