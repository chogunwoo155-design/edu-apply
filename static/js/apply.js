// 신청 폼: DRF API로 비동기 제출하고, 성공하면 폼 영역만 완료 화면으로 바꾼다.
(function () {
  const form = document.getElementById("apply-form");
  if (!form) return;

  const formError = form.querySelector(".form__error");
  const submitBtn = form.querySelector("button[type=submit]");
  const dateInput = document.getElementById("f-contact-date");

  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  dateInput.min = tomorrow.toISOString().slice(0, 10);

  function clearErrors() {
    form.querySelectorAll(".field__error").forEach((el) => (el.textContent = ""));
    form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
    formError.hidden = true;
  }

  function showErrors(errors) {
    Object.entries(errors).forEach(([field, messages]) => {
      const slot = form.querySelector(`.field__error[data-for="${field}"]`);
      const input = form.querySelector(`[name="${field}"]`);
      const text = Array.isArray(messages) ? messages.join(" ") : String(messages);
      if (slot) slot.textContent = text;
      else {
        formError.textContent = text;
        formError.hidden = false;
      }
      if (input) input.setAttribute("aria-invalid", "true");
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors();
    submitBtn.disabled = true;

    const data = Object.fromEntries(new FormData(form));
    delete data.csrfmiddlewaretoken;
    data.course = form.dataset.course;

    try {
      const res = await fetch(form.dataset.endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
        },
        body: JSON.stringify(data),
      });
      const body = await res.json();
      if (!res.ok) {
        showErrors(body);
        return;
      }
      document.getElementById("apply-form-area").hidden = true;
      const done = document.getElementById("apply-done");
      done.querySelector('[data-done="date"]').textContent = body.contact_date;
      done.querySelector('[data-done="email"]').textContent = body.email;
      done.hidden = false;
      window.scrollTo({ top: 0 });
    } catch (e) {
      formError.textContent = "네트워크 오류가 났어요. 잠시 후 다시 시도해 주세요.";
      formError.hidden = false;
    } finally {
      submitBtn.disabled = false;
    }
  });
})();
