/* CompiTek – kleine Helfer ohne externe Bibliotheken */
(function () {
  "use strict";

  /* ---------- Mobiles Menü ---------- */
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("hauptmenue");

  if (toggle && nav) {
    var setOpen = function (open) {
      toggle.setAttribute("aria-expanded", String(open));
      toggle.querySelector(".visually-hidden").textContent = open ? "Menü schließen" : "Menü öffnen";
      nav.classList.toggle("is-open", open);
    };

    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });

    nav.addEventListener("click", function (event) {
      if (event.target.closest("a")) setOpen(false);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("is-open")) {
        setOpen(false);
        toggle.focus();
      }
    });
  }

  /* ---------- Öffnungszeiten: „jetzt geöffnet?“ ----------
     Die Zeiten stehen nur an einer Stelle: in der Tabelle
     (Attribut data-hours an jeder Zeile, z. B. "09:00-12:00,15:00-18:00"). */
  var rows = document.querySelectorAll("[data-day]");
  var statusEls = document.querySelectorAll("[data-open-status]");

  if (rows.length) {
    var schedule = {};
    rows.forEach(function (row) {
      var day = Number(row.getAttribute("data-day"));
      var raw = (row.getAttribute("data-hours") || "").trim();
      schedule[day] = raw
        ? raw.split(",").map(function (slot) {
            var parts = slot.split("-");
            return { from: toMinutes(parts[0]), to: toMinutes(parts[1]) };
          })
        : [];
    });

    var now = berlinNow();

    rows.forEach(function (row) {
      if (Number(row.getAttribute("data-day")) === now.day) row.classList.add("is-today");
    });

    var text;
    var open = false;
    var current = (schedule[now.day] || []).filter(function (s) {
      return now.minutes >= s.from && now.minutes < s.to;
    })[0];

    if (current) {
      open = true;
      text = "Jetzt geöffnet – bis " + formatTime(current.to) + " Uhr";
    } else {
      var next = findNext(schedule, now);
      text = next ? "Geschlossen – öffnet " + next : "Termine nach Absprache";
    }

    statusEls.forEach(function (el) {
      el.textContent = text;
      el.classList.add(open ? "is-open" : "is-closed");
    });
  }

  function toMinutes(hhmm) {
    var p = hhmm.trim().split(":");
    return Number(p[0]) * 60 + Number(p[1] || 0);
  }

  function formatTime(minutes) {
    var h = Math.floor(minutes / 60);
    var m = minutes % 60;
    return h + ":" + (m < 10 ? "0" : "") + m;
  }

  function berlinNow() {
    var days = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
    try {
      var parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "Europe/Berlin",
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23"
      }).formatToParts(new Date());
      var get = function (type) {
        return parts.filter(function (p) { return p.type === type; })[0].value;
      };
      return { day: days[get("weekday")], minutes: Number(get("hour")) * 60 + Number(get("minute")) };
    } catch (e) {
      var d = new Date();
      return { day: d.getDay(), minutes: d.getHours() * 60 + d.getMinutes() };
    }
  }

  function findNext(schedule, now) {
    var names = ["So.", "Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa."];
    for (var offset = 0; offset < 8; offset++) {
      var day = (now.day + offset) % 7;
      var slots = schedule[day] || [];
      for (var i = 0; i < slots.length; i++) {
        if (offset > 0 || slots[i].from > now.minutes) {
          var when = offset === 0 ? "heute" : offset === 1 ? "morgen" : names[day];
          return when + " um " + formatTime(slots[i].from) + " Uhr";
        }
      }
    }
    return null;
  }

  /* ---------- Anruf-Leiste auf dem Handy ---------- */
  var callbar = document.querySelector(".callbar");
  var trigger = document.querySelector(".hero, .page-hero");

  if (callbar && trigger && "IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      callbar.classList.toggle("is-visible", !entries[0].isIntersecting);
    }).observe(trigger);
  } else if (callbar) {
    callbar.classList.add("is-visible");
  }

  /* ---------- Jahr im Footer ---------- */
  document.querySelectorAll("[data-year]").forEach(function (el) {
    el.textContent = new Date().getFullYear();
  });
})();
