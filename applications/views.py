import csv
from datetime import date

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from automation import sheets
from automation.jobs import run_job
from automation.models import JobRun
from courses.models import Course

from . import receipts, rules, selectors, services
from .models import Application


def apply(request, slug):
    course = get_object_or_404(Course, slug=slug)
    availability = rules.course_availability(course, services.active_application_count(course))
    return render(
        request,
        "applications/apply.html",
        {
            "course": course,
            "availability": availability,
            "date_choices": rules.contact_date_choices(),
            "date_bounds": rules.contact_date_bounds(),
            "contact_times": Application.ContactTime.choices,
        },
    )


def receipt(request, token):
    pk = receipts.read_token(token)
    application = get_object_or_404(Application.objects.select_related("course"), pk=pk) if pk else None
    if application is None:
        return render(request, "applications/receipt_expired.html", status=404)
    response = render(request, "applications/receipt.html", {"a": application, "course": application.course})
    response["Referrer-Policy"] = "no-referrer"  # 토큰이 든 주소가 외부로 새지 않게
    response["X-Robots-Tag"] = "noindex"
    return response


# ---------------- 관리 화면 ----------------


def _filters(request) -> dict:
    contact = request.GET.get("contact_date")
    try:
        contact_date = date.fromisoformat(contact) if contact else None
    except ValueError:
        contact_date = None
    return {
        "status": request.GET.get("status") or None,
        "course": request.GET.get("course") or None,
        "q": request.GET.get("q") or None,
        "contact_date": contact_date,
        "when": request.GET.get("when") if request.GET.get("when") in selectors.WHEN else None,
        "sort": request.GET.get("sort") if request.GET.get("sort") in selectors.SORTS else None,
    }


@staff_member_required
def manage_list(request):
    filters = _filters(request)
    qs = selectors.application_list(**filters)
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    counts = selectors.status_counts(selectors.application_list(**{**filters, "status": None}))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "manage/list.html",
        {
            "page": page,
            "filters": filters,
            "counts": counts,
            "todo": selectors.todo_counts(),
            "statuses": Application.Status.choices,
            "courses": Course.objects.order_by("title"),
            "when_labels": selectors.WHEN,
            "query_without_page": query.urlencode(),
            "query_without_status": _without(request, "status", "page"),
            "sheets_ready": sheets.is_configured(),
            "last_run": JobRun.objects.filter(dry_run=False).first(),
        },
    )


def _without(request, *keys) -> str:
    query = request.GET.copy()
    for k in keys:
        query.pop(k, None)
    return query.urlencode()


@staff_member_required
@require_POST
def manage_change_status(request, pk):
    """JS가 꺼져 있을 때를 위한 폼 제출용. 화면에서는 API(PATCH)를 부른다."""
    application = get_object_or_404(Application, pk=pk)
    try:
        services.change_status(application, request.POST.get("status", ""), by=request.user)
        messages.success(request, f"{application.name}님 신청을 '{application.get_status_display()}'(으)로 바꿨어요.")
    except services.ApplicationError as e:
        return HttpResponse(e.message, status=400)
    return redirect(_safe_next(request))


def _safe_next(request) -> str:
    nxt = request.POST.get("next", "")
    return nxt if nxt.startswith("/manage/") else "/manage/"


CSV_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(value) -> str:
    """엑셀에서 열었을 때 수식으로 실행되지 않게 막는다 (CSV injection)."""
    value = "" if value is None else str(value)
    return "'" + value if value.startswith(CSV_DANGEROUS) else value


@staff_member_required
def manage_export_csv(request):
    rows = sheets.application_rows(selectors.application_list(**_filters(request)).order_by("created_at"))
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response["Content-Disposition"] = f'attachment; filename="applications-{stamp}.csv"'
    response.write("﻿")  # 엑셀이 한글을 깨뜨리지 않게 BOM
    writer = csv.writer(response)
    writer.writerow(sheets.HEADER)
    for row in rows:
        writer.writerow([_csv_cell(c) for c in row])
    return response


@staff_member_required
@require_POST
def manage_export_sheet(request):
    run = run_job("export_sheet", rules.today(), trigger=JobRun.Trigger.MANUAL)
    if run.status == JobRun.Status.SUCCESS and "rows" in run.stats:
        messages.success(request, f"구글 시트에 {run.stats['rows']}건을 내보냈어요.")
    elif run.status == JobRun.Status.SUCCESS:
        messages.info(request, run.stats.get("skipped", "내보낼 설정이 없어요."))
    else:
        messages.error(request, f"내보내기에 실패했어요: {run.error}")
    return redirect("manage:list")


@staff_member_required
def manage_jobs(request):
    runs = JobRun.objects.all()[:100]
    return render(request, "manage/jobs.html", {"runs": runs})
