// 공통 UI: 상단 바 경계선, 바텀시트(dialog), 토스트
(function () {
  // 스크롤하면 상단 바에 경계선
  const topbar = document.querySelector("[data-topbar]");
  if (topbar) {
    const onScroll = () => topbar.classList.toggle("is-scrolled", window.scrollY > 4);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // 바텀시트: data-open-sheet="id" 로 열고, 닫기 버튼·배경 클릭·Esc로 닫는다
  function openSheet(id, opener) {
    const dialog = document.getElementById(id);
    if (!dialog) return null;
    dialog._opener = opener || document.activeElement;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    return dialog;
  }
  function closeSheet(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }
  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-open-sheet]");
    if (opener) openSheet(opener.dataset.openSheet, opener);
    const closer = e.target.closest("[data-close-sheet]");
    if (closer) closeSheet(closer.closest("dialog"));
    if (e.target.tagName === "DIALOG" && e.target.classList.contains("sheet")) {
      // 배경(::backdrop) 클릭: dialog 자신이 클릭 대상이 된다
      const r = e.target.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      if (!inside) closeSheet(e.target);
    }
  });
  document.addEventListener("close", (e) => {
    if (e.target.tagName === "DIALOG" && e.target._opener) e.target._opener.focus?.();
  }, true);

  // 토스트
  const stack = document.querySelector("[data-toasts]");
  function toast(message, { actionLabel, onAction, error = false, timeout = 4500 } = {}) {
    if (!stack) return;
    const el = document.createElement("div");
    el.className = "toast" + (error ? " toast--error" : "");
    el.setAttribute("role", error ? "alert" : "status");
    const text = document.createElement("span");
    text.textContent = message;
    el.appendChild(text);
    if (actionLabel && onAction) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = actionLabel;
      btn.addEventListener("click", () => { el.remove(); onAction(); });
      el.appendChild(btn);
    }
    stack.appendChild(el);
    setTimeout(() => el.remove(), timeout);
  }

  window.ui = { openSheet, closeSheet, toast };
})();
