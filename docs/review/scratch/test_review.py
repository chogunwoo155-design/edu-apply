from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from applications.models import Application
from courses.models import Course

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    call_command("seed_sample", verbosity=0)


@pytest.fixture
def staff(django_user_model):
    return django_user_model.objects.create_user("s", password="x", is_staff=True)


def payload(**over):
    d = {"course": "ai-problem-solving", "name": "김신청", "email": "a@example.com",
         "address": "서울", "contact_date": (timezone.localdate() + timedelta(days=2)).isoformat()}
    d.update(over)
    return d


def test_manage_status_arbitrary_value(client, staff, seeded):
    a = APIClient().post("/api/applications/", payload(), format="json").json()
    client.force_login(staff)
    r = client.post(f"/manage/{a['id']}/status/", {"status": "hacked-value"})
    print("arbitrary status ->", r.status_code, Application.objects.get(pk=a["id"]).status)


def test_manage_status_missing_key(client, staff, seeded):
    a = APIClient().post("/api/applications/", payload(), format="json").json()
    client.force_login(staff)
    client.raise_request_exception = False
    r = client.post(f"/manage/{a['id']}/status/", {})
    print("missing status ->", r.status_code)


def test_deadline_passed_still_accepts(seeded):
    Course.objects.filter(slug="ai-problem-solving").update(apply_deadline=timezone.localdate() - timedelta(days=5))
    r = APIClient().post("/api/applications/", payload(), format="json")
    print("deadline passed ->", r.status_code)


def test_capacity_not_enforced(seeded):
    Course.objects.filter(slug="ai-problem-solving").update(capacity=1)
    codes = [APIClient().post("/api/applications/", payload(email=f"x{i}@e.com"), format="json").status_code for i in range(3)]
    print("capacity=1 ->", codes)


def test_duplicate_same_person(seeded):
    codes = [APIClient().post("/api/applications/", payload(), format="json").status_code for _ in range(3)]
    print("dup ->", codes, Application.objects.count(), "mails", len(mail.outbox))


def test_today_contact_date_allowed(seeded):
    r = APIClient().post("/api/applications/", payload(contact_date=timezone.localdate().isoformat()), format="json")
    print("today ->", r.status_code)


def test_mail_failure_leaves_row(seeded):
    c = APIClient(raise_request_exception=False)
    with mock.patch("applications.api.send_mail", side_effect=ConnectionRefusedError("smtp down")):
        r = c.post("/api/applications/", payload(), format="json")
    print("smtp down ->", r.status_code, r.get("Content-Type"), "rows", Application.objects.count())


def test_no_throttle(seeded):
    codes = {APIClient().post("/api/applications/", payload(email=f"victim{i}@e.com"), format="json").status_code for i in range(30)}
    print("30 posts ->", codes, "mails", len(mail.outbox))


def test_reminder_rerun_duplicates(seeded):
    today = timezone.localdate()
    c = Course.objects.first()
    for i in range(3):
        Application.objects.create(course=c, name="n", email=f"r{i}@e.com", address="a", contact_date=today)
    call_command("send_contact_reminders")
    call_command("send_contact_reminders")
    print("rerun mails ->", len(mail.outbox))


def test_reminder_nplus1(seeded):
    today = timezone.localdate()
    c = Course.objects.first()
    for i in range(5):
        Application.objects.create(course=c, name="n", email=f"r{i}@e.com", address="a", contact_date=today)
    with CaptureQueriesContext(connection) as q:
        call_command("send_contact_reminders")
    print("reminder queries for 5 ->", len(q))


def test_reminder_one_failure_aborts(seeded):
    today = timezone.localdate()
    c = Course.objects.first()
    for i in range(3):
        Application.objects.create(course=c, name="n", email=f"r{i}@e.com", address="a", contact_date=today)
    calls = {"n": 0}
    def boom(**kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ConnectionResetError("x")
    with mock.patch("applications.management.commands.send_contact_reminders.send_mail", side_effect=boom):
        try:
            call_command("send_contact_reminders")
            print("no exception")
        except Exception as e:
            print("reminder aborted at", calls["n"], type(e).__name__)


def test_list_nplus1(client, staff, seeded):
    cs = list(Course.objects.all())
    for i in range(20):
        Application.objects.create(course=cs[i % 3], name="n", email=f"l{i}@e.com", address="a", contact_date=timezone.localdate())
    client.force_login(staff)
    with CaptureQueriesContext(connection) as q:
        client.get("/manage/")
    print("manage list 20 rows queries ->", len(q))
    api = APIClient(); api.force_authenticate(staff)
    with CaptureQueriesContext(connection) as q:
        api.get("/api/applications/")
    print("api list 20 rows queries ->", len(q))
    with CaptureQueriesContext(connection) as q:
        api.get("/api/courses/")
    print("api courses queries ->", len(q))
    with CaptureQueriesContext(connection) as q:
        client.get("/admin/applications/application/")
    print("admin list queries ->", len(q))


def test_staff_patch_validation(staff, seeded):
    a = APIClient().post("/api/applications/", payload(), format="json").json()
    api = APIClient(); api.force_authenticate(staff)
    r = api.patch(f"/api/applications/{a['id']}/", {"name": " ", "contact_date": "2000-01-01"}, format="json")
    print("staff patch blank name/past ->", r.status_code, r.json() if r.status_code != 200 else Application.objects.get(pk=a['id']).name)
    r = api.patch(f"/api/applications/{a['id']}/", {"name": "x"}, format="json")
    print("staff patch 1-char name ->", r.status_code)


def test_name_whitespace_and_control(seeded):
    r = APIClient().post("/api/applications/", payload(name="가\n나\r\n다"), format="json")
    print("name with newlines ->", r.status_code, repr(Application.objects.last().name) if r.status_code == 201 else r.json())
    r = APIClient().post("/api/applications/", payload(address="   "), format="json")
    print("blank address ->", r.status_code)
    r = APIClient().post("/api/applications/", payload(postcode="abcde"), format="json")
    print("postcode abcde ->", r.status_code)
    r = APIClient().post("/api/applications/", payload(email="A@Example.COM"), format="json")
    print("email stored ->", Application.objects.last().email)


def test_far_future_date(seeded):
    r = APIClient().post("/api/applications/", payload(contact_date="9999-12-31"), format="json")
    print("9999-12-31 ->", r.status_code)


def test_status_filter_bad(staff, seeded):
    api = APIClient(); api.force_authenticate(staff)
    print("bad status filter ->", api.get("/api/applications/?status=zzz").status_code)


def test_staff_logged_in_post_without_csrf(staff, seeded):
    api = APIClient(enforce_csrf_checks=True)
    api.login(username="s", password="x")
    r = api.post("/api/applications/", payload(), format="json")
    print("staff session w/o csrf ->", r.status_code)
