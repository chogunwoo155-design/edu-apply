from django.conf import settings


def site(request):
    return {"DEMO_NOTICE": settings.DEMO_NOTICE}
