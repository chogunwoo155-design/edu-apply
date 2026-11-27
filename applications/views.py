from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from courses.models import Course

from .models import Application


def apply(request, slug):
    course = get_object_or_404(Course, slug=slug)
    return render(request, "applications/apply.html", {"course": course})


@staff_member_required
def manage_list(request):
    applications = Application.objects.all()
    status = request.GET.get("status")
    if status:
        applications = applications.filter(status=status)
    return render(
        request,
        "manage/list.html",
        {
            "applications": applications,
            "statuses": Application.Status.choices,
            "current_status": status,
        },
    )


@staff_member_required
@require_POST
def manage_change_status(request, pk):
    application = get_object_or_404(Application, pk=pk)
    application.status = request.POST["status"]
    application.save()
    return redirect("manage:list")
