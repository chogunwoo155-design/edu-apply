// 관리 화면: 상태를 그 자리에서 바꾸고(되돌리기 가능), 줄을 누르면 옆 패널에서 상세·메모를 본다.
// 모두 이미 있는 DRF API(PATCH/GET /api/applications/{id}/)를 쓴다. 페이지 새로고침·필터 풀림 없음.
(function () {
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
  const api = (id) => `/api/applications/${id}/`;
  const STATUS_LABEL = { received: "접수", reviewing: "확인중", done: "완료" };

  async function patch(id, data) {
    const res = await fetch(api(id), {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(data),
    });
    const body = (res.headers.get("content-type") || "").includes("json") ? await res.json() : null;
    if (!res.ok) throw new Error(body ? Object.values(body).flat().join(" ") : `오류 ${res.status}`);
    return body;
  }

  // 같은 신청이 표와 카드에 둘 다 있으므로 함께 맞춘다
  function syncSelects(id, status) {
    document.querySelectorAll(`[data-status-for="${id}"]`).forEach((s) => {
      s.value = status;
      s.dataset.status = status;
    });
  }

  async function changeStatus(select, next, prev) {
    const id = select.dataset.statusFor;
    const name = select.dataset.name;
    syncSelects(id, next);
    try {
      await patch(id, { status: next });
      window.ui.toast(`${name}님 → ${STATUS_LABEL[next]}`, {
        actionLabel: "되돌리기",
        onAction: () => changeStatus(select, prev, next),
      });
    } catch (e) {
      syncSelects(id, prev);
      window.ui.toast(`바꾸지 못했어요: ${e.message}`, { error: true });
    }
  }

  document.addEventListener("focusin", (e) => {
    if (e.target.matches?.("[data-status-for]")) e.target.dataset.prev = e.target.value;
  });
  document.addEventListener("change", (e) => {
    const select = e.target.closest("[data-status-for]");
    if (!select) return;
    changeStatus(select, select.value, select.dataset.prev || select.dataset.status);
    select.dataset.prev = select.value;
  });
  // 상태 선택을 눌렀을 때 줄 클릭(상세 열기)으로 번지지 않게
  document.addEventListener("click", (e) => {
    if (e.target.closest(".status-select")) e.stopPropagation();
  }, true);

  // ---------- 상세 패널 ----------
  const sheet = document.getElementById("detail-sheet");
  const body = sheet?.querySelector("[data-detail-body]");

  function row(label, value, { html = false } = {}) {
    const div = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    if (html) dd.append(value);
    else dd.textContent = value || "—";
    div.append(dt, dd);
    return div;
  }

  async function openDetail(id, opener) {
    if (!sheet) return;
    body.innerHTML = '<p class="muted">불러오는 중…</p>';
    window.ui.openSheet("detail-sheet", opener);
    let a;
    try {
      const res = await fetch(api(id), { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(res.status);
      a = await res.json();
    } catch (e) {
      body.innerHTML = '<p class="muted">불러오지 못했어요. 다시 시도해 주세요.</p>';
      return;
    }
    body.innerHTML = "";
    const dl = document.createElement("dl");
    dl.className = "detail-dl";

    const mail = document.createElement("span");
    const link = document.createElement("a");
    link.href = `mailto:${a.email}`;
    link.textContent = a.email;
    link.style.textDecoration = "underline";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "btn btn--ghost btn--sm";
    copy.textContent = "복사";
    copy.style.marginLeft = "4px";
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(a.email); window.ui.toast("이메일을 복사했어요"); } catch (_) {}
    });
    mail.append(link, copy);

    dl.append(
      row("신청번호", a.reference),
      row("학생 이름", a.name),
      row("교육", a.course_title),
      row("이메일", mail, { html: true }),
      row("주소", [a.postcode && `(${a.postcode})`, a.address, a.address_detail].filter(Boolean).join(" ")),
      row("연락 가능", `${new Date(a.contact_date + "T00:00:00").toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" })} · ${a.contact_time_label}`),
      row("상태", a.status_label),
      row("신청 일시", new Date(a.created_at).toLocaleString("ko-KR")),
    );
    body.appendChild(dl);

    // 메모: 입력을 멈추면 자동 저장
    const label = document.createElement("label");
    label.className = "step__title";
    label.htmlFor = "memo";
    label.textContent = "담당자 메모";
    label.style.cssText = "display:block;margin:20px 0 8px";
    const memo = document.createElement("textarea");
    memo.id = "memo";
    memo.className = "memo";
    memo.value = a.admin_memo || "";
    memo.placeholder = "통화 내용, 다음에 할 일 등";
    const state = document.createElement("p");
    state.className = "memo-state";
    state.setAttribute("aria-live", "polite");
    let timer;
    memo.addEventListener("input", () => {
      state.textContent = "입력 중…";
      clearTimeout(timer);
      timer = setTimeout(async () => {
        try {
          await patch(id, { admin_memo: memo.value });
          state.textContent = "저장했어요";
        } catch (e) {
          state.textContent = `저장하지 못했어요: ${e.message}`;
        }
      }, 700);
    });
    body.append(label, memo, state);
  }

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-open-detail]");
    if (trigger) openDetail(trigger.dataset.openDetail, trigger);
  });
  // 표의 줄도 키보드로 열 수 있게
  document.querySelectorAll("tr[data-open-detail]").forEach((tr) => {
    tr.tabIndex = 0;
    tr.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openDetail(tr.dataset.openDetail, tr);
      }
    });
  });
})();
