"""
기기별 화면 점검: 실제 브라우저(Chromium, WebKit)로 페이지를 열어
1) 가로 스크롤(넘침)이 없는지, 2) 버튼·입력칸이 손가락 크기(44px)인지,
3) 신청서를 끝까지 제출할 수 있는지 확인하고 캡처를 남긴다.

    python tools/ui_check.py --base http://127.0.0.1:8765 --out docs/screenshots

필요: pip install playwright && playwright install chromium webkit
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright


@dataclass(frozen=True)
class Device:
    key: str
    label: str
    width: int
    height: int
    scale: float = 2.0
    mobile: bool = True
    engine: str = "chromium"


# 접히는 폰은 펼친 화면과 바깥 화면을 따로 본다. CSS 픽셀 기준.
DEVICES = [
    Device("fold-cover", "갤럭시 Z 폴드 바깥 화면", 344, 882, 2.6),
    Device("phone-small", "작은 폰 (iPhone SE)", 375, 667, 2.0, engine="webkit"),
    Device("phone-android", "안드로이드 폰 (Galaxy S)", 360, 780, 3.0),
    Device("phone", "iPhone 15", 393, 852, 3.0, engine="webkit"),
    Device("phone-large", "큰 폰 (Pro Max)", 430, 932, 3.0, engine="webkit"),
    Device("flip", "갤럭시 Z 플립", 412, 1004, 2.6),
    Device("phone-landscape", "폰 가로", 852, 393, 3.0, engine="webkit"),
    Device("fold-open", "갤럭시 Z 폴드 펼침", 690, 829, 2.6),
    Device("tablet-portrait", "태블릿 세로 (iPad Air)", 820, 1180, 2.0, engine="webkit"),
    Device("tablet-landscape", "태블릿 가로 (iPad Pro)", 1366, 1024, 2.0, engine="webkit"),
    Device("laptop", "노트북", 1280, 800, 1.0, mobile=False),
    Device("desktop", "데스크톱 FHD", 1920, 1080, 1.0, mobile=False),
    Device("desktop-qhd", "데스크톱 QHD", 2560, 1440, 1.0, mobile=False),
]

PAGES = [
    ("home", "/"),
    ("detail", "/courses/ai-problem-solving/"),
    ("apply", "/courses/ai-problem-solving/apply/"),
]

OVERFLOW_JS = """
() => {
  const docW = document.documentElement.clientWidth;
  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const style = getComputedStyle(el);
    if (style.position === 'fixed' && r.right <= docW + 1) continue;
    if (el.closest('.table-wrap, .tabs, .date-chips')) continue;  // 의도된 가로 스크롤 영역
    if (r.right > docW + 1 || r.left < -1) {
      offenders.push(el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(' ')[0] : ''));
    }
  }
  return {scrollW: document.documentElement.scrollWidth, docW, offenders: offenders.slice(0, 8)};
}
"""

TAP_JS = """
() => {
  const small = [];
  for (const el of document.querySelectorAll('a.btn, button, input:not([type=hidden]), select, [role=button]')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (getComputedStyle(el).visibility === 'hidden') continue;
    if (r.height < 44) small.push((el.id || el.name || el.textContent || el.tagName).trim().slice(0, 20) + ':' + Math.round(r.height));
  }
  return small;
}
"""


def check(base: str, out: Path, only: set[str] | None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    results = []
    failures = 0
    with sync_playwright() as p:
        engines = {"chromium": p.chromium.launch(), "webkit": p.webkit.launch()}
        for d in DEVICES:
            if only and d.key not in only:
                continue
            ctx = engines[d.engine].new_context(
                viewport={"width": d.width, "height": d.height},
                device_scale_factor=d.scale,
                is_mobile=d.mobile if d.engine == "chromium" else False,
                has_touch=d.mobile,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
            )
            page = ctx.new_page()
            for key, path in PAGES:
                page.goto(base + path, wait_until="networkidle")
                page.wait_for_timeout(150)
                ov = page.evaluate(OVERFLOW_JS)
                taps = page.evaluate(TAP_JS)
                shot = out / f"{d.key}__{key}.png"
                page.screenshot(path=str(shot), full_page=False)
                ok = ov["scrollW"] <= ov["docW"] and not ov["offenders"] and not taps
                failures += 0 if ok else 1
                results.append({"device": d.key, "page": key, "ok": ok, "overflow": ov, "small_targets": taps})
            results.append({"device": d.key, "page": "submit", **submit_flow(page, base)})
            if not results[-1]["ok"]:
                failures += 1
            ctx.close()
        for b in engines.values():
            b.close()

    (out / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in results:
        mark = "OK " if r["ok"] else "FAIL"
        extra = "" if r["ok"] else " " + json.dumps({k: v for k, v in r.items() if k not in {"device", "page", "ok"}}, ensure_ascii=False)
        print(f"{mark} {r['device']:<18} {r['page']:<7}{extra}")
    print(f"\n{len(results)}개 중 실패 {failures}개")
    return failures


def submit_flow(page, base: str) -> dict:
    """신청서를 실제로 채워 제출하고 완료 화면이 뜨는지 본다."""
    page.goto(base + "/courses/ai-problem-solving/apply/", wait_until="networkidle")
    target = (date.today() + timedelta(days=3)).isoformat()
    try:
        page.fill("#f-name", "점검용")
        page.fill("#f-email", "ui-check@example.com")
        page.fill("#f-address", "서울 영등포구 선유서로 1")
        page.fill("#f-contact-date", target)
        page.click("button[type=submit]")
        page.wait_for_selector("#apply-done:not([hidden])", timeout=5000)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001 - 점검 도구는 실패 이유만 남긴다
        return {"ok": False, "error": str(e).splitlines()[0]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--out", default="docs/screenshots")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    sys.exit(1 if check(args.base.rstrip("/"), Path(args.out), set(args.only) if args.only else None) else 0)
