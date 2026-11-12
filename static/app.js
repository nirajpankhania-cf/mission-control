// Engineer report form. All user text is rendered as text nodes, never parsed as markup.
(function () {
  "use strict";

  // These messages mirror mission_control/validation.py exactly, so the
  // engineer sees the same words whether the check runs here or on the server.
  var TEXT_LIMITS = {
    name: { label: "Name", max: 100 },
    station: { label: "Station", max: 100 },
    note: { label: "Note", max: 4000 }
  };
  var READING_BOUNDS = {
    wind_knots: { label: "Wind", low: 0, high: 500, unit: "knots" },
    temp_c: { label: "Temperature", low: -150, high: 150, unit: "C" },
    fuel_pct: { label: "Fuel", low: 0, high: 150, unit: "percent" }
  };
  var FIELDS = ["name", "station", "wind_knots", "temp_c", "fuel_pct", "note"];

  function messageRequired(label) { return label + " is required"; }
  function messageTooLong(label, limit) { return label + " must be " + limit + " characters or fewer"; }
  function messageNotNumber(label) { return label + " must be a number"; }
  function messageOutOfRange(label, low, high, unit) {
    return label + " must be between " + low + " and " + high + " " + unit;
  }

  function validate(values) {
    var errors = {};
    Object.keys(TEXT_LIMITS).forEach(function (field) {
      var spec = TEXT_LIMITS[field];
      var value = (values[field] || "").trim();
      if (!value) { errors[field] = messageRequired(spec.label); }
      else if (value.length > spec.max) { errors[field] = messageTooLong(spec.label, spec.max); }
    });
    Object.keys(READING_BOUNDS).forEach(function (field) {
      var spec = READING_BOUNDS[field];
      var raw = (values[field] || "").trim();
      if (!raw) { errors[field] = messageRequired(spec.label); return; }
      var number = Number(raw);
      if (!isFinite(number)) { errors[field] = messageNotNumber(spec.label); return; }
      if (number < spec.low || number > spec.high) {
        errors[field] = messageOutOfRange(spec.label, spec.low, spec.high, spec.unit);
      }
    });
    return errors;
  }

  var form = document.getElementById("report-form");
  var submit = document.getElementById("submit");
  var statusLine = document.getElementById("status-line");
  var result = document.getElementById("result");

  function readValues() {
    var values = {};
    FIELDS.forEach(function (field) { values[field] = form.elements[field].value; });
    return values;
  }

  function showErrors(errors) {
    FIELDS.forEach(function (field) {
      var box = document.getElementById("error-" + field);
      var input = form.elements[field];
      box.textContent = errors[field] || "";
      input.setAttribute("aria-invalid", errors[field] ? "true" : "false");
    });
    if (errors.body) { statusLine.textContent = errors.body; }
  }

  function clearChildren(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function showResult(payload) {
    var report = payload.report;
    var verdict = document.getElementById("result-verdict");
    verdict.textContent = report.verdict === "go" ? "GO" : "NO GO";
    verdict.className = "badge " + report.verdict;
    var brief = document.getElementById("result-brief");
    brief.textContent = report.brief_by_minutes
      ? "Brief the Flight Director within " + report.brief_by_minutes + " minutes."
      : "";
    var list = document.getElementById("result-violations");
    clearChildren(list);
    (report.violations || []).forEach(function (violation) {
      var item = document.createElement("li");
      item.textContent = violation.reading + " = " + violation.value + " (limit " + violation.limit + ")";
      list.appendChild(item);
    });
    var review = document.getElementById("result-review");
    review.textContent = report.needs_review
      ? "Marked for review: " + (report.review_reasons || []).join(", ")
      : "";
    document.getElementById("result-link").setAttribute("href", "/console#report-" + report.id);
    result.hidden = false;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    result.hidden = true;
    statusLine.textContent = "";
    var values = readValues();
    var errors = validate(values);
    showErrors(errors);
    if (Object.keys(errors).length) { return; }

    submit.disabled = true;
    statusLine.textContent = "Filing report and running the pipeline...";
    fetch("/api/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values)
    }).then(function (response) {
      return response.json().then(function (payload) { return { status: response.status, payload: payload }; });
    }).then(function (outcome) {
      submit.disabled = false;
      if (outcome.status === 201) {
        statusLine.textContent = "Report #" + outcome.payload.report.id + " filed.";
        showResult(outcome.payload);
        form.elements.note.value = "";
      } else if (outcome.payload && outcome.payload.errors) {
        statusLine.textContent = "The report was not filed. Fix the fields marked below.";
        showErrors(outcome.payload.errors);
      } else {
        statusLine.textContent = "The server could not file the report (status " + outcome.status + ").";
      }
    }).catch(function (error) {
      submit.disabled = false;
      statusLine.textContent = "Could not reach the server: " + error.message;
    });
  });

  fetch("/api/status").then(function (response) { return response.json(); }).then(function (status) {
    document.getElementById("simulated-banner").hidden = !status.simulated;
  }).catch(function () { /* the banner is informational only */ });
})();
