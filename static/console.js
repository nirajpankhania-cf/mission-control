// Flight Director console. Every value from the server is placed with textContent
// or as an attribute; nothing from a report is parsed as markup.
(function () {
  "use strict";

  var queue = document.getElementById("queue");
  var queueEmpty = document.getElementById("queue-empty");
  var detail = document.getElementById("detail");
  var selectedId = null;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }

  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function money(value) {
    var number = Number(value || 0);
    return "$" + number.toFixed(6);
  }

  function verdictLabel(verdict) {
    if (verdict === "go") { return "GO"; }
    if (verdict === "no_go") { return "NO GO"; }
    return "PENDING";
  }

  function badge(text, className) { return el("span", "badge " + className, text); }

  // ----- queue ---------------------------------------------------------
  function renderQueue(reports) {
    clear(queue);
    queueEmpty.hidden = reports.length > 0;
    reports.forEach(function (report) {
      var item = el("li");
      item.setAttribute("data-id", report.id);
      if (report.id === selectedId) { item.classList.add("selected"); }
      var row = el("div", "row");
      row.appendChild(el("strong", null, "#" + report.id + " " + report.station));
      row.appendChild(badge(verdictLabel(report.verdict), report.verdict || "muted"));
      item.appendChild(row);
      var meta = el("div", "meta");
      var parts = [report.name];
      if (report.subsystem) { parts.push(report.subsystem); }
      if (report.effective_severity) { parts.push("severity " + report.effective_severity); }
      if (report.brief_by_minutes) { parts.push("brief by " + report.brief_by_minutes + " min"); }
      parts.push("briefing " + (report.briefing_status || "none"));
      parts.push(money(report.cost_usd));
      meta.textContent = parts.join(" · ");
      item.appendChild(meta);
      if (report.needs_review) {
        var reasons = el("div", "reasons");
        reasons.appendChild(badge("NEEDS REVIEW", "review"));
        reasons.appendChild(document.createTextNode(" " + (report.review_reasons || []).join(", ")));
        item.appendChild(reasons);
      }
      item.addEventListener("click", function () { openReport(report.id); });
      queue.appendChild(item);
    });
  }

  function loadQueue() {
    return fetch("/api/reports").then(function (r) { return r.json(); }).then(function (payload) {
      renderQueue(payload.reports || []);
    }).catch(function () { queueEmpty.textContent = "Could not load the queue."; queueEmpty.hidden = false; });
  }

  // ----- detail --------------------------------------------------------
  function fact(list, key, value) {
    list.appendChild(el("dt", null, key));
    list.appendChild(el("dd", null, value));
  }

  function renderDetail(payload) {
    var report = payload.report;
    var briefing = payload.briefing;
    detail.hidden = false;
    document.getElementById("detail-title").textContent =
      "Report #" + report.id + " from " + report.name + " at " + report.station;

    var verdict = document.getElementById("detail-verdict");
    verdict.textContent = verdictLabel(report.verdict);
    verdict.className = "badge " + (report.verdict || "muted");
    document.getElementById("detail-severity").textContent =
      "severity " + (report.effective_severity || "?") + " · brief by " + (report.brief_by_minutes || "?") + " min";
    var review = document.getElementById("detail-review");
    review.hidden = !report.needs_review;
    review.textContent = "NEEDS REVIEW: " + (report.review_reasons || []).join(", ");
    var status = document.getElementById("detail-briefing-status");
    status.textContent = briefing ? "briefing " + briefing.status : "no briefing";
    status.className = "badge " + (briefing ? briefing.status : "muted");

    var facts = document.getElementById("detail-facts");
    clear(facts);
    fact(facts, "Filed", report.created_at);
    fact(facts, "Readings", "wind " + report.wind_knots + " kn · temp " + report.temp_c + " C · fuel " + report.fuel_pct + " %");
    fact(facts, "Subsystem", report.subsystem || "?");
    fact(facts, "Sorted severity", report.severity || "?");
    fact(facts, "Pipeline status", report.status);
    fact(facts, "Report cost", money(payload.cost_usd));

    document.getElementById("briefing-text").textContent = briefing ? briefing.text : "No briefing was produced.";
    var approveForm = document.getElementById("approve-form");
    var approvedLine = document.getElementById("approved-line");
    if (briefing && briefing.status === "pending") {
      approveForm.hidden = false;
      approvedLine.hidden = true;
      approveForm.setAttribute("data-briefing-id", briefing.id);
    } else {
      approveForm.hidden = true;
      approvedLine.hidden = !briefing;
      if (briefing) {
        approvedLine.textContent = "Approved by " + briefing.approved_by + " at " + briefing.approved_at + ".";
      }
    }
    document.getElementById("error-approver").textContent = "";

    var violations = document.getElementById("violations");
    clear(violations);
    if (!report.violations || !report.violations.length) {
      violations.appendChild(el("li", "clear", "None: all three readings are within the launch limits."));
    }
    (report.violations || []).forEach(function (v) {
      violations.appendChild(el("li", "flagged", v.reading + " = " + v.value + " (limit " + v.limit + ")"));
    });

    var checks = document.getElementById("checks");
    clear(checks);
    var labels = { hidden: "Hidden instructions", missing: "Missing details", panic: "Panic in tone" };
    ["hidden", "missing", "panic"].forEach(function (kind) {
      var check = (report.checks || {})[kind];
      var item = el("li");
      item.appendChild(el("strong", null, labels[kind] + ": "));
      if (!check) {
        item.appendChild(el("span", "muted", "not run"));
      } else {
        item.appendChild(el("span", check.flagged ? "flagged" : "clear", check.flagged ? "FLAGGED" : "clear"));
        item.appendChild(document.createTextNode(" " + (check.reason || "") + (check.status === "error" ? " (check errored, counted as flagged)" : "")));
      }
      checks.appendChild(item);
    });

    document.getElementById("note-text").textContent = report.note;

    var trace = document.getElementById("trace");
    clear(trace);
    document.getElementById("cost-total").textContent = "· total " + money(payload.cost_usd) + " over " + payload.trace.length + " steps";
    payload.trace.forEach(function (step) {
      var card = el("div", "card " + step.kind + (step.status === "error" ? " error" : ""));
      card.appendChild(el("div", "name", step.seq + ". " + step.name));
      card.appendChild(el("div", "tokens", (step.kind === "code" ? "code" : step.model) + " · " + step.status));
      card.appendChild(el("div", "tokens", "in " + step.input_tokens + " · out " + step.output_tokens + " tokens"));
      card.appendChild(el("div", "tokens", money(step.cost_usd) + " · " + step.duration_ms + " ms"));
      var summary = summarizeDetail(step);
      if (summary) { card.appendChild(el("div", "detail", summary)); }
      trace.appendChild(card);
    });
  }

  function summarizeDetail(step) {
    var d = step.detail || {};
    if (d.error) { return d.error; }
    if (step.name === "limits") { return "verdict " + d.verdict + ", " + (d.violations || []).length + " violation(s)"; }
    if (step.name === "sort") { return d.subsystem + " / " + d.severity + (d.reason ? ": " + d.reason : ""); }
    if (step.name === "brief_by") { return "effective " + d.effective_severity + ", brief by " + d.brief_by_minutes + " min"; }
    if (step.name.indexOf("check_") === 0) { return (d.flagged ? "flagged" : "clear") + (d.reason ? ": " + d.reason : ""); }
    if (step.name.indexOf("draft_") === 0) { return (d.feedback_in ? "feedback in: " + d.feedback_in + "\n" : "") + (d.summary || ""); }
    if (step.name.indexOf("review_") === 0) { return (d.approved ? "pass" : "not passed") + (d.feedback ? ": " + d.feedback : ""); }
    if (step.name === "assemble_briefing") { return d.rounds + " round(s), briefing " + d.briefing_status; }
    return "";
  }

  function openReport(id) {
    selectedId = id;
    window.location.hash = "report-" + id;
    Array.prototype.forEach.call(queue.children, function (item) {
      item.classList.toggle("selected", Number(item.getAttribute("data-id")) === id);
    });
    return fetch("/api/reports/" + id).then(function (r) { return r.json(); }).then(renderDetail);
  }

  document.getElementById("approve").addEventListener("click", function () {
    var form = document.getElementById("approve-form");
    var briefingId = form.getAttribute("data-briefing-id");
    var approver = document.getElementById("approver").value.trim();
    var error = document.getElementById("error-approver");
    if (!approver) { error.textContent = "Approver name is required"; return; }
    fetch("/api/briefings/" + briefingId + "/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approver: approver })
    }).then(function (r) { return r.json().then(function (p) { return { status: r.status, payload: p }; }); })
      .then(function (outcome) {
        if (outcome.status === 200) {
          error.textContent = "";
          openReport(selectedId);
          loadQueue();
        } else if (outcome.payload.errors) {
          error.textContent = outcome.payload.errors.approver || "Could not approve.";
        } else {
          error.textContent = outcome.payload.error || ("Could not approve (status " + outcome.status + ")");
        }
      }).catch(function (e) { error.textContent = "Could not reach the server: " + e.message; });
  });

  document.getElementById("refresh").addEventListener("click", function () { loadQueue(); });

  fetch("/api/status").then(function (r) { return r.json(); }).then(function (status) {
    document.getElementById("simulated-banner").hidden = !status.simulated;
    document.getElementById("model-line").textContent =
      (status.simulated ? "Simulated models" : "Live models") + ": fast " + status.fast_model +
      " for sorting and checks, strong " + status.strong_model + " for draft and review" +
      (status.prices_checked_on ? " · prices checked " + status.prices_checked_on : "");
  }).catch(function () { /* informational only */ });

  loadQueue().then(function () {
    var match = /^#report-(\d+)$/.exec(window.location.hash);
    if (match) { openReport(Number(match[1])); }
  });
  setInterval(loadQueue, 10000);
})();
