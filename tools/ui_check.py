"""
기기별 화면 점검: 실제 브라우저(Chromium, WebKit)로 13개 기기 크기에서 페이지를 열고 자동으로 검사한다.

검사 항목 (화면마다)
  overflow   가로로 넘치는 요소가 없는가 (의도한 가로 스크롤 영역 제외)
  tap        버튼·입력칸이 손가락 크기(44px) 이상인가
  hidden     hidden 속성인데 화면에 보이는 요소가 없는가  ← 1차에서 완료 화면이 늘 보이던 버그를 놓쳤다
  cta        하단 버튼이 내용 칸(640px)보다 넓게 늘어나지 않는가  ← 1차 QHD에서 2560px까지 늘어났다
  cover      고정된 상단 바·하단 버튼이 화면 높이의 30% 넘게 가리지 않는가  ← 1차 폰 가로에서 35%
흐름
  submit     신청서를 단계별로 실제로 채워 제출 → 접수증 페이지가 뜨는가
  manage     (--admin 지정 시) 관리 화면 로그인 → 목록이 넘치지 않는가

    python tools/ui_check.py --base http://127.0.0.1:8765 --out docs/screenshots --admin demo:<비밀번호>

필요: pip install -r requirements-dev.txt && playwright install chromium webkit
점검은 신청을 실제로 넣는다. 점검 전용 DB로 띄운 서버에 돌린다(README 참고).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
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


# 접히는 폰은 바깥 화면과 펼친 화면을 따로 본다. CSS 픽셀 기준.
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
DARK_DEVICES = {"phone", "desktop"}

PAGES = [
    ("home", "/"),
    ("detail", "/courses/ai-problem-solving/"),
    ("apply", "/courses/ai-problem-solving/apply/"),
]

CHECK_JS = """
() => {
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const name = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/)[0] : '');

  const overflow = [];
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el) || el.closest('.chip-scroll, .tabs, .skip-link, dialog, .honeypot')) continue;
    const r = el.getBoundingClientRect();
    if (r.right > vw + 1 || r.left < -1) overflow.push(name(el));
  }

  const tap = [];
  for (const el of document.querySelectorAll('a.btn, button, input:not([type=hidden]):not([type=radio]):not([type=checkbox]), select, .choice span')) {
    if (!visible(el) || el.closest('dialog:not([open]), .honeypot')) continue;
    const r = el.getBoundingClientRect();
    if (r.height < 44) tap.push(((el.textContent || el.name || el.id || '').trim().slice(0, 16) || name(el)) + ':' + Math.round(r.height));
  }

  const hidden = [];
  for (const el of document.querySelectorAll('[hidden]')) {
    if (el.getClientRects().length) hidden.push(name(el));
  }

  let cta = null;
  const ctaBtn = document.querySelector('.bottom-cta .btn');
  if (ctaBtn && visible(ctaBtn)) cta = Math.round(ctaBtn.getBoundingClientRect().width);

  let covered = 0;
  for (const el of document.querySelectorAll('.topbar, .bottom-cta')) {
    const st = getComputedStyle(el);
    if ((st.position === 'fixed' || st.position === 'sticky') && visible(el)) {
      const r = el.getBoundingClientRect();
      if (r.bottom > 0 && r.top < vh) covered += Math.min(r.bottom, vh) - Math.max(r.top, 0);
    }
  }
  return { vw, vh, overflow: overflow.slice(0, 6), tap: tap.slice(0, 6), hidden, cta, cover: Math.round(covered / vh * 100) };
}
"""

CTA_MAX = 642  # 내용 칸 640px


def judge(m: dict) -> list[str]:
    problems = []
    if m["overflow"]:
        problems.append(f"넘침 {m['overflow']}")
    if m["tap"]:
        problems.append(f"작은 버튼 {m['tap']}")
    if m["hidden"]:
        problems.append(f"hidden인데 보임 {m['hidden']}")
    if m["cta"] and m["cta"] > CTA_MAX:
        problems.append(f"하단 버튼 폭 {m['cta']}px")
    if m["cover"] > 30:
        problems.append(f"고정 영역이 화면의 {m['cover']}%")
    return problems


def check(base: str, out: Path, only: set[str] | None, admin: str | None) -> int:
    out.mkdir(parents=True, exist_ok=True)
    results = []
    stamp = int(time.time())
    with sync_playwright() as p:
        engines = {"chromium": p.chromium.launch(), "webkit": p.webkit.launch()}
        for d in DEVICES:
            if only and d.key not in only:
                continue
            for scheme in ["light", "dark"] if d.key in DARK_DEVICES else ["light"]:
                ctx = engines[d.engine].new_context(
                    viewport={"width": d.width, "height": d.height},
                    device_scale_factor=d.scale,
                    is_mobile=d.mobile if d.engine == "chromium" else False,
                    has_touch=d.mobile,
                    locale="ko-KR",
                    timezone_id="Asia/Seoul",
                    color_scheme=scheme,
                )
                page = ctx.new_page()
                suffix = "" if scheme == "light" else "__dark"
                for key, path in PAGES:
                    page.goto(base + path, wait_until="networkidle")
                    page.wait_for_timeout(200)
                    m = page.evaluate(CHECK_JS)
                    page.screenshot(path=str(out / f"{d.key}__{key}{suffix}.png"))
                    results.append({"device": d.key + suffix, "page": key, "problems": judge(m), "metrics": m})
                if scheme == "light":
                    results.append({"device": d.key, "page": "submit", **submit_flow(page, base, out, d, stamp)})
                    if admin:
                        results.append({"device": d.key, "page": "manage", **manage_flow(page, base, out, d, admin)})
                ctx.close()
        for b in engines.values():
            b.close()

    (out / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failures = 0
    for r in results:
        ok = not r["problems"]
        failures += 0 if ok else 1
        print(f"{'OK ' if ok else 'FAIL'} {r['device']:<22} {r['page']:<7} {'; '.join(r['problems'])}")
    print(f"\n{len(results)}개 중 실패 {failures}개")
    return failures


def submit_flow(page, base: str, out: Path, d: Device, stamp: int) -> dict:
    """신청서를 단계별로 채워 제출하고, 접수증 페이지가 뜨는지 본다."""
    page.goto(base + "/courses/ai-problem-solving/apply/", wait_until="networkidle")
    try:
        page.fill("#f-name", "점검용")
        page.click("[data-submit]")
        page.fill("#f-email", f"ui-check-{d.key}-{stamp}@example.com")
        page.click("[data-submit]")
        page.fill("#f-address", "서울 영등포구 선유서로 1")
        page.click("[data-submit]")
        page.locator(".chip-scroll .choice").first.click()
        page.check("#f-privacy")
        page.wait_for_timeout(150)
        m = page.evaluate(CHECK_JS)
        page.screenshot(path=str(out / f"{d.key}__apply-filled.png"))
        page.click("[data-submit]")
        page.wait_for_url("**/applications/receipt/**", timeout=8000)
        page.wait_for_timeout(200)
        page.screenshot(path=str(out / f"{d.key}__receipt.png"))
        done = page.evaluate(CHECK_JS)
        problems = judge(m) + [f"접수증: {p}" for p in judge(done)]
        if "접수됐어요" not in page.inner_text("h1"):
            problems.append("접수증 제목이 없음")
        return {"problems": problems}
    except Exception as e:  # noqa: BLE001 - 점검 도구는 실패 이유만 남긴다
        page.screenshot(path=str(out / f"{d.key}__submit-error.png"))
        return {"problems": [f"제출 흐름 실패: {str(e).splitlines()[0]}"]}


def manage_flow(page, base: str, out: Path, d: Device, admin: str) -> dict:
    user, password = admin.split(":", 1)
    try:
        page.goto(base + "/manage/", wait_until="networkidle")
        if "/admin/login" in page.url:
            page.fill("#id_username", user)
            page.fill("#id_password", password)
            page.click("input[type=submit]")
            page.wait_for_url(lambda url: "/admin/login" not in url and "/manage/" in url)
            page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)
        m = page.evaluate(CHECK_JS)
        page.screenshot(path=str(out / f"{d.key}__manage.png"))
        page.locator("[data-open-detail]:visible").first.click()
        page.wait_for_selector("#detail-sheet[open] .detail-dl", timeout=5000)
        page.wait_for_timeout(300)
        page.screenshot(path=str(out / f"{d.key}__manage-detail.png"))
        return {"problems": judge(m)}
    except Exception as e:  # noqa: BLE001
        return {"problems": [f"관리 화면 실패: {str(e).splitlines()[0]}"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--out", default="docs/screenshots")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--admin", help="관리 화면도 볼 때 '아이디:비밀번호' (로컬 점검용 계정)")
    args = ap.parse_args()
    sys.exit(1 if check(args.base.rstrip("/"), Path(args.out), set(args.only) if args.only else None, args.admin) else 0)
