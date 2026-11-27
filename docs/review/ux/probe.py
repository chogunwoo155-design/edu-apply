"""UX 리뷰용 탐색 스크립트 (docs/review/ux 아래에만 저장)."""
import json
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path(__file__).parent / "shots"
OUT.mkdir(parents=True, exist_ok=True)
APPLY = BASE + "/courses/ai-problem-solving/apply/"
DETAIL = BASE + "/courses/ai-problem-solving/"
res = {}


def shot(page, name, full=False):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def errs(pg):
    return pg.evaluate(
        "[...document.querySelectorAll('.field__error,.form__error')].filter(e=>e.textContent).map(e=>(e.dataset.for||'form')+': '+e.textContent)"
    )


def login(pg):
    pg.goto(BASE + "/admin/login/?next=/manage/")
    pg.fill("#id_username", "demo")
    pg.fill("#id_password", "demo-pass-1234")
    pg.click("input[type=submit]")
    pg.wait_for_load_state("networkidle")


with sync_playwright() as p:
    b = p.chromium.launch()
    mob = dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True,
               has_touch=True, locale="ko-KR", timezone_id="Asia/Seoul")

    # 1) 빈 제출 / 잘못된 값
    ctx = b.new_context(**mob)
    pg = ctx.new_page()
    pg.goto(APPLY, wait_until="networkidle")
    res["done_display_initially"] = pg.evaluate("getComputedStyle(document.getElementById('apply-done')).display")
    res["date_min"] = pg.evaluate("document.getElementById('f-contact-date').min")
    pg.click("button[type=submit]")
    pg.wait_for_timeout(800)
    res["empty_errors"] = errs(pg)
    res["focus_after_error"] = pg.evaluate("document.activeElement.id || document.activeElement.tagName")
    shot(pg, "phone_empty_submit", True)
    pg.fill("#f-name", "김")
    pg.fill("#f-email", "abc@")
    pg.fill("#f-address", "a")
    pg.fill("#f-contact-date", date.today().isoformat())
    pg.click("button[type=submit]")
    pg.wait_for_timeout(800)
    res["bad_errors"] = errs(pg)
    shot(pg, "phone_bad_values", True)
    res["aria_describedby"] = pg.evaluate("[...document.querySelectorAll('input:not([type=hidden])')].map(i=>i.id+':'+i.getAttribute('aria-describedby'))")
    # 2) 네트워크 실패
    pg.route("**/api/applications/", lambda r: r.abort())
    pg.fill("#f-name", "김철수")
    pg.fill("#f-email", "a@example.com")
    pg.click("button[type=submit]")
    pg.wait_for_timeout(800)
    res["net_fail"] = errs(pg)
    shot(pg, "phone_network_fail")
    pg.unroute("**/api/applications/")
    # 3) 서버 500 (HTML)
    pg.route("**/api/applications/", lambda r: r.fulfill(status=500, body="<h1>Server Error</h1>", content_type="text/html"))
    pg.click("button[type=submit]")
    pg.wait_for_timeout(800)
    res["server500"] = errs(pg)
    pg.unroute("**/api/applications/")
    # 4) 새로고침 시 입력 유지?
    pg.reload(wait_until="networkidle")
    res["after_reload_name"] = pg.input_value("#f-name")
    # 5) 키보드 열린 상태 흉내
    pg.set_viewport_size({"width": 390, "height": 450})
    pg.focus("#f-address-detail")
    pg.wait_for_timeout(300)
    shot(pg, "phone_keyboard_open_detail")
    pg.focus("#f-contact-date")
    pg.wait_for_timeout(300)
    shot(pg, "phone_keyboard_open_date")
    ctx.close()

    # 6) 실제 제출 1건 → 완료 화면
    ctx = b.new_context(**mob)
    pg = ctx.new_page()
    pg.goto(DETAIL, wait_until="networkidle")
    pg.goto(APPLY, wait_until="networkidle")
    pg.fill("#f-name", "UX리뷰")
    pg.fill("#f-email", "ux-review@example.com")
    pg.fill("#f-address", "서울 영등포구 선유로 1")
    pg.fill("#f-contact-date", (date.today() + timedelta(days=4)).isoformat())
    pg.click("button[type=submit]")
    pg.wait_for_timeout(1500)
    res["done_text"] = pg.evaluate("document.getElementById('apply-done').innerText")
    res["focus_after_done"] = pg.evaluate("document.activeElement.tagName + '#' + document.activeElement.id")
    res["url_after_done"] = pg.url
    shot(pg, "phone_done", True)
    pg.reload(wait_until="networkidle")
    res["reload_after_done_shows_form"] = pg.evaluate("!document.getElementById('apply-form-area').hidden")
    ctx.close()

    # 7) 다크 모드
    ctx = b.new_context(**{**mob, "color_scheme": "dark"})
    pg = ctx.new_page()
    pg.goto(APPLY, wait_until="networkidle"); shot(pg, "dark_apply")
    pg.goto(DETAIL, wait_until="networkidle"); shot(pg, "dark_detail")
    ctx.close()

    # 8) 기기별 추가 컷
    for key, w, h in [("fold-cover", 344, 882), ("landscape", 852, 393), ("fold-open", 690, 829),
                      ("tablet-l", 1366, 1024), ("qhd", 2560, 1440)]:
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, locale="ko-KR")
        pg = ctx.new_page()
        pg.goto(APPLY, wait_until="networkidle"); shot(pg, f"{key}_apply")
        res[f"{key}_apply_cta"] = pg.evaluate("(()=>{const c=document.querySelector('.bottom-cta');const r=c.getBoundingClientRect();return [Math.round(r.width),Math.round(r.height)]})()")
        pg.goto(DETAIL, wait_until="networkidle"); shot(pg, f"{key}_detail_full", True)
        res[f"{key}_detail_firstfold"] = pg.evaluate("(()=>{const f=document.querySelector('.facts').getBoundingClientRect().top;return {factsTop:Math.round(f),vh:innerHeight}})()")
        ctx.close()

    # 9) 관리 화면
    for key, w, h, m in [("manage_desktop", 1440, 900, False), ("manage_phone", 390, 844, True)]:
        ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if m else 1,
                            is_mobile=m, has_touch=m, locale="ko-KR")
        pg = ctx.new_page()
        pg.goto(BASE + "/manage/", wait_until="networkidle")
        res[key + "_login_url"] = pg.url
        shot(pg, key + "_login")
        pg.fill("#id_username", "demo"); pg.fill("#id_password", "demo-pass-1234")
        pg.click("input[type=submit]"); pg.wait_for_load_state("networkidle")
        res[key + "_after_login_url"] = pg.url
        shot(pg, key, True)
        shot(pg, key + "_fold")
        res[key + "_rows"] = pg.evaluate("document.querySelectorAll('tbody tr').length")
        ctx.close()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="ko-KR")
    pg = ctx.new_page()
    login(pg)
    pg.goto(BASE + "/manage/?status=received", wait_until="networkidle")
    row = pg.locator("tbody tr").filter(has_text="UX리뷰").first
    if row.count():
        row.locator("select").select_option("reviewing")
        pg.wait_for_load_state("networkidle")
        res["after_status_change_url"] = pg.url
    pg.goto(BASE + "/admin/applications/application/", wait_until="networkidle"); shot(pg, "admin_list")
    ctx.close()

    # 10) WebKit 폰트 굵기·날짜 칸
    wk = p.webkit.launch()
    ctx = wk.new_context(viewport={"width": 393, "height": 852}, locale="ko-KR")
    pg = ctx.new_page(); pg.goto(APPLY, wait_until="networkidle")
    res["webkit_h1"] = pg.evaluate("(()=>{const h=document.querySelector('.h1');const s=getComputedStyle(h);return [s.fontWeight,document.fonts.status,[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family+' '+f.weight).slice(0,3)]})()")
    ctx.close(); wk.close()
    b.close()

print(json.dumps(res, ensure_ascii=False, indent=1))
