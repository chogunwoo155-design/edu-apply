from django.db import models
from django.urls import reverse


class Course(models.Model):
    class Category(models.TextChoices):
        AI = "ai", "AI · SW"
        DIGITAL = "digital", "디지털 리터러시"
        CAREER = "career", "진로 · 기업가정신"

    class Cover(models.TextChoices):
        # 대표 이미지는 사람 사진 없이 도형 일러스트(static/img/covers/*.svg)만 쓴다.
        ORBIT = "orbit", "궤도"
        GRID = "grid", "격자"
        STEPS = "steps", "계단"

    slug = models.SlugField("주소용 이름", unique=True)
    title = models.CharField("교육명", max_length=80)
    tagline = models.CharField("한 줄 소개", max_length=120)
    category = models.CharField("분야", max_length=20, choices=Category.choices)
    description = models.TextField("소개")
    target = models.CharField("대상", max_length=60)
    schedule = models.CharField("운영 방식", max_length=80, help_text="예: 주 1회 · 2시간 · 6주")
    location = models.CharField("장소", max_length=80)
    capacity = models.PositiveIntegerField("정원")
    fee = models.PositiveIntegerField("참가비(원)", default=0)
    cover = models.CharField("대표 이미지", max_length=20, choices=Cover.choices, default=Cover.ORBIT)
    starts_on = models.DateField("시작일", null=True, blank=True)
    apply_deadline = models.DateField("신청 마감일", null=True, blank=True)
    is_open = models.BooleanField("신청 받는 중", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "교육"
        verbose_name_plural = "교육"
        ordering = ["-is_open", "starts_on", "id"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("courses:detail", args=[self.slug])

    @property
    def cover_path(self) -> str:
        return f"img/covers/{self.cover}.svg"


class CurriculumItem(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="curriculum")
    order = models.PositiveSmallIntegerField("순서")
    title = models.CharField("주제", max_length=80)
    summary = models.CharField("내용", max_length=200)

    class Meta:
        verbose_name = "커리큘럼"
        verbose_name_plural = "커리큘럼"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["course", "order"], name="uniq_curriculum_order"),
        ]

    def __str__(self) -> str:
        return f"{self.order}. {self.title}"
