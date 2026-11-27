"""
ui_check.py가 남긴 캡처를 README용 비교 이미지로 묶는다.

    python tools/make_gallery.py --v1 var/shots-v1 --v2 var/shots-v2 --out docs/screenshots
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_PATHS = ["C:/Windows/Fonts/malgunbd.ttf", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"]
BG = (244, 245, 247)
INK = (25, 28, 33)
SUB = (107, 114, 128)


def font(size: int):
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def strip(items: list[tuple[Path, str, str]], height: int, out: Path, title: str, gap: int = 28) -> None:
    """(이미지, 제목, 부제) 목록을 같은 높이로 맞춰 가로로 붙인다."""
    tiles = []
    for path, label, sub in items:
        im = Image.open(path).convert("RGB")
        w = round(im.width * height / im.height)
        tiles.append((im.resize((w, height), Image.LANCZOS), label, sub))
    top, bottom = 76, 70
    width = sum(t[0].width for t in tiles) + gap * (len(tiles) + 1)
    canvas = Image.new("RGB", (width, top + height + bottom), BG)
    d = ImageDraw.Draw(canvas)
    d.text((gap, 22), title, fill=INK, font=font(30))
    x = gap
    for im, label, sub in tiles:
        canvas.paste(im, (x, top))
        d.rectangle([x - 1, top - 1, x + im.width, top + im.height], outline=(220, 223, 228), width=2)
        d.text((x, top + height + 14), label, fill=INK, font=font(20))
        d.text((x, top + height + 42), sub, fill=SUB, font=font(16))
        x += im.width + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, optimize=True)
    print("만듦", out, canvas.size)


def main(v1: Path, v2: Path, out: Path) -> None:
    devices = [
        ("fold-cover", "폴드 바깥", "344×882"),
        ("phone-small", "iPhone SE", "375×667"),
        ("phone", "iPhone 15", "393×852"),
        ("flip", "Z 플립", "412×1004"),
        ("fold-open", "폴드 펼침", "690×829"),
        ("tablet-portrait", "태블릿 세로", "820×1180"),
    ]
    strip([(v2 / f"{k}__detail.png", l, s) for k, l, s in devices], 760, out / "devices-detail.png", "교육 소개 · 기기별")
    strip([(v2 / f"{k}__apply-filled.png", l, s) for k, l, s in devices], 760, out / "devices-apply.png", "신청서 · 기기별 (4단계까지 채운 상태)")
    strip(
        [
            (v2 / "phone-landscape__detail.png", "폰 가로", "852×393"),
            (v2 / "tablet-landscape__detail.png", "태블릿 가로", "1366×1024"),
            (v2 / "desktop__detail.png", "FHD", "1920×1080"),
            (v2 / "desktop-qhd__detail.png", "QHD", "2560×1440"),
        ],
        520, out / "devices-wide.png", "넓은 화면 · 키 낮은 화면",
    )
    strip(
        [
            (v1 / "phone__apply.png", "1차 · 폰", "완료 블록이 빈칸째로 늘 보임"),
            (v2 / "phone__apply.png", "2차 · 폰", "한 단계씩 여는 폼"),
            (v1 / "phone-landscape__apply.png", "1차 · 폰 가로", "고정 바·버튼이 화면 35% 가림"),
            (v2 / "phone-landscape__apply.png", "2차 · 폰 가로", "키 낮은 화면은 고정 해제"),
        ],
        700, out / "before-after-mobile.png", "1차 → 2차 (UX 리뷰 반영)",
    )
    strip(
        [
            (v1 / "desktop-qhd__apply.png", "1차 · QHD", "하단 버튼이 2560px로 늘어남"),
            (v2 / "desktop-qhd__apply.png", "2차 · QHD", "내용 칸에 맞춘 버튼"),
        ],
        560, out / "before-after-desktop.png", "1차 → 2차 (넓은 화면)",
    )
    strip(
        [
            (v2 / "desktop__manage-detail.png", "관리 화면 · PC", "요약·검색·상태 바로 변경·옆 패널"),
            (v2 / "phone__manage.png", "관리 화면 · 폰", "표 대신 카드"),
            (v2 / "phone__receipt.png", "접수증", "새로고침해도 다시 제출 안 됨"),
        ],
        760, out / "manage-receipt.png", "관리 화면 · 접수증",
    )
    strip(
        [
            (v2 / "phone__apply__dark.png", "다크 · 폰", "신청서"),
            (v2 / "phone__detail__dark.png", "다크 · 폰", "교육 소개"),
            (v2 / "desktop__home__dark.png", "다크 · PC", "교육 목록"),
        ],
        700, out / "dark-mode.png", "다크 모드",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1", default="var/shots-v1")
    ap.add_argument("--v2", default="var/shots-v2")
    ap.add_argument("--out", default="docs/screenshots")
    a = ap.parse_args()
    main(Path(a.v1), Path(a.v2), Path(a.out))
