// flight-deals page script. Plain JS, no framework, no external resources.
// Every write goes through fetch() with the X-Flight-Deals-Client header.
"use strict";

(function () {
  const CLIENT_HEADER = "X-Flight-Deals-Client";

  async function api(method, url, body) {
    const options = {
      method: method,
      headers: { [CLIENT_HEADER]: "1", Accept: "application/json" },
      credentials: "same-origin",
    };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(url, options);
    } catch (err) {
      return { ok: false, status: 0, data: { errors: { _: "無法連線到服務" } } };
    }
    let data = {};
    try {
      data = await response.json();
    } catch (err) {
      data = {};
    }
    return { ok: response.ok, status: response.status, data: data };
  }

  function flash(message, kind) {
    const box = document.getElementById("flash");
    if (!box) return;
    box.textContent = message;
    box.className = "flash flash-" + (kind || "info");
    box.setAttribute("role", kind === "error" ? "alert" : "status");
    box.hidden = false;
  }

  // Loading state: native disabled + aria-busy + optional busy label.
  function setBusy(button, busy) {
    if (busy) {
      if (button.getAttribute("data-idle-label") === null) {
        button.setAttribute("data-idle-label", button.textContent);
      }
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      const label = button.getAttribute("data-busy-label");
      if (label) button.textContent = label;
    } else {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      const idle = button.getAttribute("data-idle-label");
      if (idle !== null) button.textContent = idle;
      button.removeAttribute("data-idle-label");
    }
  }

  function firstError(data) {
    if (data && data.error) return data.error;
    if (data && data.errors) {
      const values = Object.values(data.errors);
      if (values.length) return values[0];
    }
    return "操作失敗";
  }

  function clearErrors(form) {
    form.querySelectorAll("[data-error-for]").forEach(function (el) {
      el.textContent = "";
    });
    form.querySelectorAll("[aria-invalid]").forEach(function (el) {
      el.removeAttribute("aria-invalid");
    });
  }

  function showErrors(form, errors) {
    let shown = false;
    Object.keys(errors || {}).forEach(function (field) {
      const target = form.querySelector('[data-error-for="' + field + '"]');
      const input = form.querySelector('[name="' + field + '"]');
      if (input) input.setAttribute("aria-invalid", "true");
      if (target) {
        target.textContent = errors[field];
        shown = true;
      }
    });
    if (!shown) {
      const general = form.querySelector('[data-error-for="_"]');
      if (general) {
        general.textContent = firstError({ errors: errors });
      }
    }
    const firstInvalid = form.querySelector('[aria-invalid="true"]');
    if (firstInvalid) firstInvalid.focus();
    else {
      const general = form.querySelector('[data-error-for="_"]');
      if (general && general.textContent) general.scrollIntoView({ block: "nearest" });
    }
  }

  // ---- watch form ----------------------------------------------------------

  function radioValue(form, name) {
    const checked = form.querySelector('input[name="' + name + '"]:checked');
    return checked ? checked.value : "";
  }

  function syncWatchForm(form) {
    const state = {
      trip_type: radioValue(form, "trip_type"),
      date_mode: radioValue(form, "date_mode"),
    };
    form.querySelectorAll("[data-show-when]").forEach(function (el) {
      const parts = el.getAttribute("data-show-when").split("=");
      el.hidden = state[parts[0]] !== parts[1];
    });
    form.querySelectorAll(".js-window-end-label").forEach(function (el) {
      el.textContent =
        state.trip_type === "one_way"
          ? el.getAttribute("data-label-oneway")
          : el.getAttribute("data-label-round");
    });
  }

  function collectWatch(form) {
    const value = function (name) {
      const el = form.querySelector('[name="' + name + '"]');
      return el ? el.value.trim() : "";
    };
    const tripType = radioValue(form, "trip_type");
    const dateMode = radioValue(form, "date_mode");
    const payload = {
      name: value("name"),
      origin: value("origin").toUpperCase(),
      destination: value("destination").toUpperCase(),
      trip_type: tripType,
      date_mode: dateMode,
      max_stops: value("max_stops"),
      budget: value("budget"),
      notify_on_new_low: form.querySelector('[name="notify_on_new_low"]').checked,
    };
    if (dateMode === "fixed") {
      payload.depart_date = value("depart_date");
      if (tripType === "round_trip") payload.return_date = value("return_date");
    } else {
      payload.window_start = value("window_start");
      payload.window_end = value("window_end");
      if (tripType === "round_trip") {
        payload.min_trip_days = value("min_trip_days");
        payload.max_trip_days = value("max_trip_days");
      }
    }
    return payload;
  }

  function initWatchForm() {
    const form = document.getElementById("watch-form");
    if (!form) return;
    form.addEventListener("change", function () {
      syncWatchForm(form);
    });
    syncWatchForm(form);
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      clearErrors(form);
      const method = form.getAttribute("data-mode") === "edit" ? "PUT" : "POST";
      const submit = form.querySelector('button[type="submit"]');
      setBusy(submit, true);
      const result = await api(method, form.getAttribute("data-url"), collectWatch(form));
      setBusy(submit, false);
      if (result.ok && result.data.id) {
        window.location.href = "/watches/" + result.data.id;
        return;
      }
      showErrors(form, result.data.errors || { _: firstError(result.data) });
    });
  }

  // ---- settings form -------------------------------------------------------

  function initSettingsForm() {
    const form = document.getElementById("settings-form");
    if (!form) return;
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      clearErrors(form);
      const payload = {};
      form.querySelectorAll("input[name]").forEach(function (input) {
        payload[input.name] = input.value.trim();
      });
      const submit = form.querySelector('button[type="submit"]');
      setBusy(submit, true);
      const result = await api("POST", "/api/settings", payload);
      setBusy(submit, false);
      if (result.ok) {
        flash("設定已儲存，下一輪掃描起生效", "ok");
        return;
      }
      showErrors(form, result.data.errors || { _: firstError(result.data) });
    });
  }

  // ---- action buttons ------------------------------------------------------

  async function onAction(button) {
    const action = button.getAttribute("data-action");
    const id = button.getAttribute("data-watch-id");
    let result;
    if (action === "set-enabled") {
      const enabled = button.getAttribute("data-enabled") === "true";
      setBusy(button, true);
      result = await api("POST", "/api/watches/" + id + "/status", { enabled: enabled });
      if (result.ok) {
        window.location.reload();
        return;
      }
      setBusy(button, false);
    } else if (action === "delete-watch") {
      const name = button.getAttribute("data-watch-name") || "";
      const confirmed = window.confirm(
        "確定要刪除監看「" + name + "」嗎？\n此監看的所有價格紀錄與通知紀錄都會一併刪除，無法復原。"
      );
      if (!confirmed) return;
      setBusy(button, true);
      result = await api("DELETE", "/api/watches/" + id);
      if (result.ok) {
        const redirect = button.getAttribute("data-redirect");
        if (redirect) window.location.href = redirect;
        else window.location.reload();
        return;
      }
      setBusy(button, false);
    } else if (action === "scan-now") {
      setBusy(button, true);
      result = await api("POST", "/api/watches/" + id + "/scan");
      setBusy(button, false);
      if (result.ok) {
        flash(result.data.message || "已排入立即查價", "ok");
        return;
      }
    } else if (action === "telegram-test") {
      const out = document.getElementById("telegram-test-result");
      setBusy(button, true);
      if (out) {
        out.className = "inline-result";
        out.textContent = "發送中…";
      }
      result = await api("POST", "/api/telegram/test");
      setBusy(button, false);
      const text = result.ok ? result.data.message : "失敗：" + firstError(result.data);
      if (out) {
        out.textContent = text;
        out.className = "inline-result " + (result.ok ? "result-ok" : "result-fail");
      }
      return;
    } else {
      return;
    }
    flash(firstError(result.data), "error");
  }

  function initActions() {
    document.addEventListener("click", function (event) {
      const button = event.target.closest("[data-action]");
      if (!button || button.disabled) return;
      event.preventDefault();
      onAction(button);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initWatchForm();
    initSettingsForm();
    initActions();
  });
})();
