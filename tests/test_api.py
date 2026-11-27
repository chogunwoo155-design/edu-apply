"""공개 API · 관리자 API. 1차 6개 + 리뷰에서 나온 결함의 회귀 테스트."""

from datetime import timedelta
from unittest import mock

from django.core import mail
from django.db import connection
from django.test.utils import CaptureQueriesContext

from applications import rules
from applications.models import Application
from automation.models import NotificationLog

from .conftest import next_contact_day, payload


def test_course_list_is_public_without_n_plus_1(api, courses):
    with CaptureQueriesContext(connection) as ctx:
        res = api.get("/api/courses/")
    assert res.status_code == 200
    assert res.json()["count"] == 3
    assert len(res.json()["results"][0]["curriculum"]) > 0
    assert len(ctx) <= 3  # count + 교육 + 커리큘럼(prefetch). 1차는 교육 수만큼 늘었다


def test_anyone_can_apply_and_gets_receipt_and_mail(api, courses, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        res = api.post("/api/applications/", payload(), format="json")
    assert res.status_code == 201, res.json()
    body = res.json()
    assert body["reference"].startswith("HS")
    assert body["status"] == "received"
    assert "address" not in body  # 접수증에 주소를 되돌려주지 않는다
    assert len(mail.outbox) == 1
    assert mail.outbox[0].alternatives  # HTML 본문 포함
    assert NotificationLog.objects.get().status == NotificationLog.Status.SENT


def test_mail_failure_does_not_fail_the_application(api, courses, django_capture_on_commit_callbacks):
    """1차: SMTP가 죽으면 신청은 저장된 채 500 → 사용자가 다시 눌러 중복. (리뷰 D5)"""
    with mock.patch("automation.mailer.EmailMultiAlternatives.send", side_effect=ConnectionResetError("smtp down")):
        with django_capture_on_commit_callbacks(execute=True):
            res = api.post("/api/applications/", payload(), format="json")
    assert res.status_code == 201
    log = NotificationLog.objects.get()
    assert log.status == NotificationLog.Status.FAILED and "smtp down" in log.last_error


def test_duplicate_application_rejected_case_insensitive(api, courses):
    """리뷰 C1: 같은 사람·같은 교육 중복 허용."""
    assert api.post("/api/applications/", payload(), format="json").status_code == 201
    res = api.post("/api/applications/", payload(email="APPLY@Example.com"), format="json")
    assert res.status_code == 400
    assert "email" in res.json()
    assert Application.objects.count() == 1


def test_same_email_can_apply_to_another_course(api, courses):
    api.post("/api/applications/", payload(), format="json")
    res = api.post("/api/applications/", payload(course="digital-literacy"), format="json")
    assert res.status_code == 201


def test_contact_date_rules(api, courses):
    today = rules.today()
    cases = {
        today: 400,  # 오늘은 안 됨 (아침 배치 뒤 신청은 안내를 못 받음, 리뷰 A3)
        today - timedelta(days=1): 400,
        today + timedelta(days=rules.CONTACT_WINDOW_DAYS + 7): 400,  # 상한 (리뷰 A5)
    }
    saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    cases[saturday] = 400  # 주말
    for i, (d, code) in enumerate(cases.items()):
        res = api.post("/api/applications/", payload(email=f"d{i}@example.com", contact_date=d.isoformat()), format="json")
        assert res.status_code == code, (d, res.json())
        assert "contact_date" in res.json()


def test_error_messages_are_korean_sentences(api, courses):
    """리뷰 UX F2: 'blank일 수 없습니다' 같은 DRF 기본 번역이 그대로 나왔다."""
    res = api.post("/api/applications/", {"course": "ai-problem-solving", "privacy_agreed": True}, format="json")
    assert res.status_code == 400
    text = str(res.json())
    assert "blank" not in text and "필드" not in text and "포멧" not in text
    assert "학생 이름을 적어 주세요" in text


def test_privacy_consent_required(api, courses):
    res = api.post("/api/applications/", payload(privacy_agreed=False), format="json")
    assert res.status_code == 400 and "privacy_agreed" in res.json()


def test_closed_course_deadline_and_capacity(api, courses):
    """리뷰 A2: is_open만 보고 마감일·정원은 무시했다."""
    course = courses.get(slug="ai-problem-solving")
    course.apply_deadline = rules.today() - timedelta(days=1)
    course.save()
    assert api.post("/api/applications/", payload(), format="json").status_code == 400

    course.apply_deadline = None
    course.capacity = 1
    course.save()
    assert api.post("/api/applications/", payload(email="a1@example.com"), format="json").status_code == 201
    res = api.post("/api/applications/", payload(email="a2@example.com"), format="json")
    assert res.status_code == 400 and "정원" in str(res.json())


def test_control_characters_and_postcode_validated(api, courses):
    res = api.post("/api/applications/", payload(name="가\n나"), format="json")
    assert res.status_code == 400 and "name" in res.json()
    res = api.post("/api/applications/", payload(postcode="abcde"), format="json")
    assert res.status_code == 400 and "postcode" in res.json()


def test_honeypot_blocks_bots(api, courses):
    res = api.post("/api/applications/", payload(website="http://spam"), format="json")
    assert res.status_code == 400


def test_public_create_is_rate_limited(api, courses):
    """리뷰 B1: 익명 POST 무제한 → 남의 주소로 메일 폭탄."""
    from rest_framework.throttling import SimpleRateThrottle

    with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", {"applications": "3/hour"}):
        codes = [
            api.post("/api/applications/", payload(email=f"r{i}@example.com"), format="json").status_code
            for i in range(4)
        ]
    assert codes == [201, 201, 201, 429]


def test_list_requires_staff_and_searches_without_n_plus_1(api, admin_api, courses):
    for i in range(5):
        api.post("/api/applications/", payload(email=f"s{i}@example.com", name=f"검색{i}"), format="json")
    assert api.get("/api/applications/").status_code == 403
    with CaptureQueriesContext(connection) as ctx:
        res = admin_api.get("/api/applications/?q=검색3")
    assert res.json()["count"] == 1
    assert len(ctx) <= 4  # 1차: 행마다 교육 조회 (리뷰 E2)


def test_staff_patch_status_goes_through_service_and_logs(admin_api, api, courses, staff_user):
    api.post("/api/applications/", payload(), format="json")
    a = Application.objects.get()
    res = admin_api.patch(f"/api/applications/{a.pk}/", {"status": "reviewing", "admin_memo": "전화 예정"}, format="json")
    assert res.status_code == 200 and res.json()["status"] == "reviewing"
    log = a.status_logs.get()
    assert (log.from_status, log.to_status, log.changed_by) == ("received", "reviewing", staff_user)


def test_staff_patch_rejects_invalid_status_and_past_date(admin_api, api, courses):
    api.post("/api/applications/", payload(), format="json")
    a = Application.objects.get()
    assert admin_api.patch(f"/api/applications/{a.pk}/", {"status": "hacked"}, format="json").status_code == 400
    past = (rules.today() - timedelta(days=3)).isoformat()
    assert admin_api.patch(f"/api/applications/{a.pk}/", {"contact_date": past}, format="json").status_code == 400


def test_staff_can_delete_and_get_summary(admin_api, api, courses):
    api.post("/api/applications/", payload(), format="json")
    a = Application.objects.get()
    assert admin_api.get("/api/applications/summary/").json()["received"] == 1
    assert admin_api.delete(f"/api/applications/{a.pk}/").status_code == 204


def test_next_contact_day_helper_skips_weekends():
    d = next_contact_day(1)
    assert d.weekday() < 5
