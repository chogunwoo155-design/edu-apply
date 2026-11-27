from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, render

from applications import rules

from .models import Course, CurriculumItem


def home(request):
    courses = Course.objects.annotate(applied=Count("applications"))
    items = [(c, rules.course_availability(c, c.applied)) for c in courses]
    open_count = sum(1 for _, a in items if a.open)
    return render(request, "courses/home.html", {"items": items, "open_count": open_count})


def privacy(request):
    return render(request, "courses/privacy.html")


def detail(request, slug):
    course = get_object_or_404(
        Course.objects.annotate(applied=Count("applications")).prefetch_related(
            Prefetch("curriculum", queryset=CurriculumItem.objects.order_by("order"))
        ),
        slug=slug,
    )
    availability = rules.course_availability(course, course.applied)
    return render(request, "courses/detail.html", {"course": course, "availability": availability})
