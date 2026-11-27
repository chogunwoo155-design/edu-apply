from datetime import timedelta

from django.core import mail
from django.utils import timezone

from applications.models import Application


def payload(**over):
    data = {
        "course": "ai-problem-solving",
        "name": "김신청",
        "email": "apply@example.com",
        "address": "서울 영등포구 선유서로 1",
        "contact_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
    }
    data.update(over)
    return data


def test_course_list_is_public(api, courses):
    res = api.get("/api/courses/")
    assert res.status_code == 200
    assert res.json()["count"] == 3
    assert len(res.json()["results"][0]["curriculum"]) > 0


def test_anyone_can_apply_and_gets_mail(api, courses):
    res = api.post("/api/applications/", payload(), format="json")
    assert res.status_code == 201, res.json()
    assert res.json()["status"] == "received"
    assert Application.objects.count() == 1
    assert len(mail.outbox) == 1


def test_past_contact_date_rejected(api, courses):
    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    res = api.post("/api/applications/", payload(contact_date=yesterday), format="json")
    assert res.status_code == 400
    assert "contact_date" in res.json()


def test_closed_course_rejected(api, courses):
    courses.filter(slug="ai-problem-solving").update(is_open=False)
    res = api.post("/api/applications/", payload(), format="json")
    assert res.status_code == 400


def test_list_requires_staff(api, admin_api, courses):
    api.post("/api/applications/", payload(), format="json")
    assert api.get("/api/applications/").status_code == 403
    assert admin_api.get("/api/applications/").json()["count"] == 1


def test_staff_can_update_and_delete(admin_api, api, courses):
    created = api.post("/api/applications/", payload(), format="json").json()
    res = admin_api.patch(f"/api/applications/{created['id']}/", {"status": "reviewing"}, format="json")
    assert res.status_code == 200 and res.json()["status"] == "reviewing"
    assert admin_api.delete(f"/api/applications/{created['id']}/").status_code == 204
