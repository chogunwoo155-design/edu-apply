"""관리 화면. 리뷰 A1·M1·M2: 상태값 검증 없음, 값 없으면 500, 필터 풀림, CSV 수식 실행."""

import pytest

from applications import rules, services
from applications.models import Application

from .conftest import next_contact_day


@pytest.fixture
def one(courses):
    data = services.ApplicantInput(name="=HYPERLINK(1)", email="m@example.com", address="서울 영등포구 1", contact_date=next_contact_day(2))
    return services.submit_application(courses.get(slug="ai-problem-solving").pk, data)


def test_manage_requires_staff(client, one, django_user_model):
    assert client.get("/manage/").status_code == 302
    user = django_user_model.objects.create_user("plain", password="x-test-pass")
    client.force_login(user)
    assert client.get("/manage/").status_code == 302


def test_manage_list_filters_and_counts(client, staff_user, one):
    client.force_login(staff_user)
    res = client.get("/manage/?status=received&q=m@example")
    assert res.status_code == 200
    assert res.context["counts"]["received"] == 1
    assert list(res.context["page"].object_list) == [one]


def test_form_status_change_validates(client, staff_user, one):
    client.force_login(staff_user)
    assert client.post(f"/manage/{one.pk}/status/", {"status": "hacked"}).status_code == 400
    assert client.post(f"/manage/{one.pk}/status/", {}).status_code == 400  # 1차: KeyError 500
    res = client.post(f"/manage/{one.pk}/status/", {"status": "done", "next": "/manage/?status=received"})
    assert res.status_code == 302 and res.url == "/manage/?status=received"  # 필터 유지
    one.refresh_from_db()
    assert one.status == Application.Status.DONE


def test_open_redirect_blocked(client, staff_user, one):
    client.force_login(staff_user)
    res = client.post(f"/manage/{one.pk}/status/", {"status": "done", "next": "https://evil.example"})
    assert res.url == "/manage/"


def test_csv_export_neutralizes_formulas(client, staff_user, one):
    client.force_login(staff_user)
    res = client.get("/manage/export.csv")
    text = res.content.decode("utf-8-sig")
    assert "'=HYPERLINK(1)" in text
    assert text.splitlines()[0].startswith("신청번호")


def test_jobs_page(client, staff_user):
    client.force_login(staff_user)
    assert client.get("/manage/jobs/").status_code == 200


def test_rules_use_korean_today_not_utc(monkeypatch):
    """1차 apply.js는 toISOString()(UTC)으로 최소 날짜를 잡아 KST 0~9시에 하루 어긋났다."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from django.utils import timezone

    kst_0030 = datetime(2026, 12, 1, 0, 30, tzinfo=ZoneInfo("Asia/Seoul"))  # UTC로는 11/30 15:30
    monkeypatch.setattr(timezone, "now", lambda: kst_0030)
    assert rules.today().isoformat() == "2026-12-01"
    first, _ = rules.contact_date_bounds()
    assert first.isoformat() == "2026-12-02"
