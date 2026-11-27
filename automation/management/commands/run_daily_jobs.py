"""
매일 아침(08:00 KST) 스케줄러가 부르는 명령.

    python manage.py run_daily_jobs                       # 오늘 기준 전체
    python manage.py run_daily_jobs --dry-run             # 보내지 않고 몇 건인지만
    python manage.py run_daily_jobs --date 2026-12-01     # 특정 날짜 기준으로 다시 돌리기
    python manage.py run_daily_jobs --only staff_digest --force

하나라도 실패하면 종료 코드 1 → 스케줄러(EventBridge/cron/Airflow)가 실패로 알림.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from automation.jobs import JOBS, run_job
from automation.models import JobRun


class Command(BaseCommand):
    help = "매일 배치: 실패 메일 재시도 → 연락 하루 전 안내 → 담당자 요약 → 시트 내보내기"

    def add_arguments(self, parser):
        parser.add_argument("--date", type=date.fromisoformat, help="기준 날짜 YYYY-MM-DD (기본: 오늘, KST)")
        parser.add_argument("--dry-run", action="store_true", help="메일·시트에 쓰지 않고 대상 건수만 계산")
        parser.add_argument("--only", nargs="+", choices=list(JOBS), help="일부 작업만 실행")
        parser.add_argument("--force", action="store_true", help="하루 한 번 작업도 다시 실행")
        parser.add_argument("--manual", action="store_true", help="수동 실행으로 기록")

    def handle(self, *args, **opts):
        target = opts["date"] or timezone.localdate()
        trigger = JobRun.Trigger.MANUAL if opts["manual"] else JobRun.Trigger.SCHEDULE
        names = opts["only"] or list(JOBS)
        failed = []
        for name in names:
            run = run_job(name, target, dry_run=opts["dry_run"], trigger=trigger, force=opts["force"])
            mark = self.style.SUCCESS("성공") if run.status == JobRun.Status.SUCCESS else self.style.ERROR("실패")
            self.stdout.write(f"[{mark}] {name} {run.stats or ''} {run.error}")
            if run.status == JobRun.Status.FAILED:
                failed.append(name)
        if failed:
            raise CommandError(f"실패한 작업: {', '.join(failed)}")
