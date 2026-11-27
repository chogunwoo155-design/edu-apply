import pytest
from django.core.management import call_command
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def courses(db):
    call_command("seed_sample", verbosity=0)
    from courses.models import Course

    return Course.objects.order_by("id")


@pytest.fixture
def admin_api(db, django_user_model):
    user = django_user_model.objects.create_user("staff", password="x-test-pass", is_staff=True)
    client = APIClient()
    client.force_authenticate(user)
    return client
