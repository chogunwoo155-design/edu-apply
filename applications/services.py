"""
신청 서비스 계층.

뷰 · API · 관리 화면 · admin · 배치는 비즈니스 규칙을 직접 갖지 않고 이 함수들만 부른다.
1차에서는 신청+메일이 ViewSet.perform_create에, 상태 변경이 함수 뷰에, 안내 메일이
관리 명령에 흩어져 있었고 메일 코드가 두 벌이었다 (docs/REFACTORING.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db import IntegrityError, transaction
from django.utils import timezone

from automation.mailer import deliver
from automation.models import NotificationLog
from courses.models import Course

from . import rules
from .models import Application, ApplicationStatusLog


class ApplicationError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 신청 거절 사유. field가 있으면 그 칸 아래에 표시한다."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


@dataclass(frozen=True)
class ApplicantInput:
    name: str
    email: str
    address: str
    contact_date: date
    postcode: str = ""
    address_detail: str = ""
    contact_time: str = Application.ContactTime.ANY


def active_application_count(course: Course) -> int:
    return course.applications.count()


def submit_application(course_id: int, data: ApplicantInput, *, base: date | None = None) -> Application:
    """
    신청 접수. 규칙: 신청 가능(열림·마감일·정원) → 연락 날짜 → 중복.
    교육 행을 잠그고(select_for_update) 정원을 세므로, 마지막 한 자리에 동시에 들어와도 한 명만 붙는다.
    접수 확인 메일은 커밋이 끝난 뒤 보낸다. 메일이 실패해도 신청은 성공이고, 실패 건은 배치가 다시 보낸다.
    """
    error = rules.contact_date_error(data.contact_date, base)
    if error:
        raise ApplicationError(error, "contact_date")

    email = data.email.strip().lower()
    with transaction.atomic():
        course = Course.objects.select_for_update().get(pk=course_id)
        availability = rules.course_availability(course, active_application_count(course), base)
        if not availability.open:
            raise ApplicationError(availability.reason)
        if course.applications.filter(email__iexact=email).exists():
            raise ApplicationError("이 이메일로 이미 신청하셨어요. 접수 메일을 확인해 주세요.", "email")
        try:
            with transaction.atomic():
                application = Application.objects.create(
                    course=course,
                    name=data.name,
                    email=email,
                    postcode=data.postcode,
                    address=data.address,
                    address_detail=data.address_detail,
                    contact_date=data.contact_date,
                    contact_time=data.contact_time,
                    privacy_agreed_at=timezone.now(),
                )
        except IntegrityError:  # 검사와 저장 사이에 같은 신청이 끼어든 경우
            raise ApplicationError("이 이메일로 이미 신청하셨어요. 접수 메일을 확인해 주세요.", "email")

        transaction.on_commit(lambda: deliver(application, NotificationLog.Kind.CONFIRMATION))
    return application


def change_status(application: Application, new_status: str, *, by=None) -> Application:
    if new_status not in Application.Status.values:
        raise ApplicationError("알 수 없는 상태예요.", "status")
    if new_status == application.status:
        return application
    with transaction.atomic():
        ApplicationStatusLog.objects.create(
            application=application,
            from_status=application.status,
            to_status=new_status,
            changed_by=by if getattr(by, "is_authenticated", False) else None,
        )
        application.status = new_status
        application.save(update_fields=["status", "updated_at"])
    return application


def update_memo(application: Application, memo: str) -> Application:
    application.admin_memo = memo.strip()[:2000]
    application.save(update_fields=["admin_memo", "updated_at"])
    return application
