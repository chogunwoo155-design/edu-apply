"""
매일 돌리는 배치 작업들.

각 작업은 (기준 날짜, dry_run)을 받아 처리 결과(dict)를 돌려준다.
run_job()이 JobRun 기록·예외 처리를 감싸므로, 작업 함수는 자기 일만 한다.
날짜를 인자로 받기 때문에 지난 날짜로 다시 돌리거나(--date) 테스트하기 쉽다.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Callable

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from applications.models import Application

from . import sheets
from .mailer import MAX_ATTEMPTS, deliver
from .models import JobRun, NotificationLog

logger = logging.getLogger(__name__)

STALE_DAYS = 3  # '접수' 상태로 이만큼 지나면 담당자 요약에 '확인 필요'로 올린다

JobFunc = Callable[[date, bool], dict]


def contact_reminders(target_date: date, dry_run: bool) -> dict:
    """연락 가능 날짜가 내일인 신청자에게 '내일 연락드려요' 메일."""
    tomorrow = target_date + timedelta(days=1)
    targets = (
        Application.objects.select_related("course")
        .filter(contact_date=tomorrow)
        .exclude(status=Application.Status.DONE)
    )
    counts = Counter(deliver(a, NotificationLog.Kind.CONTACT_REMINDER, dry_run=dry_run).value for a in targets)
    return {"contact_date": tomorrow.isoformat(), **counts}


def retry_failed_notifications(target_date: date, dry_run: bool) -> dict:
    """지난번에 실패한 메일(접수 확인 포함)을 다시 보낸다."""
    failed = NotificationLog.objects.select_related("application__course").filter(
        status=NotificationLog.Status.FAILED, attempts__lt=MAX_ATTEMPTS
    )
    counts = Counter(deliver(log.application, log.kind, dry_run=dry_run).value for log in failed)
    return dict(counts)


def staff_digest(target_date: date, dry_run: bool) -> dict:
    """담당자에게: 오늘 연락할 신청자 + 오래 방치된 '접수' 건."""
    recipients = settings.STAFF_NOTIFY_EMAILS
    if not recipients:
        return {"skipped": "STAFF_NOTIFY_EMAILS 미설정"}

    today_contacts = list(
        Application.objects.select_related("course")
        .filter(contact_date=target_date)
        .exclude(status=Application.Status.DONE)
        .order_by("course__title", "name")
    )
    stale_before = timezone.make_aware(datetime.combine(target_date - timedelta(days=STALE_DAYS), time.min))
    stale = list(
        Application.objects.select_related("course")
        .filter(status=Application.Status.RECEIVED, created_at__lt=stale_before)
        .order_by("created_at")
    )
    stats = {"today_contacts": len(today_contacts), "stale": len(stale), "recipients": len(recipients)}
    if dry_run or not (today_contacts or stale):
        return {**stats, "sent": False}

    body = render_to_string(
        "emails/staff_digest.txt",
        {"date": target_date, "today_contacts": today_contacts, "stale": stale, "stale_days": STALE_DAYS},
    )
    send_mail(
        subject=f"[신청 관리] {target_date:%m/%d} 연락 {len(today_contacts)}건 · 확인 필요 {len(stale)}건",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
    )
    return {**stats, "sent": True}


def export_sheet(target_date: date, dry_run: bool) -> dict:
    """전체 신청 목록을 Google Spreadsheet에 덮어쓴다."""
    if not sheets.is_configured():
        return {"skipped": "Google Sheets 미설정"}
    rows = sheets.application_rows(Application.objects.select_related("course").order_by("created_at"))
    if not dry_run:
        sheets.get_writer().replace_all(rows)
    return {"rows": len(rows)}


# 실행 순서대로. 실패한 메일 재시도를 먼저 해서 오늘 요약에 반영되게 한다.
JOBS: dict[str, JobFunc] = {
    "retry_failed_notifications": retry_failed_notifications,
    "contact_reminders": contact_reminders,
    "staff_digest": staff_digest,
    "export_sheet": export_sheet,
}

# 하루에 한 번만 성공하면 되는 작업 (다시 돌려도 건너뜀, --force로 강제)
ONCE_PER_DAY = {"staff_digest"}


def run_job(
    name: str,
    target_date: date,
    *,
    dry_run: bool = False,
    trigger: str = JobRun.Trigger.SCHEDULE,
    force: bool = False,
) -> JobRun:
    func = JOBS[name]
    if (
        name in ONCE_PER_DAY
        and not force
        and not dry_run
        and JobRun.objects.filter(job=name, target_date=target_date, status=JobRun.Status.SUCCESS, dry_run=False).exists()
    ):
        return JobRun.objects.create(
            job=name,
            target_date=target_date,
            trigger=trigger,
            status=JobRun.Status.SUCCESS,
            stats={"skipped": "오늘 이미 성공"},
            finished_at=timezone.now(),
        )

    run = JobRun.objects.create(job=name, target_date=target_date, trigger=trigger, dry_run=dry_run)
    try:
        run.stats = func(target_date, dry_run)
        run.status = JobRun.Status.SUCCESS
    except Exception as exc:  # noqa: BLE001 - 한 작업이 실패해도 다음 작업은 돈다
        logger.exception("배치 실패: %s", name)
        run.status = JobRun.Status.FAILED
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
    run.finished_at = timezone.now()
    run.save()
    return run
