// Behaviour of the pages. No inline scripts (Content-Security-Policy).
(function () {
  "use strict";

  const TASK_POLL_MS = 2000;
  const TASK_MAX_WAIT_MS = 15 * 60 * 1000;
  const TASK_MAX_FAILURES = 3;
  const STATUS_POLL_MS = 15000;
  const STATUS_CLASSES = { running: "success", exited: "danger" };

  function each(selector, callback, root) {
    (root || document).querySelectorAll(selector).forEach(callback);
  }

  // ----- navigation on small screens -----
  each("[data-nav-toggle]", function (button) {
    button.addEventListener("click", function () {
      const nav = document.getElementById(button.getAttribute("aria-controls"));
      const open = nav.classList.toggle("open");
      button.setAttribute("aria-expanded", String(open));
    });
  });

  // ----- theme: light or dark -----
  each("[data-theme-toggle]", function (button) {
    const root = document.documentElement;
    function show() {
      const dark = root.dataset.theme === "dark";
      // the icon itself follows data-theme (CSS): sun in the dark theme, moon in the light one
      const label = dark ? "Switch to the light theme" : "Switch to the dark theme";
      button.title = label;
      button.setAttribute("aria-label", label);
    }
    button.addEventListener("click", function () {
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try {
        window.localStorage.setItem("mtas-theme", next);
      } catch (error) {
        // no storage: the choice is kept for this page only
      }
      show();
    });
    show();
    button.hidden = false;
  });

  // ----- drop-down menus: close on a click outside and with Escape -----
  const menus = document.querySelectorAll("[data-menu]");
  function closeMenus(except) {
    menus.forEach(function (menu) {
      if (menu !== except) menu.removeAttribute("open");
    });
  }
  menus.forEach(function (menu) {
    menu.addEventListener("toggle", function () {
      if (menu.open) closeMenus(menu);
    });
  });
  document.addEventListener("click", function (event) {
    if (!event.target.closest("[data-menu]")) closeMenus(null);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeMenus(null);
  });

  // ----- copy to clipboard -----
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // http pages have no clipboard API
    const area = document.createElement("textarea");
    area.value = text;
    area.className = "sr-only";
    document.body.appendChild(area);
    area.select();
    const done = document.execCommand("copy");
    area.remove();
    return done ? Promise.resolve() : Promise.reject(new Error("copy failed"));
  }

  each("[data-copy]", function (button) {
    const label = button.querySelector("[data-label]");
    button.addEventListener("click", function () {
      copyText(button.dataset.copy).then(
        function () {
          button.classList.add("is-done");
          if (label) label.textContent = "Copied";
          setTimeout(function () {
            button.classList.remove("is-done");
            if (label) label.textContent = "Copy";
          }, 1500);
        },
        function () {
          if (label) label.textContent = "Not copied";
        }
      );
    });
  });

  // ----- show and hide passwords -----
  each("[data-reveal]", function (button) {
    const target = document.getElementById(button.dataset.reveal);
    const label = button.querySelector("[data-label]");
    button.addEventListener("click", function () {
      const shown = button.getAttribute("aria-pressed") === "true";
      target.textContent = shown ? "••••••••" : target.dataset.secret;
      button.setAttribute("aria-pressed", String(!shown));
      if (label) label.textContent = shown ? "Show" : "Hide";
    });
  });

  // ----- date picker: DD.MM.YYYY HH:MM, weeks start on Monday -----
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];
  const WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

  function pad(number) {
    return String(number).padStart(2, "0");
  }

  function parseDate(text) {
    const match = /^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?$/.exec(text.trim());
    if (!match) return null;
    const date = new Date(+match[3], +match[2] - 1, +match[1],
      match[4] === undefined ? 23 : +match[4], match[5] === undefined ? 59 : +match[5]);
    return date.getDate() === +match[1] ? date : null;
  }

  function formatDate(date) {
    return pad(date.getDate()) + "." + pad(date.getMonth() + 1) + "." + date.getFullYear() +
      " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  each("input[data-datepicker]", function (input) {
    const wrap = input.closest(".datepicker");
    const toggle = wrap.querySelector(".datepicker-toggle");
    const panel = element("div", "datepicker-panel");
    panel.hidden = true;
    wrap.appendChild(panel);

    let selected = null;
    let shown = new Date();

    function hourMinute() {
      return selected ? [selected.getHours(), selected.getMinutes()] : [23, 59];
    }

    function pick(year, month, day) {
      const time = hourMinute();
      selected = new Date(year, month, day, time[0], time[1]);
      input.value = formatDate(selected);
      draw();
    }

    function setTime(text) {
      const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
      if (!match || +match[1] > 23 || +match[2] > 59) return false;
      const base = selected || new Date();
      selected = new Date(base.getFullYear(), base.getMonth(), base.getDate(), +match[1], +match[2]);
      input.value = formatDate(selected);
      draw();
      return true;
    }

    function draw() {
      panel.replaceChildren();
      const head = element("div", "datepicker-head");
      const previous = element("button", "btn sm", "‹");
      const next = element("button", "btn sm", "›");
      previous.type = next.type = "button";
      previous.setAttribute("aria-label", "Previous month");
      next.setAttribute("aria-label", "Next month");
      previous.addEventListener("click", function () {
        shown = new Date(shown.getFullYear(), shown.getMonth() - 1, 1);
        draw();
      });
      next.addEventListener("click", function () {
        shown = new Date(shown.getFullYear(), shown.getMonth() + 1, 1);
        draw();
      });
      head.append(previous, element("strong", "", MONTHS[shown.getMonth()] + " " + shown.getFullYear()), next);
      panel.appendChild(head);

      const grid = element("div", "datepicker-grid");
      WEEKDAYS.forEach(function (name) {
        grid.appendChild(element("span", "datepicker-weekday", name));
      });
      const year = shown.getFullYear();
      const month = shown.getMonth();
      const offset = (new Date(year, month, 1).getDay() + 6) % 7;
      for (let i = 0; i < offset; i += 1) grid.appendChild(element("span"));
      const today = new Date();
      const days = new Date(year, month + 1, 0).getDate();
      for (let day = 1; day <= days; day += 1) {
        const button = element("button", "datepicker-day", String(day));
        button.type = "button";
        if (day === today.getDate() && month === today.getMonth() && year === today.getFullYear()) {
          button.classList.add("is-today");
        }
        if (selected && day === selected.getDate() && month === selected.getMonth() && year === selected.getFullYear()) {
          button.classList.add("is-selected");
        }
        button.addEventListener("click", function () {
          pick(year, month, day);
        });
        grid.appendChild(button);
      }
      panel.appendChild(grid);

      const foot = element("div", "datepicker-foot");
      const time = element("input", "input datepicker-time");
      const current = hourMinute();
      time.value = pad(current[0]) + ":" + pad(current[1]);
      time.setAttribute("aria-label", "Time (HH:MM)");
      time.maxLength = 5;
      time.addEventListener("change", function () {
        if (!setTime(time.value)) time.classList.add("is-invalid");
      });
      const endOfDay = element("button", "btn sm", "23:59");
      const done = element("button", "btn sm primary", "Done");
      const clear = element("button", "btn sm", "Clear");
      endOfDay.type = done.type = clear.type = "button";
      endOfDay.addEventListener("click", function () {
        setTime("23:59");
      });
      clear.addEventListener("click", function () {
        selected = null;
        input.value = "";
        close();
      });
      done.addEventListener("click", function () {
        if (time.value && !setTime(time.value)) return;
        close();
      });
      foot.append(time, endOfDay, clear, done);
      panel.appendChild(foot);
    }

    function open() {
      selected = parseDate(input.value);
      shown = selected ? new Date(selected.getFullYear(), selected.getMonth(), 1) : new Date();
      draw();
      panel.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
    }

    function close() {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", function () {
      if (panel.hidden) open();
      else close();
    });
    input.addEventListener("blur", function () {
      const date = parseDate(input.value);
      if (date) input.value = formatDate(date);
    });
    document.addEventListener("click", function (event) {
      if (!wrap.contains(event.target)) close();
    });
    wrap.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        close();
        toggle.focus();
      }
      if (event.key === "Enter" && event.target.classList.contains("datepicker-time")) {
        event.preventDefault();
        if (setTime(event.target.value)) close();
      }
    });
  });

  // ----- forms: confirm, no double submit -----
  function uploadTooLarge(form) {
    if (!form.dataset.maxUpload) return false;
    let total = 0;
    each("input[type=file]", function (input) {
      Array.prototype.forEach.call(input.files || [], function (file) {
        total += file.size;
      });
    }, form);
    const limit = Number(form.dataset.maxUpload);
    const error = form.querySelector("[data-upload-error]");
    const tooLarge = total > limit;
    if (error) {
      error.hidden = !tooLarge;
      error.textContent = tooLarge
        ? "The files are too large: " + (total / 1048576).toFixed(1) + " MB. Upload at most " + Math.round(limit / 1048576) + " MB at once."
        : "";
    }
    return tooLarge;
  }

  each("form", function (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
        event.preventDefault();
        return;
      }
      if (uploadTooLarge(form)) {
        event.preventDefault();
        return;
      }
      each("button[type=submit], button:not([type])", function (button) {
        button.disabled = true;
      }, form);
      each("[data-busy]", function (element) {
        element.hidden = false;
      }, form);
    });
  });

  // ----- filter the rows of a table -----
  each("[data-filter]", function (input) {
    const table = document.getElementById(input.dataset.filter);
    const counter = document.querySelector('[data-filter-count="' + input.dataset.filter + '"]');
    function apply() {
      const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      let shown = 0;
      each("tbody tr", function (row) {
        const text = row.textContent.toLowerCase();
        const match = words.every(function (word) {
          return text.includes(word);
        });
        row.hidden = !match;
        if (match) shown += 1;
      }, table);
      if (counter) counter.textContent = shown;
    }
    input.addEventListener("input", apply);
    apply();
  });

  // ----- sort a table by a column -----
  each("table th[data-sort]", function (header) {
    header.addEventListener("click", function () {
      const table = header.closest("table");
      const body = table.tBodies[0];
      const index = Array.from(header.parentNode.children).indexOf(header);
      const ascending = header.getAttribute("aria-sort") !== "ascending";
      const numeric = header.dataset.sort === "number";

      function key(row) {
        const cell = row.children[index];
        const text = (cell.dataset.value || cell.textContent).trim();
        return numeric ? parseFloat(text) || 0 : text.toLowerCase();
      }

      const rows = Array.from(body.rows).sort(function (a, b) {
        const x = key(a);
        const y = key(b);
        if (x === y) return 0;
        return (x > y ? 1 : -1) * (ascending ? 1 : -1);
      });
      rows.forEach(function (row) {
        body.appendChild(row);
      });
      each("th[data-sort]", function (other) {
        other.removeAttribute("aria-sort");
      }, table);
      header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
    });
  });

  // ----- background tasks: reload the page when a task is done -----
  // Stops after TASK_MAX_WAIT_MS or when the server does not know the task.
  // The server marks lost and too long tasks as failed, so a reload shows the result.
  function stopWaiting(element, text) {
    const message = document.createElement("span");
    message.className = "badge warning";
    message.textContent = text + " ";
    const link = document.createElement("a");
    link.href = window.location.href;
    link.textContent = "Reload the page";
    message.appendChild(link);
    element.replaceChildren(message);
  }

  each("[data-task]", function (element) {
    const started = Date.now();
    let failures = 0;

    function again(delay) {
      if (Date.now() - started > TASK_MAX_WAIT_MS) {
        stopWaiting(element, "No result yet.");
        return;
      }
      setTimeout(poll, delay);
    }

    function poll() {
      fetch("/api/tasks/" + encodeURIComponent(element.dataset.task), {
        headers: { Accept: "application/json" },
      })
        .then(function (response) {
          if (response.ok) return response.json();
          // 404: no such task, 401/403: logged out
          throw new Error("HTTP " + response.status);
        })
        .then(function (task) {
          failures = 0;
          if (task.finished) {
            window.location.reload();
          } else {
            again(TASK_POLL_MS);
          }
        })
        .catch(function () {
          failures += 1;
          if (failures >= TASK_MAX_FAILURES) {
            stopWaiting(element, "The state of the task is not available.");
          } else {
            again(TASK_POLL_MS * 3);
          }
        });
    }
    setTimeout(poll, TASK_POLL_MS);
  });

  // ----- containers: keep the state badges up to date -----
  const badges = document.querySelectorAll("[data-container-status]");
  if (badges.length) {
    setInterval(function () {
      if (document.hidden) return;
      fetch("/api/services/status", { headers: { Accept: "application/json" } })
        .then(function (response) {
          return response.ok ? response.json() : {};
        })
        .then(function (statuses) {
          badges.forEach(function (badge) {
            const status = statuses[badge.dataset.containerStatus];
            if (!status) return;
            badge.textContent = status;
            badge.className = "badge " + (STATUS_CLASSES[status] || "");
          });
          document.querySelectorAll("[data-container-state]").forEach(function (state) {
            const status = statuses[state.dataset.containerState];
            if (!status) return;
            state.textContent = status.charAt(0).toUpperCase() + status.slice(1);
            state.className = "container-state " + status;
          });
          document.querySelectorAll("[data-start-button]").forEach(function (button) {
            const status = statuses[button.dataset.startButton];
            if (status) button.disabled = status === "running";
          });
        })
        .catch(function () {});
    }, STATUS_POLL_MS);
  }
})();
