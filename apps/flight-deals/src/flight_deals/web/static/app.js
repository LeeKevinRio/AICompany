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
      let input = form.querySelector('[name="' + field + '"]');
      if (input && input.type === "hidden") {
        input = form.querySelector('[data-combo-for="' + field + '"]');
      }
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
      date_input: radioValue(form, "date_input"),
    };
    form.querySelectorAll("[data-show-when]").forEach(function (el) {
      // Several conditions may be joined with commas; all of them must match.
      const visible = el
        .getAttribute("data-show-when")
        .split(",")
        .every(function (condition) {
          const parts = condition.split("=");
          return state[parts[0]] === parts[1];
        });
      el.hidden = !visible;
    });
    form.querySelectorAll(".js-window-end-label").forEach(function (el) {
      el.textContent =
        state.trip_type === "one_way"
          ? el.getAttribute("data-label-oneway")
          : el.getAttribute("data-label-round");
    });
  }

  // Whole numbers become ints; anything else is passed through as the raw
  // string so the server can reject it with a clear message.
  function toInt(text) {
    return /^-?\d+$/.test(text) ? parseInt(text, 10) : text;
  }

  function hourOrNull(text) {
    return text === "" ? null : toInt(text);
  }

  // Disable the unchecked airline boxes once the cap is reached.
  function initAirlinePicker() {
    const list = document.getElementById("airline-list");
    if (!list) return;
    const max = parseInt(list.getAttribute("data-max"), 10) || 5;
    const boxes = list.querySelectorAll('input[type="checkbox"]');
    const sync = function () {
      const checked = list.querySelectorAll("input:checked").length;
      boxes.forEach(function (box) {
        box.disabled = checked >= max && !box.checked;
      });
    };
    list.addEventListener("change", sync);
    sync();
  }

  function collectWatch(form) {
    const value = function (name) {
      const el = form.querySelector('[name="' + name + '"]');
      return el ? el.value.trim() : "";
    };
    // Airport code: the hidden input when an option was picked, otherwise the
    // raw visible text so the server can reject it (never fall back silently).
    const airport = function (name) {
      const code = value(name);
      if (code) return code.toUpperCase();
      const visible = form.querySelector('[data-combo-for="' + name + '"]');
      return visible ? visible.value.trim().toUpperCase() : "";
    };
    const tripType = radioValue(form, "trip_type");
    const dateMode = radioValue(form, "date_mode");
    const payload = {
      name: value("name"),
      origin: airport("origin"),
      destination: airport("destination"),
      trip_type: tripType,
      date_mode: dateMode,
      max_stops: value("max_stops"),
      budget: value("budget"),
      notify_on_new_low: form.querySelector('[name="notify_on_new_low"]').checked,
    };
    payload.adults = toInt(value("adults"));
    payload.children = toInt(value("children"));
    payload.cabin = value("cabin");
    payload.airlines = Array.prototype.map.call(
      form.querySelectorAll('input[name="airlines"]:checked'),
      function (el) {
        return el.value;
      }
    );
    payload.dep_hour_from = hourOrNull(value("dep_hour_from"));
    payload.dep_hour_to = hourOrNull(value("dep_hour_to"));
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

  // ---- airport combobox ----------------------------------------------------
  // All matching and ordering happens server-side; this only renders the
  // results in the order received (ADR-0002 C-22).

  const COMBO_DEBOUNCE_MS = 150;

  function initCombobox(root) {
    const field = root.getAttribute("data-combo");
    const input = root.querySelector(".combo-input");
    const list = root.querySelector(".combo-list");
    const status = root.querySelector(".combo-status");
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = field;
    hidden.value = input.getAttribute("data-code") || "";
    root.appendChild(hidden);

    let items = [];
    let active = -1;
    let timer = null;
    let controller = null;
    let seq = 0;

    function cancelPending() {
      if (timer) clearTimeout(timer);
      timer = null;
      if (controller) controller.abort();
      controller = null;
      seq += 1;
    }

    function announce(text) {
      // Clear first so a repeated message is announced again by screen readers.
      status.textContent = "";
      setTimeout(function () {
        status.textContent = text;
      }, 50);
    }

    function clearFieldError() {
      input.removeAttribute("aria-invalid");
      const slot = root.querySelector("[data-error-for]");
      if (slot) slot.textContent = "";
    }

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function setActive(index) {
      const options = list.children;
      if (active >= 0 && options[active]) options[active].setAttribute("aria-selected", "false");
      active = index;
      if (active >= 0 && options[active]) {
        options[active].setAttribute("aria-selected", "true");
        input.setAttribute("aria-activedescendant", options[active].id);
        options[active].scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function select(index) {
      const item = items[index];
      if (!item) return;
      cancelPending();
      hidden.value = item.code;
      input.value = item.display;
      clearFieldError();
      close();
      root.dispatchEvent(
        new CustomEvent("combo-select", { detail: { code: item.code, display: item.display } })
      );
      if (root.hasAttribute("data-combo-multi")) {
        // Multi-select pickers only emit the event; the input is reset for the next pick.
        hidden.value = "";
        input.value = "";
        items = [];
        list.textContent = "";
      }
    }

    function render(failed) {
      list.textContent = "";
      items.forEach(function (item, index) {
        const li = document.createElement("li");
        li.id = "opt-" + field + "-" + index;
        li.className = "combo-option";
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        li.textContent = item.label;
        li.addEventListener("mousedown", function (event) {
          event.preventDefault();
        });
        li.addEventListener("click", function () {
          select(index);
        });
        list.appendChild(li);
      });
      active = -1;
      input.removeAttribute("aria-activedescendant");
      if (items.length && document.activeElement === input) {
        list.hidden = false;
        input.setAttribute("aria-expanded", "true");
        status.textContent = items.length + " 筆結果";
      } else {
        close();
        if (failed) status.textContent = "暫時無法取得機場清單";
        else status.textContent = input.value.trim() ? "找不到符合的機場或城市" : "";
      }
    }

    async function search(query) {
      if (controller) controller.abort();
      controller = new AbortController();
      const mine = ++seq;
      let result = [];
      let failed = false;
      try {
        const response = await fetch("/api/airports?q=" + encodeURIComponent(query), {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (response.ok) {
          const data = await response.json();
          if (data && Array.isArray(data.items)) result = data.items;
          else failed = true;
        } else {
          failed = true;
        }
      } catch (err) {
        if (err && err.name === "AbortError") return;
        result = [];
        failed = true;
      }
      if (mine !== seq) return;
      items = result;
      render(failed);
    }

    input.addEventListener("input", function () {
      hidden.value = "";
      close();
      if (timer) clearTimeout(timer);
      // Drop any in-flight response from the previous keystroke, otherwise it
      // could reopen the list with stale results during the debounce window.
      if (controller) controller.abort();
      seq += 1;
      const query = input.value.trim();
      if (!query) {
        items = [];
        render();
        return;
      }
      timer = setTimeout(function () {
        search(query);
      }, COMBO_DEBOUNCE_MS);
    });

    // Clicking the scrollbar must not blur the input and close the list.
    list.addEventListener("mousedown", function (event) {
      event.preventDefault();
    });

    input.addEventListener("keydown", function (event) {
      // Ignore keys that belong to an IME composition (e.g. Zhuyin).
      if (event.isComposing || event.keyCode === 229) return;
      const open = !list.hidden && items.length > 0;
      if (event.key === "ArrowDown") {
        if (!open) return;
        event.preventDefault();
        setActive(active + 1 >= items.length ? 0 : active + 1);
      } else if (event.key === "ArrowUp") {
        if (!open) return;
        event.preventDefault();
        setActive(active <= 0 ? items.length - 1 : active - 1);
      } else if (event.key === "Enter") {
        if (!open) return;
        event.preventDefault();
        if (active >= 0) {
          select(active);
        } else if (
          items.length === 1 ||
          items[0].code.toLowerCase() === input.value.trim().toLowerCase()
        ) {
          // Selection conditions only: single result, or first code equals the typed text.
          select(0);
        } else {
          announce("請用上下鍵選取");
        }
      } else if (event.key === "Escape") {
        if (open) {
          event.preventDefault();
          close();
        }
      } else if (event.key === "Tab") {
        close();
      }
    });

    input.addEventListener("blur", function () {
      cancelPending();
      const text = input.value.trim();
      if (
        hidden.value === "" &&
        /^[A-Za-z]{3}$/.test(text) &&
        items.length > 0 &&
        items[0].code.toLowerCase() === text.toLowerCase()
      ) {
        select(0);
      } else {
        close();
      }
    });
  }

  function initComboboxes(form) {
    form.querySelectorAll("[data-combo]").forEach(initCombobox);
  }

  // ---- expired date hints --------------------------------------------------
  // A date earlier than the field min is a hint, not an error; the server rules
  // are unchanged (unchanged old dates may still be saved).

  const EXPIRED_TEXT = "此日期已過，請更新";

  function initExpiredHints(form) {
    ["depart_date", "return_date", "window_start", "window_end"].forEach(function (name) {
      const input = form.querySelector('[name="' + name + '"]');
      const slot = document.getElementById("h-" + name);
      if (!input || !slot) return;
      const check = function () {
        const min = input.getAttribute("min");
        const expired = Boolean(input.value) && Boolean(min) && input.value < min;
        slot.textContent = expired ? EXPIRED_TEXT : "";
      };
      input.addEventListener("input", check);
      input.addEventListener("change", check);
      check();
    });
  }

  function initWatchForm() {
    const form = document.getElementById("watch-form");
    if (!form) return;
    initComboboxes(form);
    initExpiredHints(form);
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

  function initRetentionHints(form) {
    form.querySelectorAll("input[data-retention-warn]").forEach(function (input) {
      const hint = document.getElementById(input.getAttribute("data-retention-warn"));
      if (!hint) return;
      const original = Number(input.defaultValue);
      input.addEventListener("input", function () {
        const next = Number(input.value);
        if (input.value.trim() !== "" && Number.isFinite(next) && next > 0 && next < original) {
          hint.textContent = "下次清除將刪除超過 " + next + " 天的資料";
        } else {
          hint.textContent = "";
        }
      });
    });
  }

  function initSettingsForm() {
    const form = document.getElementById("settings-form");
    if (!form) return;
    initRetentionHints(form);
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      clearErrors(form);
      const payload = {};
      Array.prototype.forEach.call(form.elements, function (input) {
        if (input.tagName !== "INPUT" || !input.name) return;
        payload[input.name] = input.type === "checkbox" ? input.checked : input.value.trim();
      });
      const submit = form.querySelector('button[type="submit"]');
      setBusy(submit, true);
      const result = await api("POST", "/api/settings", payload);
      setBusy(submit, false);
      if (result.ok) {
        const notice = result.data && result.data.notice;
        flash(notice ? "設定已儲存。" + notice : "設定已儲存，下一輪掃描起生效", "ok");
        return;
      }
      showErrors(form, result.data.errors || { _: firstError(result.data) });
    });
  }

  // ---- action buttons ------------------------------------------------------

  // ---- scan now with polling ----------------------------------------------

  const POLL_INTERVAL_MS = 2000; // must not go below 2 seconds
  const POLL_LIMIT_MS = 90000;
  // Bumped on every pagehide/pageshow so a poll loop started before a bfcache
  // restore stops, and a new click always gets its own live token.
  let pollGeneration = 0;
  window.addEventListener("pagehide", function () {
    pollGeneration += 1;
  });
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) {
      pollGeneration += 1;
      document.querySelectorAll('[data-action="scan-now"]').forEach(function (b) {
        setBusy(b, false);
      });
    }
  });

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  async function readScanStatus(id) {
    const result = await api("GET", "/api/watches/" + id + "/scan-status");
    if (!result.ok || !result.data) return null;
    return result.data;
  }

  async function scanNow(button, id) {
    const token = ++pollGeneration;
    setBusy(button, true);
    const base = await readScanStatus(id);
    if (token !== pollGeneration) return;
    const baseRunId = base ? base.scan_run_id : null;
    const baseRunning = Boolean(base) && base.status === "running";
    const result = await api("POST", "/api/watches/" + id + "/scan");
    if (token !== pollGeneration) return;
    if (!result.ok) {
      // 409 means disabled or expired; show the server message, do not poll.
      setBusy(button, false);
      flash(firstError(result.data), "error");
      return;
    }
    if (baseRunning) flash("已有查價進行中", "info");
    else flash(result.data.message || "已排入立即查價", "ok");
    const startedAt = Date.now();
    let sawRunning = baseRunning;
    while (Date.now() - startedAt + POLL_INTERVAL_MS <= POLL_LIMIT_MS) {
      await sleep(POLL_INTERVAL_MS);
      if (token !== pollGeneration) return;
      const current = await readScanStatus(id);
      if (token !== pollGeneration) return;
      if (!current) continue;
      if (current.status === "running") sawRunning = true;
      const finished = current.status !== "running";
      const isNewRun = current.scan_run_id !== baseRunId;
      // A run already running at baseline completes with the same run id.
      if (finished && (isNewRun || baseRunning)) {
        window.location.reload();
        return;
      }
    }
    setBusy(button, false);
    flash(
      sawRunning
        ? "仍在查價中，完成後請重新整理"
        : "尚未偵測到新的查價結果，請稍後重新整理",
      "info"
    );
  }

  // ---- unembedded-results hint (round trip + business/first + 2+ pax) -----

  function initUnembeddedHint() {
    document.querySelectorAll("[data-unembedded-hint]").forEach(function (hint) {
      const form = hint.closest("form");
      if (!form) return;
      const count = function (name) {
        const el = form.querySelector('[name="' + name + '"]');
        const n = el ? parseInt(el.value, 10) : 0;
        return Number.isNaN(n) ? 0 : n;
      };
      const cabinEl = form.querySelector('[name="cabin"]');
      const sync = function () {
        const cabin = cabinEl ? cabinEl.value : "";
        hint.hidden = !(
          radioValue(form, "trip_type") === "round_trip" &&
          (cabin === "business" || cabin === "first") &&
          count("adults") + count("children") >= 2
        );
      };
      form.addEventListener("change", sync);
      form.addEventListener("input", sync);
      sync();
    });
  }

  // ---- explore form ----------------------------------------------------------

  // Rough count of departure days from today to the end of the month. The
  // server decides the real number; this is only a preview.
  function estimateCells(box, month) {
    const maxCells = parseInt(box.getAttribute("data-max-cells"), 10) || 31;
    const match = /^(\d{4})-(\d{2})$/.exec(month);
    if (!match) return maxCells;
    const year = parseInt(match[1], 10);
    const mon = parseInt(match[2], 10);
    const daysInMonth = new Date(year, mon, 0).getDate();
    const todayText =
      box.getAttribute("data-today") ||
      new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Taipei" });
    const prefix = year + "-" + String(mon).padStart(2, "0");
    let days = daysInMonth;
    if (todayText.slice(0, 7) === prefix) {
      days = daysInMonth - parseInt(todayText.slice(8, 10), 10) + 1;
    } else if (todayText.slice(0, 7) > prefix) {
      days = 0;
    }
    return Math.max(0, Math.min(days, maxCells));
  }

  function collectExplore(form) {
    const value = function (name) {
      const el = form.querySelector('[name="' + name + '"]');
      return el ? el.value.trim() : "";
    };
    const airport = function (name) {
      const code = value(name);
      if (code) return code.toUpperCase();
      const visible = form.querySelector('[data-combo-for="' + name + '"]');
      return visible ? visible.value.trim().toUpperCase() : "";
    };
    const tripType = radioValue(form, "trip_type");
    return {
      origin: airport("origin"),
      destination: airport("destination"),
      trip_type: tripType,
      month: value("month"),
      trip_days: tripType === "round_trip" ? toInt(value("trip_days")) : null,
      max_stops: value("max_stops"),
      adults: toInt(value("adults")),
      children: toInt(value("children")),
      cabin: value("cabin"),
      airlines: Array.prototype.map.call(
        form.querySelectorAll('input[name="airlines"]:checked'),
        function (el) {
          return el.value;
        }
      ),
      dep_hour_from: hourOrNull(value("dep_hour_from")),
      dep_hour_to: hourOrNull(value("dep_hour_to")),
    };
  }

  function initExploreForm() {
    const form = document.getElementById("explore-form");
    if (!form) return;
    initComboboxes(form);
    const box = document.getElementById("explore-estimate");
    const monthEl = form.querySelector('[name="month"]');
    const syncAll = function () {
      syncWatchForm(form);
      if (!box || !monthEl) return;
      const cells = estimateCells(box, monthEl.value);
      const left = box.getAttribute("data-hourly-left");
      const reserve = box.getAttribute("data-reserve");
      let text = "預計查詢約 " + cells + " 次";
      if (left !== null && left !== "") {
        text += "／本小時剩餘 " + left + " 次";
        if (reserve !== null && reserve !== "") text += "（保留 " + reserve + " 次給排程）";
      }
      box.textContent = text;
    };
    form.addEventListener("change", syncAll);
    syncAll();
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      clearErrors(form);
      const submit = form.querySelector('button[type="submit"]');
      setBusy(submit, true);
      const result = await api("POST", form.getAttribute("data-url"), collectExplore(form));
      setBusy(submit, false);
      if (result.ok && result.data.id) {
        window.location.href = "/explorations/" + result.data.id;
        return;
      }
      if (result.status === 409) {
        showErrors(form, { _: result.data.message || "目前無法開始探索，請稍後再試" });
        return;
      }
      showErrors(form, result.data.errors || { _: result.data.message || "無法開始探索，請檢查輸入" });
    });
  }

  // ---- exploration progress polling -----------------------------------------

  const EXPLORE_NO_PROGRESS_MS = 120000;

  // Shared by the exploration and comparison progress pages.
  async function pollProgress(root, statusUrl, defaultTotal) {
    const total = parseInt(root.getAttribute("data-total"), 10) || defaultTotal;
    let lastDone = parseInt(root.getAttribute("data-done"), 10) || 0;
    const text = document.getElementById("progress-text");
    const bar = document.getElementById("progress-bar");
    const note = document.getElementById("progress-note");
    const token = ++pollGeneration;
    const startedAt = Date.now();
    let lastProgressAt = startedAt;
    const hardLimitMs = (total * 30 + 60) * 1000;
    while (true) {
      await sleep(POLL_INTERVAL_MS);
      if (token !== pollGeneration) return;
      const now = Date.now();
      if (now - lastProgressAt >= EXPLORE_NO_PROGRESS_MS || now - startedAt >= hardLimitMs) {
        if (note) note.hidden = false;
        return;
      }
      const result = await api("GET", statusUrl);
      if (token !== pollGeneration) return;
      if (!result.ok || !result.data) continue;
      const data = result.data;
      if (data.status === "done" || data.status === "failed") {
        window.location.reload();
        return;
      }
      if (typeof data.done === "number") {
        if (data.done > lastDone) {
          lastDone = data.done;
          lastProgressAt = Date.now();
        }
        if (text) text.textContent = "已查 " + data.done + "／共 " + data.total;
        if (bar) {
          bar.max = data.total;
          bar.value = data.done;
        }
      }
    }
  }

  async function pollExploration(root) {
    const match = /^\/explorations\/(\d+)\/?$/.exec(window.location.pathname);
    if (!match) return;
    await pollProgress(root, "/api/explorations/" + match[1] + "/status", 31);
  }

  function initExplorationPage() {
    const root = document.getElementById("exploration-progress");
    if (root) pollExploration(root);
  }

  // ---- multi-destination comparison ------------------------------------------

  function collectCompare(form) {
    const value = function (name) {
      const el = form.querySelector('[name="' + name + '"]');
      return el ? el.value.trim() : "";
    };
    const origin = value("origin");
    const visible = form.querySelector('[data-combo-for="origin"]');
    const tripType = radioValue(form, "trip_type");
    const round = tripType === "round_trip";
    const dateInput = round ? radioValue(form, "date_input") : "fixed";
    const codes = Array.prototype.map.call(
      form.querySelectorAll("#compare-destinations li[data-code]"),
      function (li) {
        return li.getAttribute("data-code");
      }
    );
    return {
      origin: (origin || (visible ? visible.value.trim() : "")).toUpperCase(),
      destinations: codes,
      trip_type: tripType,
      date_input: dateInput,
      depart_date: value("depart_date"),
      return_date: round && dateInput === "fixed" ? value("return_date") : null,
      trip_days: round && dateInput === "stay" ? toInt(value("trip_days")) : null,
      max_stops: value("max_stops"),
      cabin: value("cabin"),
    };
  }

  function initCompareForm() {
    const form = document.getElementById("compare-form");
    if (!form) return;
    initComboboxes(form);
    const list = document.getElementById("compare-destinations");
    const empty = document.getElementById("compare-destinations-empty");
    const live = document.getElementById("compare-destinations-status");
    const pick = form.querySelector('[data-combo="destination_pick"]');
    const pickInput = pick ? pick.querySelector(".combo-input") : null;
    const slot = form.querySelector('[data-error-for="destinations"]');
    const box = document.getElementById("compare-estimate");
    const maxItems = parseInt(list.getAttribute("data-max"), 10) || 8;

    const announce = function (text) {
      if (live) live.textContent = text;
    };
    const setPickError = function (text) {
      if (slot) slot.textContent = text;
      if (pickInput) {
        if (text) pickInput.setAttribute("aria-invalid", "true");
        else pickInput.removeAttribute("aria-invalid");
      }
    };
    const codes = function () {
      return Array.prototype.map.call(list.querySelectorAll("li[data-code]"), function (li) {
        return li.getAttribute("data-code");
      });
    };
    const syncEstimate = function () {
      const count = codes().length;
      if (empty) empty.hidden = count > 0;
      if (!box) return;
      const reserve = box.getAttribute("data-reserve");
      const available = box.getAttribute("data-available");
      let text = "預計查詢 " + count + " 次";
      if (available !== null && available !== "") {
        text += "／本小時可用 " + available + " 次";
        if (reserve !== null && reserve !== "") text += "（已保留 " + reserve + " 次給排程）";
        const short = count > 0 && count > parseInt(available, 10);
        if (short) text += "。本小時額度不足以開始比價，請稍後再試";
      }
      box.textContent = text;
    };
    const bindRemove = function (li) {
      const button = li.querySelector("[data-remove-destination]");
      if (!button) return;
      button.addEventListener("click", function () {
        const name = li.getAttribute("data-label") || li.getAttribute("data-code");
        li.remove();
        setPickError("");
        announce("已移除 " + name);
        syncEstimate();
        if (pickInput) pickInput.focus();
      });
    };

    list.querySelectorAll("li[data-code]").forEach(bindRemove);

    if (pick) {
      pick.addEventListener("combo-select", function (event) {
        const code = String(event.detail.code || "").toUpperCase();
        const display = event.detail.display || code;
        if (!code) return;
        if (codes().indexOf(code) !== -1) {
          setPickError("已加入此目的地");
          return;
        }
        if (codes().length >= maxItems) {
          setPickError("最多只能比較 " + maxItems + " 個目的地");
          return;
        }
        const li = document.createElement("li");
        li.className = "chip";
        li.setAttribute("data-code", code);
        li.setAttribute("data-label", display);
        const label = document.createElement("span");
        label.textContent = display;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "chip-remove";
        remove.setAttribute("data-remove-destination", "");
        remove.setAttribute("aria-label", "移除 " + display);
        remove.textContent = "移除";
        li.appendChild(label);
        li.appendChild(remove);
        list.appendChild(li);
        bindRemove(li);
        setPickError("");
        announce("已加入 " + display + "，目前 " + codes().length + " 個目的地");
        syncEstimate();
      });
    }

    form.addEventListener("change", function () {
      syncWatchForm(form);
    });
    syncWatchForm(form);
    syncEstimate();

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      clearErrors(form);
      const submit = form.querySelector('button[type="submit"]');
      setBusy(submit, true);
      const result = await api("POST", form.getAttribute("data-url"), collectCompare(form));
      setBusy(submit, false);
      if (result.ok && result.data.id) {
        window.location.href =
          "/comparisons/" + result.data.id + (result.data.reused === true ? "?reused=1" : "");
        return;
      }
      const general = form.querySelector('[data-error-for="_"]');
      if (result.status === 409) {
        showErrors(form, { _: result.data.message || "目前無法開始比價，請稍後再試" });
        if (general && result.data.progress_url) {
          general.appendChild(document.createTextNode(" "));
          const link = document.createElement("a");
          link.href = result.data.progress_url;
          link.textContent = "查看進行中的進度";
          general.appendChild(link);
        }
        return;
      }
      const errors = result.data.errors || { _: result.data.message || "無法開始比價，請檢查輸入" };
      showErrors(form, errors);
      if (errors.destinations && pickInput) {
        pickInput.setAttribute("aria-invalid", "true");
        pickInput.focus();
      }
    });
  }

  function initComparisonPage() {
    const root = document.getElementById("comparison-progress");
    if (!root) return;
    const url = root.getAttribute("data-status-url");
    if (url) pollProgress(root, url, 8);
  }

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
      await scanNow(button, id);
      return;
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
    initAirlinePicker();
    initUnembeddedHint();
    initExploreForm();
    initExplorationPage();
    initCompareForm();
    initComparisonPage();
    initSettingsForm();
    initActions();
  });
})();
