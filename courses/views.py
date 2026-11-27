from django.shortcuts import get_object_or_404, render

from .models import Course


def home(request):
    courses = Course.objects.all()
    return render(request, "courses/home.html", {"courses": courses})


def detail(request, slug):
    course = get_object_or_404(Course, slug=slug)
    return render(request, "courses/detail.html", {"course": course})
