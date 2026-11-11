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
      button.textContent = dark ? "Light theme" : "Dark theme";
      button.title = dark ? "Switch to the light theme" : "Switch to the dark theme";
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

  // ----- forms: confirm, no double submit -----
  each("form", function (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
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
        })
        .catch(function () {});
    }, STATUS_POLL_MS);
  }
})();
