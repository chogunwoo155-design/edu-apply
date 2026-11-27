"""배치·자동화. 리뷰 D1~D4: 재실행 시 중복 발송, 한 건 실패하면 전체 중단, dry-run/날짜 지정/기록 없음."""

from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.management import CommandError, call_command

from applications import services
from applications.models import Application
from automation import jobs, sheets
from automation.models import JobRun, NotificationLog

from .conftest import next_contact_day


def make(course, i, contact_date, **over):
    data = services.ApplicantInput(
        name=f"신청{i}", email=f"b{i}@example.com", address="서울 영등포구 선유서로 1", contact_date=contact_date
    )
    a = services.submit_application(course.pk, data)
    if over:
        Application.objects.filter(pk=a.pk).update(**over)
        a.refresh_from_db()
    return a


@pytest.fixture
def three_due_tomorrow(courses):
    """기준일(target)과, 기준일 다음 날 연락받기로 한 신청 3건."""
    contact = next_contact_day(2)
    target = contact - timedelta(days=1)
    course = courses.get(slug="ai-problem-solving")
    apps = [make(course, i, contact) for i in range(3)]
    mail.outbox.clear()
    return target, apps


def test_reminders_sent_once_even_if_rerun(three_due_tomorrow):
    target, _ = three_due_tomorrow
    call_command("run_daily_jobs", "--date", target.isoformat(), "--only", "contact_reminders", verbosity=0)
    call_command("run_daily_jobs", "--date", target.isoformat(), "--only", "contact_reminders", verbosity=0)
    assert len(mail.outbox) == 3  # 1차: 두 번 돌리면 6통
    assert NotificationLog.objects.filter(kind="contact_reminder", status="sent").count() == 3
    second = JobRun.objects.filter(job="contact_reminders").order_by("started_at").last()
    assert second.stats["skipped"] == 3


def test_one_failure_does_not_stop_others_and_is_retried(three_due_tomorrow):
    target, apps = three_due_tomorrow
    real_send = mail.EmailMultiAlternatives.send
    calls = {"n": 0}

    def flaky(self, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionResetError("smtp hiccup")
        return real_send(self, *a, **kw)

    with mock.patch("automation.mailer.EmailMultiAlternatives.send", flaky):
        run = jobs.run_job("contact_reminders", target)
    assert run.stats == {"contact_date": (target + timedelta(days=1)).isoformat(), "sent": 2, "failed": 1}
    assert len(mail.outbox) == 2  # 1차: 두 번째에서 예외 → 세 번째는 안 감

    retry = jobs.run_job("retry_failed_notifications", target)
    assert retry.stats == {"sent": 1}
    assert len(mail.outbox) == 3
    assert not NotificationLog.objects.filter(status="failed").exists()


def test_dry_run_sends_nothing(three_due_tomorrow):
    target, _ = three_due_tomorrow
    call_command("run_daily_jobs", "--date", target.isoformat(), "--dry-run", verbosity=0)
    assert mail.outbox == []
    assert not NotificationLog.objects.filter(kind="contact_reminder").exists()
    run = JobRun.objects.get(job="contact_reminders")
    assert run.dry_run and run.stats["would_send"] == 3


def test_done_applications_are_not_reminded(three_due_tomorrow):
    target, apps = three_due_tomorrow
    services.change_status(apps[0], Application.Status.DONE)
    run = jobs.run_job("contact_reminders", target)
    assert run.stats["sent"] == 2


def test_staff_digest_lists_today_and_stale_once_per_day(courses, settings):
    settings.STAFF_NOTIFY_EMAILS = ["staff@example.com"]
    contact = next_contact_day(2)
    course = courses.get(slug="ai-problem-solving")
    make(course, 1, contact)
    stale = make(course, 2, contact)
    Application.objects.filter(pk=stale.pk).update(created_at=stale.created_at - timedelta(days=10))
    mail.outbox.clear()

    first = jobs.run_job("staff_digest", contact)
    assert first.stats["today_contacts"] == 2 and first.stats["stale"] == 1 and first.stats["sent"]
    assert "연락 2건" in mail.outbox[0].subject
    again = jobs.run_job("staff_digest", contact)
    assert again.stats == {"skipped": "오늘 이미 성공"}
    assert len(mail.outbox) == 1


def test_failed_job_recorded_and_command_exits_nonzero(courses):
    with mock.patch.dict(jobs.JOBS, {"contact_reminders": mock.Mock(side_effect=RuntimeError("boom"))}):
        with pytest.raises(CommandError):
            call_command("run_daily_jobs", "--only", "contact_reminders", verbosity=0)
    run = JobRun.objects.get()
    assert run.status == JobRun.Status.FAILED and "boom" in run.error and run.finished_at


def test_export_sheet_skips_without_config(courses, monkeypatch):
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    run = jobs.run_job("export_sheet", next_contact_day(1))
    assert run.status == JobRun.Status.SUCCESS and "skipped" in run.stats


def test_export_sheet_writes_snapshot(courses, monkeypatch):
    course = courses.get(slug="ai-problem-solving")
    make(course, 1, next_contact_day(2))
    written = {}

    class FakeWriter:
        def replace_all(self, rows):
            written["rows"] = rows

    monkeypatch.setattr(sheets, "is_configured", lambda: True)
    monkeypatch.setattr(sheets, "get_writer", lambda: FakeWriter())
    run = jobs.run_job("export_sheet", next_contact_day(1))
    assert run.stats == {"rows": 1}
    assert written["rows"][0][3] == "신청1"
