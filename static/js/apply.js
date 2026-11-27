// 신청서: 한 단계씩 열리는 폼 → DRF API로 비동기 제출 → 서버가 만든 접수증 페이지로 이동
// JS가 꺼져 있으면 모든 단계가 한 번에 보인다(no-js). 날짜·시간 계산은 서버(rules.py)가 내려 준 값만 쓴다.
(function () {
  const form = document.getElementById("apply-form");
  if (!form) return;

  const $ = (sel, root = form) => root.querySelector(sel);
  const $$ = (sel, root = form) => Array.from(root.querySelectorAll(sel));
  const steps = $$("[data-step]");
  const submitBtn = $("[data-submit]");
  const formError = $("[data-form-error]");
  const progress = document.querySelector("[data-progress]");
  const progressText = document.querySelector("[data-progress-text]");
  const draftKey = form.dataset.draftKey;
  let revealed = 1;
  let sending = false;

  // ---------- 검사 (서버와 같은 규칙. 최종 판단은 서버) ----------
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  const checks = {
    name: (v) => (v.trim().length >= 2 ? "" : v.trim() ? "이름을 두 글자 이상 적어 주세요." : "학생 이름을 적어 주세요."),
    email: (v) => (!v.trim() ? "연락받을 이메일을 적어 주세요." : EMAIL_RE.test(v.trim()) ? "" : "이메일 주소 형식을 확인해 주세요."),
    address: (v) => (v.trim().length >= 4 ? "" : "주소를 찾아 주세요."),
    contact_date: () => {
      const picked = form.querySelector("input[name=contact_date]:checked");
      if (!picked) return "연락받을 날짜를 골라 주세요.";
      if (picked.value === "other") {
        const other = document.getElementById("f-other-date");
        if (!other.value) return "달력에서 날짜를 골라 주세요.";
        if (other.value < other.min || other.value > other.max) return "고를 수 없는 날짜예요.";
        const day = new Date(other.value + "T00:00:00").getDay();
        if (day === 0 || day === 6) return "주말에는 연락드리기 어려워요. 평일을 골라 주세요.";
      }
      return "";
    },
    privacy_agreed: () => (document.getElementById("f-privacy").checked ? "" : "개인정보 수집·이용에 동의해 주세요."),
  };
  const stepFields = { 1: ["name"], 2: ["email"], 3: ["address"], 4: ["contact_date", "privacy_agreed"] };

  function valueOf(name) {
    const el = form.elements[name];
    return el && "value" in el ? el.value : "";
  }

  function setError(name, message) {
    const slot = $(`[data-error-for="${name}"]`);
    if (slot) slot.textContent = message || "";
    const input = name === "contact_date" ? null : form.elements[name];
    if (input && input.setAttribute) {
      if (message) input.setAttribute("aria-invalid", "true");
      else input.removeAttribute("aria-invalid");
    }
  }

  function validate(name) {
    const message = checks[name] ? checks[name](valueOf(name)) : "";
    setError(name, message);
    return !message;
  }

  function focusField(name) {
    const target =
      name === "contact_date"
        ? form.querySelector("input[name=contact_date]:checked") || form.querySelector("input[name=contact_date]")
        : name === "privacy_agreed"
          ? document.getElementById("f-privacy")
          : form.elements[name];
    if (target && target.focus) target.focus({ preventScroll: false });
  }

  // ---------- 단계 ----------
  function render() {
    steps.forEach((s) => s.classList.toggle("is-revealed", Number(s.dataset.step) <= revealed));
    const isLast = revealed >= steps.length;
    const label = $("[data-submit-label]");
    if (label && !sending) label.textContent = isLast ? "신청하기" : "다음";
    if (progress) progress.style.setProperty("--p", `${(revealed / steps.length) * 100}%`);
    if (progressText) progressText.textContent = `${revealed} / ${steps.length}`;
  }

  function reveal(n, { focus = true } = {}) {
    if (n <= revealed) return;
    revealed = Math.min(n, steps.length);
    render();
    const step = steps[revealed - 1];
    step.classList.add("is-entering");
    step.addEventListener("animationend", () => step.classList.remove("is-entering"), { once: true });
    if (focus) {
      const first = step.querySelector("input:not([type=hidden]):not([type=radio]), input[type=radio]");
      if (first) setTimeout(() => first.focus(), 30);
    }
  }

  // 지금까지 연 단계를 모두 검사. 틀린 첫 칸으로 보낸다
  function validateUpTo(n) {
    let firstBad = null;
    for (let i = 1; i <= n; i++) {
      for (const name of stepFields[i]) {
        if (!validate(name) && !firstBad) firstBad = name;
      }
    }
    if (firstBad) focusField(firstBad);
    return !firstBad;
  }

  // ---------- 입력 편의 ----------
  // 입력하면 그 칸의 오류를 지우고, 칸을 떠날 때 검사한다
  form.addEventListener("input", (e) => {
    const name = e.target.name;
    if (name && e.target.getAttribute("aria-invalid")) validate(name);
    saveDraft();
  });
  form.addEventListener("focusout", (e) => {
    const name = e.target.name;
    if (name && checks[name] && e.target.value && name !== "contact_date") validate(name);
  });

  // Enter(모바일 '다음')는 다음 칸으로. 마지막 단계에서만 제출
  form.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.isComposing || e.target.tagName !== "INPUT" || e.target.type === "checkbox") return;
    const stepEl = e.target.closest("[data-step]");
    const inputs = $$("input:not([type=hidden]):not([type=radio])", stepEl).filter((i) => i.offsetParent !== null);
    const idx = inputs.indexOf(e.target);
    if (idx >= 0 && idx < inputs.length - 1) {
      e.preventDefault();
      inputs[idx + 1].focus();
    }
  });

  // 흔한 이메일 오타 제안
  const DOMAIN_FIX = { "gmial.com": "gmail.com", "gamil.com": "gmail.com", "gmail.co": "gmail.com", "gmail.con": "gmail.com",
    "naver.co": "naver.com", "naver.con": "naver.com", "nave.com": "naver.com", "hanmail.ent": "hanmail.net", "hanmail.com": "hanmail.net",
    "daum.com": "daum.net", "nate.con": "nate.com", "kakao.co": "kakao.com" };
  const suggest = $("[data-email-suggest]");
  form.elements.email.addEventListener("blur", () => {
    const v = form.elements.email.value.trim();
    const domain = v.split("@")[1]?.toLowerCase();
    if (domain && DOMAIN_FIX[domain]) {
      const fixed = v.split("@")[0] + "@" + DOMAIN_FIX[domain];
      suggest.innerHTML = "";
      suggest.append("혹시 ");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = fixed;
      btn.addEventListener("click", () => {
        form.elements.email.value = fixed;
        suggest.hidden = true;
        validate("email");
        saveDraft();
      });
      suggest.append(btn, " 아닌가요?");
      suggest.hidden = false;
    } else {
      suggest.hidden = true;
    }
  });

  // 날짜 칩
  const otherWrap = $("[data-other-date-wrap]");
  const otherInput = document.getElementById("f-other-date");
  const picked = $("[data-picked]");
  const contactTimeLabel = () => form.querySelector("input[name=contact_time]:checked")?.closest("label").textContent.trim();
  function showPicked() {
    const r = form.querySelector("input[name=contact_date]:checked");
    let label = r?.dataset.label;
    if (r?.value === "other" && otherInput.value) {
      const d = new Date(otherInput.value + "T00:00:00");
      label = d.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" }).replace(/\((.)\)/, "($1)");
    }
    if (label && (r.value !== "other" || otherInput.value)) {
      picked.innerHTML = "";
      const strong = document.createElement("strong");
      strong.textContent = label;
      picked.append(strong, ` ${contactTimeLabel() === "언제든" ? "" : contactTimeLabel() + "에 "}연락드릴게요`.replace("  ", " "));
      picked.hidden = false;
    } else {
      picked.hidden = true;
    }
  }
  form.addEventListener("change", (e) => {
    if (e.target.name === "contact_date") {
      const isOther = e.target.value === "other";
      otherWrap.hidden = !isOther;
      if (isOther) {
        otherInput.focus();
        try { otherInput.showPicker?.(); } catch (_) { /* 사용자 동작이 아니면 막힐 수 있다 */ }
      }
      validate("contact_date");
    }
    if (e.target === otherInput) validate("contact_date");
    if (e.target.name === "privacy_agreed") validate("privacy_agreed");
    showPicked();
    saveDraft();
  });

  // 개인정보 동의 시트의 "동의하고 닫기"
  document.querySelector("[data-agree]")?.addEventListener("click", () => {
    const box = document.getElementById("f-privacy");
    box.checked = true;
    validate("privacy_agreed");
    window.ui?.closeSheet(document.getElementById("privacy-sheet"));
  });

  // ---------- 주소 찾기 (카카오 우편번호, 키 필요 없음) ----------
  const POSTCODE_SRC = "https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js";
  let postcodeLoading = null;
  function loadPostcode() {
    if (window.daum?.Postcode) return Promise.resolve();
    if (!postcodeLoading) {
      postcodeLoading = new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = POSTCODE_SRC;
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
    return postcodeLoading;
  }
  document.querySelector("[data-open-postcode]")?.addEventListener("click", async (e) => {
    const sheet = window.ui.openSheet("postcode-sheet", e.currentTarget);
    const frame = document.querySelector("[data-postcode-frame]");
    const fallback = document.querySelector("[data-postcode-fallback]");
    try {
      await loadPostcode();
      frame.innerHTML = "";
      new window.daum.Postcode({
        width: "100%",
        height: "100%",
        oncomplete(data) {
          let addr = data.roadAddress || data.jibunAddress;
          if (data.buildingName && data.apartment === "Y") addr += ` (${data.buildingName})`;
          form.elements.address.value = addr;
          form.elements.postcode.value = data.zonecode || "";
          window.ui.closeSheet(sheet);
          validate("address");
          saveDraft();
          setTimeout(() => form.elements.address_detail.focus(), 50);
        },
      }).embed(frame, { autoClose: false });
    } catch (_) {
      frame.hidden = true;
      fallback.hidden = false;
    }
  });
  // 직접 고쳐 쓰면 검색으로 채운 우편번호는 더 이상 맞지 않으므로 비운다
  form.elements.address.addEventListener("input", () => { form.elements.postcode.value = ""; });

  // ---------- 임시 저장 (같은 탭 안에서만: sessionStorage) ----------
  const DRAFT_FIELDS = ["name", "email", "address", "address_detail", "postcode"];
  function saveDraft() {
    try {
      const data = Object.fromEntries(DRAFT_FIELDS.map((f) => [f, valueOf(f)]));
      data.contact_date = form.querySelector("input[name=contact_date]:checked")?.value || "";
      data.other_date = otherInput.value;
      data.contact_time = form.querySelector("input[name=contact_time]:checked")?.value || "";
      data.revealed = revealed;
      sessionStorage.setItem(draftKey, JSON.stringify(data));
    } catch (_) { /* 사생활 보호 모드 등: 저장 없이 진행 */ }
  }
  function restoreDraft() {
    let data;
    try { data = JSON.parse(sessionStorage.getItem(draftKey) || "null"); } catch (_) { data = null; }
    if (!data) return;
    DRAFT_FIELDS.forEach((f) => { if (data[f] && form.elements[f]) form.elements[f].value = data[f]; });
    if (data.contact_date) {
      const r = form.querySelector(`input[name=contact_date][value="${CSS.escape(data.contact_date)}"]`);
      if (r) {
        r.checked = true;
        if (data.contact_date === "other") { otherWrap.hidden = false; otherInput.value = data.other_date || ""; }
      }
    }
    if (data.contact_time) {
      const t = form.querySelector(`input[name=contact_time][value="${CSS.escape(data.contact_time)}"]`);
      if (t) t.checked = true;
    }
    revealed = Math.max(1, Math.min(Number(data.revealed) || 1, steps.length));
    render();
    showPicked();
  }
  const clearDraft = () => { try { sessionStorage.removeItem(draftKey); } catch (_) {} };

  // ---------- 제출 ----------
  function setSending(on) {
    sending = on;
    submitBtn.disabled = on;
    submitBtn.setAttribute("aria-busy", on ? "true" : "false");
    submitBtn.innerHTML = on
      ? '<span class="spinner" aria-hidden="true"></span><span data-submit-label>신청하는 중…</span>'
      : "<span data-submit-label></span>";
    if (!on) render();
  }

  function showFormError(message, { retry = false } = {}) {
    formError.innerHTML = "";
    const p = document.createElement("span");
    p.textContent = message;
    formError.appendChild(p);
    if (retry) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn btn--secondary btn--sm";
      b.textContent = "다시 시도";
      b.addEventListener("click", () => form.requestSubmit());
      formError.appendChild(b);
    }
    formError.hidden = false;
    formError.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  const STATUS_MESSAGES = {
    403: "보안 확인이 만료됐어요. 페이지를 새로고침한 뒤 다시 시도해 주세요. 적은 내용은 남아 있어요.",
    429: "짧은 시간에 신청이 너무 많이 들어왔어요. 잠시 후 다시 시도해 주세요.",
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (sending) return;
    formError.hidden = true;

    if (!validateUpTo(revealed)) return;
    if (revealed < steps.length) {
      reveal(revealed + 1);
      saveDraft();
      return;
    }

    const picked = form.querySelector("input[name=contact_date]:checked");
    const data = {
      course: form.dataset.course,
      name: valueOf("name").trim(),
      email: valueOf("email").trim(),
      address: valueOf("address").trim(),
      address_detail: valueOf("address_detail").trim(),
      postcode: valueOf("postcode"),
      contact_date: picked.value === "other" ? otherInput.value : picked.value,
      contact_time: form.querySelector("input[name=contact_time]:checked")?.value || "any",
      privacy_agreed: document.getElementById("f-privacy").checked,
      website: valueOf("website"),
    };

    setSending(true);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const res = await fetch(form.dataset.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": valueOf("csrfmiddlewaretoken") },
        body: JSON.stringify(data),
        signal: controller.signal,
      });
      const isJson = (res.headers.get("content-type") || "").includes("application/json");
      const body = isJson ? await res.json() : null;

      if (res.ok && body?.receipt_url) {
        clearDraft();
        window.location.replace(body.receipt_url); // 뒤로 가기·새로고침으로 다시 제출되지 않게
        return;
      }
      if (res.status === 400 && body) {
        let firstBad = null;
        Object.entries(body).forEach(([field, messages]) => {
          const text = Array.isArray(messages) ? messages.join(" ") : String(messages);
          if ($(`[data-error-for="${field}"]`)) {
            setError(field, text);
            firstBad = firstBad || field;
          } else {
            showFormError(text);
          }
        });
        if (firstBad) focusField(firstBad);
        return;
      }
      showFormError(
        STATUS_MESSAGES[res.status] || "일시적인 문제가 생겼어요. 잠시 후 다시 시도해 주세요. 같은 신청이 두 번 접수되지는 않아요.",
        { retry: res.status >= 500 },
      );
    } catch (e) {
      const offline = navigator.onLine === false;
      showFormError(
        offline ? "인터넷 연결이 끊겼어요. 연결을 확인한 뒤 다시 시도해 주세요." : "응답이 늦어지고 있어요. 다시 시도해 주세요. 같은 신청이 두 번 접수되지는 않아요.",
        { retry: true },
      );
    } finally {
      clearTimeout(timer);
      setSending(false);
    }
  });

  restoreDraft();
  render();
})();
