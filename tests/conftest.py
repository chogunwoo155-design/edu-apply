from datetime import date, timedelta

import pytest
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APIClient

from applications import rules


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()  # 요청 제한(throttle) 카운터가 테스트끼리 섞이지 않게
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def courses(db):
    call_command("seed_sample", verbosity=0)
    from courses.models import Course

    return Course.objects.order_by("id")


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user("staff", password="x-test-pass", is_staff=True)


@pytest.fixture
def admin_api(staff_user):
    client = APIClient()
    client.force_authenticate(staff_user)
    return client


def next_contact_day(after: int = 1, base: date | None = None) -> date:
    """오늘(KST)부터 after일 뒤 이후의 첫 평일."""
    d = (base or rules.today()) + timedelta(days=after)
    while not rules.is_contact_day(d):
        d += timedelta(days=1)
    return d


def payload(**over):
    data = {
        "course": "ai-problem-solving",
        "name": "김신청",
        "email": "apply@example.com",
        "address": "서울 영등포구 선유서로 1",
        "contact_date": next_contact_day(2).isoformat(),
        "privacy_agreed": True,
    }
    data.update(over)
    return data
