from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from applications.models import Application


class Command(BaseCommand):
    help = "연락 가능 날짜가 오늘인 신청자에게 안내 메일을 보낸다 (매일 아침 실행)."

    def handle(self, *args, **options):
        today = timezone.localdate()
        targets = Application.objects.filter(contact_date=today).exclude(
            status=Application.Status.DONE
        )
        sent = 0
        for application in targets:
            send_mail(
                subject=f"[히어로스쿨] 오늘 {application.course.title} 담당자가 연락드립니다",
                message=(
                    f"{application.name}님, 안녕하세요.\n"
                    f"신청하신 '{application.course.title}' 안내를 위해 오늘 담당자가 연락드릴 예정입니다."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[application.email],
            )
            sent += 1
        self.stdout.write(f"안내 메일 {sent}건 발송")
