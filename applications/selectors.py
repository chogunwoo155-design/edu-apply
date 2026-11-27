"""조회 전용 함수. 관리 화면 · API · 내보내기가 같은 필터를 쓴다."""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Count, Q, QuerySet

from . import rules
from .models import Application

WHEN = {"today": "오늘 연락", "overdue": "연락일 지남", "week": "7일 안"}
SORTS = {"contact": ("contact_date", "created_at"), "new": ("-created_at",)}


def application_list(
    *,
    status: str | None = None,
    course: str | None = None,
    q: str | None = None,
    contact_date: date | None = None,
    when: str | None = None,
    sort: str | None = None,
) -> QuerySet[Application]:
    qs = Application.objects.select_related("course").order_by(*SORTS.get(sort or "", SORTS["new"]))
    today = rules.today()
    if when == "today":
        qs = qs.filter(contact_date=today).exclude(status=Application.Status.DONE)
    elif when == "overdue":
        qs = qs.filter(contact_date__lt=today).exclude(status=Application.Status.DONE)
    elif when == "week":
        qs = qs.filter(contact_date__range=(today, today + timedelta(days=7))).exclude(status=Application.Status.DONE)
    if status in Application.Status.values:
        qs = qs.filter(status=status)
    if course:
        qs = qs.filter(course__slug=course)
    if contact_date:
        qs = qs.filter(contact_date=contact_date)
    if q:
        q = q.strip()
        cond = Q(name__icontains=q) | Q(email__icontains=q) | Q(address__icontains=q)
        if q.upper().startswith("HS") and "-" in q:  # 신청번호로 찾기: HS261127-0042
            tail = q.rsplit("-", 1)[-1]
            if tail.isdigit():
                cond |= Q(pk=int(tail))
        qs = qs.filter(cond)
    return qs


def todo_counts() -> dict[str, int]:
    """관리 화면 위 요약 카드: 오늘 연락할 사람, 연락일이 지났는데 끝나지 않은 사람, 오늘 들어온 신청."""
    today = rules.today()
    open_ = Application.objects.exclude(status=Application.Status.DONE)
    return {
        "today": open_.filter(contact_date=today).count(),
        "overdue": open_.filter(contact_date__lt=today).count(),
        "new_today": Application.objects.filter(created_at__date=today).count(),
    }


def status_counts(qs: QuerySet[Application] | None = None) -> dict[str, int]:
    qs = Application.objects.all() if qs is None else qs
    agg = qs.aggregate(
        total=Count("id"),
        **{s: Count("id", filter=Q(status=s)) for s in Application.Status.values},
    )
    return agg
