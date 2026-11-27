"""
신청 규칙. 화면(날짜 칩), API 검증, 배치가 모두 이 한 곳을 본다.

날짜는 전부 한국 시간(settings.TIME_ZONE) 기준의 '오늘'에서 계산한다.
브라우저 시계나 UTC로 계산하지 않는다 (1차에서 KST 0~9시에 하루가 어긋나던 버그).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone

CONTACT_WINDOW_DAYS = 30  # 오늘부터 며칠 안에서 연락 날짜를 고를 수 있나
DATE_CHIP_COUNT = 10  # 신청 화면에 칩으로 보여 줄 날짜 수


def today() -> date:
    return timezone.localdate()


def is_contact_day(d: date) -> bool:
    """담당자가 연락하는 날: 평일(월~금). 공휴일은 운영 정책이 정해지면 여기서 뺀다."""
    return d.weekday() < 5


def contact_date_bounds(base: date | None = None) -> tuple[date, date]:
    """
    고를 수 있는 연락 날짜 범위. 가장 빠른 날은 '내일'.
    오늘을 허용하면 아침 배치 뒤에 들어온 신청은 안내 메일을 못 받는다.
    """
    base = base or today()
    return base + timedelta(days=1), base + timedelta(days=CONTACT_WINDOW_DAYS)


def contact_date_error(d: date, base: date | None = None) -> str | None:
    first, last = contact_date_bounds(base)
    if d < first:
        return "내일 이후 날짜를 골라 주세요."
    if d > last:
        return f"{CONTACT_WINDOW_DAYS}일 안의 날짜를 골라 주세요."
    if not is_contact_day(d):
        return "주말에는 연락드리기 어려워요. 평일을 골라 주세요."
    return None


def contact_date_choices(base: date | None = None, count: int = DATE_CHIP_COUNT) -> list[date]:
    first, last = contact_date_bounds(base)
    days, d = [], first
    while d <= last and len(days) < count:
        if is_contact_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


@dataclass(frozen=True)
class Availability:
    open: bool
    reason: str = ""
    seats_left: int | None = None


def course_availability(course, applied_count: int, base: date | None = None) -> Availability:
    base = base or today()
    if not course.is_open:
        return Availability(False, "신청이 마감된 교육이에요.")
    if course.apply_deadline and base > course.apply_deadline:
        return Availability(False, "신청 기간이 끝났어요.")
    seats_left = max(course.capacity - applied_count, 0)
    if seats_left == 0:
        return Availability(False, "정원이 모두 찼어요.", 0)
    return Availability(True, seats_left=seats_left)
