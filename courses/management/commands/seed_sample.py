"""
샘플 교육 데이터를 넣는다. 교육 내용은 과제용 가상 데이터다.

    python manage.py seed_sample              # 교육 3개
    python manage.py seed_sample --demo-admin # + 로컬 확인용 관리자 계정
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from courses.models import Course, CurriculumItem

DEMO_ADMIN = ("demo", "demo-pass-1234")  # 로컬 전용. 운영에서는 createsuperuser를 쓴다.

SAMPLES = [
    {
        "slug": "ai-problem-solving",
        "title": "AI로 우리 동네 문제 해결하기",
        "tagline": "생성형 AI를 도구 삼아, 내가 사는 동네의 진짜 문제를 풀어 보는 6주 프로젝트",
        "category": Course.Category.AI,
        "cover": Course.Cover.ORBIT,
        "description": (
            "AI가 무엇을 잘하고 무엇을 못하는지 직접 써 보며 익히고, 팀별로 동네의 문제 하나를 골라 "
            "AI를 활용한 해결 아이디어를 시제품까지 만들어 발표합니다. 코딩 경험이 없어도 참여할 수 있어요."
        ),
        "target": "중학교 1~3학년",
        "schedule": "주 1회 · 2시간 · 6주",
        "location": "서울 영등포구 · 오프라인",
        "capacity": 24,
        "fee": 0,
        "curriculum": [
            ("AI와 첫 대화", "생성형 AI의 원리와 한계를 실습으로 이해해요"),
            ("문제 찾기", "동네를 관찰하고 인터뷰하며 풀 만한 문제를 골라요"),
            ("아이디어 다듬기", "AI와 함께 해결책을 여러 개 만들고 하나로 좁혀요"),
            ("시제품 만들기", "노코드 도구로 아이디어를 손에 잡히는 형태로 만들어요"),
            ("검증하기", "실제 사용자에게 보여 주고 피드백을 받아 고쳐요"),
            ("발표회", "팀별로 결과를 발표하고 서로의 프로젝트를 응원해요"),
        ],
    },
    {
        "slug": "digital-literacy",
        "title": "가짜를 가려내는 디지털 리터러시",
        "tagline": "딥페이크와 허위 정보 사이에서 스스로 판단하는 힘을 기르는 4주 과정",
        "category": Course.Category.DIGITAL,
        "cover": Course.Cover.GRID,
        "description": (
            "뉴스, 영상, 이미지가 어떻게 만들어지고 퍼지는지 살펴보고, 출처 확인과 교차 검증을 "
            "직접 해 봅니다. AI가 만든 콘텐츠를 알아보는 방법과 책임 있는 사용법도 함께 다룹니다."
        ),
        "target": "초등학교 5학년 ~ 중학교 2학년",
        "schedule": "주 1회 · 90분 · 4주",
        "location": "온라인 (Zoom)",
        "capacity": 30,
        "fee": 0,
        "curriculum": [
            ("정보는 어떻게 퍼질까", "알고리즘과 공유가 만드는 정보의 흐름을 알아봐요"),
            ("출처 확인하기", "원문, 작성자, 날짜를 추적하는 습관을 만들어요"),
            ("AI가 만든 것 알아보기", "생성 이미지·영상의 특징과 확인 도구를 써 봐요"),
            ("책임 있게 만들기", "내가 만드는 콘텐츠의 영향과 저작권을 생각해요"),
        ],
    },
    {
        "slug": "young-founders",
        "title": "청소년 창업가 캠프",
        "tagline": "아이디어를 비즈니스 모델로 바꾸고 모의 투자 피칭까지 경험하는 2일 캠프",
        "category": Course.Category.CAREER,
        "cover": Course.Cover.STEPS,
        "description": (
            "고객 문제를 정의하고, 가치 제안과 수익 구조를 설계한 뒤, 멘토 앞에서 3분 피칭을 합니다. "
            "실패해도 괜찮은 환경에서 기획부터 실행까지 한 사이클을 끝까지 경험해요."
        ),
        "target": "고등학교 1~2학년",
        "schedule": "2일 · 하루 6시간",
        "location": "서울 영등포구 · 오프라인",
        "capacity": 40,
        "fee": 30000,
        "curriculum": [
            ("고객 문제 정의", "누구의 어떤 불편을 풀지 한 문장으로 정해요"),
            ("가치 제안 설계", "해결책이 고객에게 주는 가치를 구체화해요"),
            ("비즈니스 모델", "수익 구조와 비용을 캔버스로 정리해요"),
            ("3분 피칭", "멘토 앞에서 발표하고 질문에 답해요"),
        ],
    },
]


class Command(BaseCommand):
    help = "샘플 교육 데이터를 넣는다"

    def add_arguments(self, parser):
        parser.add_argument("--demo-admin", action="store_true", help="로컬 확인용 관리자 계정 생성")

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        for i, data in enumerate(SAMPLES):
            data = dict(data)
            curriculum = data.pop("curriculum")
            data["starts_on"] = today + timedelta(days=21 + i * 7)
            data["apply_deadline"] = today + timedelta(days=14 + i * 7)
            course, _ = Course.objects.update_or_create(slug=data["slug"], defaults=data)
            course.curriculum.all().delete()
            CurriculumItem.objects.bulk_create(
                CurriculumItem(course=course, order=n, title=t, summary=s)
                for n, (t, s) in enumerate(curriculum, start=1)
            )
        self.stdout.write(self.style.SUCCESS(f"교육 {len(SAMPLES)}개를 넣었습니다."))

        if options["demo_admin"]:
            User = get_user_model()
            username, password = DEMO_ADMIN
            user, created = User.objects.get_or_create(
                username=username, defaults={"is_staff": True, "is_superuser": True}
            )
            if created:
                user.set_password(password)
                user.save()
            self.stdout.write(f"로컬 관리자 계정: {username} (비밀번호는 seed_sample.py의 DEMO_ADMIN)")
