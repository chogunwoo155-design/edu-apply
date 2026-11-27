import pytest
from datetime import timedelta
from django.utils import timezone
from django.core.management import call_command
from rest_framework.test import APIClient
from applications.models import Application
pytestmark = pytest.mark.django_db

def test_email_case(django_user_model):
    call_command("seed_sample", verbosity=0)
    d = {"course": "ai-problem-solving", "name": "김신청", "email": "A@Example.COM", "address": "서울",
         "contact_date": (timezone.localdate() + timedelta(days=2)).isoformat()}
    r = APIClient().post("/api/applications/", d, format="json")
    print("email stored ->", Application.objects.get(pk=r.json()["id"]).email)
    staff = django_user_model.objects.create_user("s", password="x", is_staff=True)
    api = APIClient(); api.force_authenticate(staff)
    r2 = api.patch(f"/api/applications/{r.json()['id']}/", {"contact_date": "2000-01-01", "status": "nope"}, format="json")
    print("staff patch past+bad status ->", r2.status_code, r2.content[:120])
    r3 = api.patch(f"/api/applications/{r.json()['id']}/", {"contact_date": "2000-01-01"}, format="json")
    print("staff patch past date ->", r3.status_code)
