// FinSight frontend. Plain JS. All server text is rendered with textContent / createElement,
// never innerHTML, so answers and source passages cannot inject markup.
"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  form: $("ask-form"), question: $("question"), submit: $("ask-submit"), count: $("ask-count"),
  filters: $("filters"), examples: $("examples"), result: $("result"),
  resultQuestion: $("result-question"), steps: $("steps"), notice: $("notice"),
  noticeLabel: $("notice-label"), noticeText: $("notice-text"), noticeHint: $("notice-hint"),
  answer: $("answer"), sources: $("sources"), sourcesList: $("sources-list"), runMeta: $("run-meta"),
  panel: $("panel"), scrim: $("scrim"), panelClose: $("panel-close"), panelRef: $("panel-ref"),
  panelCompany: $("panel-company"), panelYear: $("panel-year"), panelPage: $("panel-page"),
  panelText: $("panel-text"), themeToggle: $("theme-toggle"), themeLabel: $("theme-label"),
};

// Real graph nodes (from /api/ask/stream) that complete each visible step.
const STEPS = [
  { label: "Reading the question", doneBy: ["decompose"] },
  { label: "Searching the reports", doneBy: ["retrieve"] },
  { label: "Ranking passages", doneBy: ["retrieve"] },
  { label: "Writing the answer", doneBy: ["generate"] },
  { label: "Checking citations", doneBy: ["verify_citations"] },
];

let controller = null;      // AbortController of the request in flight
let lastTrigger = null;     // element that opened the source panel

/* ---------- small DOM helpers ---------- */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

/* ---------- theme ---------- */
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
function effectiveTheme() {
  return document.documentElement.dataset.theme || (darkQuery.matches ? "dark" : "light");
}
function syncThemeLabel() {
  const next = effectiveTheme() === "dark" ? "Light" : "Dark";
  els.themeLabel.textContent = next;
  els.themeToggle.setAttribute("aria-label", `Switch to ${next.toLowerCase()} theme`);
}
els.themeToggle.addEventListener("click", () => {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("finsight-theme", next); } catch (e) { /* private mode */ }
  syncThemeLabel();
});
darkQuery.addEventListener("change", syncThemeLabel);
syncThemeLabel();

/* ---------- company filters ---------- */
function selectedCompanies() {
  return [...els.filters.querySelectorAll(".filter[data-company]:not([data-company=''])")]
    .filter((b) => b.getAttribute("aria-pressed") === "true")
    .map((b) => b.dataset.company);
}
els.filters.addEventListener("click", (e) => {
  const btn = e.target.closest(".filter");
  if (!btn) return;
  const all = els.filters.querySelector(".filter[data-company='']");
  if (btn === all) {
    els.filters.querySelectorAll(".filter").forEach((b) => b.setAttribute("aria-pressed", String(b === all)));
    return;
  }
  btn.setAttribute("aria-pressed", String(btn.getAttribute("aria-pressed") !== "true"));
  all.setAttribute("aria-pressed", String(selectedCompanies().length === 0));
});

/* ---------- question input ---------- */
function autosize() {
  els.question.style.height = "auto";
  els.question.style.height = `${els.question.scrollHeight}px`;
  els.count.textContent = `${els.question.value.length}/500`;
}
els.question.addEventListener("input", autosize);
els.question.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    els.form.requestSubmit();
  }
});
document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName || "");
  if (e.key === "/" && !typing && els.panel.hidden) {
    e.preventDefault();
    els.question.focus();
  }
});
els.examples.addEventListener("click", (e) => {
  const btn = e.target.closest(".example");
  if (!btn) return;
  els.question.value = btn.textContent.trim();
  autosize();
  els.form.requestSubmit();
});

/* ---------- progress steps ---------- */
function renderSteps() {
  clear(els.steps);
  els.steps.classList.remove("steps--settled");
  STEPS.forEach((s, i) => {
    const li = el("li", "step");
    li.dataset.index = String(i);
    li.dataset.state = i === 0 ? "current" : "pending";
    const mark = el("span", "step__mark");
    mark.setAttribute("aria-hidden", "true");
    li.append(mark, el("span", "step__label", s.label));
    els.steps.append(li);
  });
}
function markNode(node) {
  const items = [...els.steps.children];
  STEPS.forEach((s, i) => {
    if (s.doneBy.includes(node)) items[i].dataset.state = "done";
  });
  if (node === "refuse") {
    STEPS.forEach((s, i) => { if (i >= 3) items[i].dataset.state = "skipped"; });
  }
  const next = items.find((li) => li.dataset.state === "pending" || li.dataset.state === "current");
  items.forEach((li) => { if (li.dataset.state === "current") li.dataset.state = "pending"; });
  if (next) next.dataset.state = "current";
  items.forEach((li) => {
    const mark = li.querySelector(".step__mark");
    mark.textContent = li.dataset.state === "done" ? "✓" : "";
  });
}
function settleSteps() {
  els.steps.querySelectorAll(".step[data-state='current'], .step[data-state='pending']")
    .forEach((li) => { li.dataset.state = "skipped"; });
  els.steps.classList.add("steps--settled");
}

/* ---------- notices (refusal, limits, errors) ---------- */
function showNotice(label, text, hint) {
  els.noticeLabel.textContent = label;
  els.noticeText.textContent = text;
  els.noticeHint.textContent = hint || "";
  els.notice.hidden = false;
}

/* ---------- display-only text tidying (what is sent to the API is unchanged) ---------- */
function displayQuestion(q) {
  const t = q.trim();
  const capped = t.charAt(0).toUpperCase() + t.slice(1);
  return /[?.!]$/.test(capped) ? capped : `${capped}?`;
}

const MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December";
const DATE_NO_COMMA = new RegExp(`\\b(${MONTHS}) (\\d{1,2}) (\\d{4})\\b`, "g");
function tidyAnswer(text) {
  return text
    .replace(/[    ]/g, " ")  // narrow/thin spaces the model emits read as no space
    .replace(/ {2,}/g, " ")
    .replace(DATE_NO_COMMA, "$1 $2, $3");      // "March 31 2026" -> "March 31, 2026"
}

/* figures a citation supports: numbers in the answer text just before its chip */
const FIGURE = /\d[\d,]*(?:\.\d+)?%?/g;
function figuresIn(text) {
  return (text.match(FIGURE) || [])
    .map((f) => f.replace(/,$/, ""))
    .filter((f) => !/^(19|20)\d{2}$/.test(f) && (f.length >= 2 || /[.%]/.test(f)));
}

/* Text nodes for a short excerpt around the first supported figure found in the chunk.
   Figures are compared digits-only, so "267,021" in the answer finds "2,67,021" in the source,
   and the source's own form is the one highlighted. */
const digitsOnly = (s) => s.replace(/,/g, "");
function excerptNodes(text, figures) {
  const flat = text
    .replace(/\|(\s*:?-{3,}:?\s*\|)+/g, "|")   // markdown table rules
    .replace(/\|(\s*\|)+/g, "|")               // runs of empty cells
    .replace(/\s+/g, " ").trim();
  const wanted = [...new Set(figures)].sort((a, b) => b.length - a.length).map(digitsOnly);
  const found = [...flat.matchAll(FIGURE)];
  for (const target of wanted) {
    const m = found.find((f) => digitsOnly(f[0].replace(/,$/, "")) === target);
    if (!m) continue;
    const fig = m[0].replace(/,$/, "");
    const start = Math.max(0, m.index - 60), end = Math.min(flat.length, m.index + fig.length + 120);
    return [
      document.createTextNode((start > 0 ? "… " : "") + flat.slice(start, m.index)),
      el("mark", null, fig),
      document.createTextNode(flat.slice(m.index + fig.length, end) + (end < flat.length ? " …" : "")),
    ];
  }
  return [document.createTextNode(flat.slice(0, 200) + (flat.length > 200 ? " …" : ""))];
}

/* ---------- answer rendering ---------- */
const CITE_PART = /^\s*(.+?)\s*,\s*(FY\s?\d{4})\s*,\s*p(?:age)?\.?\s*(\d+)\s*$/i;
const TOKEN = /\[([^\[\]]+)\]|\*\*([^*]+)\*\*/g;

function citeKey(company, fy, page) {
  return `${company.toLowerCase()}|${fy.replace(/\s/g, "").toUpperCase()}|${page}`;
}
function chipLabel(c) {
  return `${c.company} · FY${String(c.fiscal_year).slice(-2)} · p.${c.page}`;
}
function makeChip(citation) {
  const btn = el("button", "cite", chipLabel(citation));
  btn.type = "button";
  btn.setAttribute("aria-haspopup", "dialog");
  btn.setAttribute("aria-expanded", "false");
  btn.setAttribute("aria-label",
    `Source: ${citation.company}, ${citation.fiscal_year}, page ${citation.page}. Open passage.`);
  btn.addEventListener("click", () => openPanel(citation, btn));
  return btn;
}

function renderInline(container, text, byKey, figures) {
  let last = 0;
  let sinceChip = "";  // answer text since the previous citation: the claim the next chip supports
  for (const m of text.matchAll(TOKEN)) {
    if (m.index > last) {
      container.append(document.createTextNode(text.slice(last, m.index)));
      sinceChip += text.slice(last, m.index);
    }
    if (m[2] !== undefined) {
      container.append(el("strong", null, m[2]));
      sinceChip += m[2];
    } else {
      const chips = m[1].split(";").map((part) => {
        const pm = part.match(CITE_PART);
        return pm ? byKey.get(citeKey(pm[1], pm[2], pm[3])) : undefined;
      });
      if (chips.some(Boolean)) {
        chips.filter(Boolean).forEach((c) => {
          container.append(makeChip(c));
          const key = citeKey(c.company, c.fiscal_year, c.page);
          figures.set(key, [...(figures.get(key) || []), ...figuresIn(sinceChip)]);
        });
        sinceChip = "";
      } else {
        container.append(document.createTextNode(m[0]));  // a bracket that is not a citation
        sinceChip += m[0];
      }
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) container.append(document.createTextNode(text.slice(last)));
}

function renderAnswer(data) {
  const byKey = new Map(data.citations.map((c) => [citeKey(c.company, c.fiscal_year, c.page), c]));
  const figures = new Map();  // citation key -> figures the answer attributes to it
  clear(els.answer);
  tidyAnswer(data.answer).split(/\n{2,}/).map((p) => p.trim()).filter(Boolean).forEach((para) => {
    const p = el("p");
    renderInline(p, para.replace(/\s*\n\s*/g, " "), byKey, figures);
    els.answer.append(p);
  });
  els.answer.hidden = false;

  clear(els.sourcesList);
  data.citations.forEach((c) => {
    const li = el("li", "source");
    const excerpt = el("p", "source__excerpt");
    const key = citeKey(c.company, c.fiscal_year, c.page);
    excerpt.append(...excerptNodes(c.text || c.snippet || "", figures.get(key) || []));
    li.append(makeChip(c), excerpt);
    els.sourcesList.append(li);
  });
  els.sources.hidden = data.citations.length === 0;
}

function renderRunMeta(data) {
  const parts = [`${(data.latency_ms / 1000).toFixed(1)} s`, data.question_type,
    `${data.citations.length} ${data.citations.length === 1 ? "citation" : "citations"}`];
  if (data.trace_id) parts.push(`trace ${data.trace_id.slice(0, 8)}`);
  els.runMeta.textContent = parts.join(" · ");
  els.runMeta.title = data.trace_id ? `Langfuse trace ${data.trace_id}` : "";
}

/* ---------- source panel ---------- */
function focusables() {
  return [...els.panel.querySelectorAll("button, [href], [tabindex]:not([tabindex='-1'])")];
}
function openPanel(citation, trigger) {
  lastTrigger = trigger;
  els.panelRef.textContent = chipLabel(citation);
  els.panelCompany.textContent = citation.company;
  els.panelYear.textContent = citation.fiscal_year;
  els.panelPage.textContent = `p.${citation.page}`;
  els.panelText.textContent = citation.text || citation.snippet || "";
  els.panelText.scrollTop = 0;
  els.scrim.hidden = false;
  els.panel.hidden = false;
  trigger.setAttribute("aria-expanded", "true");
  els.panelClose.focus();
}
function closePanel() {
  if (els.panel.hidden) return;
  els.panel.hidden = true;
  els.scrim.hidden = true;
  if (lastTrigger) {
    lastTrigger.setAttribute("aria-expanded", "false");
    lastTrigger.focus();
  }
}
els.panelClose.addEventListener("click", closePanel);
els.scrim.addEventListener("click", closePanel);
document.addEventListener("keydown", (e) => {
  if (els.panel.hidden) return;
  if (e.key === "Escape") { e.preventDefault(); closePanel(); return; }
  if (e.key === "Tab") {  // keep focus inside the open panel
    const f = focusables();
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
});

/* ---------- asking ---------- */
async function errorFromResponse(res) {
  let detail = "";
  try {
    const body = await res.json();
    detail = typeof body.detail === "string" ? body.detail : "";
  } catch (e) { /* not JSON */ }
  if (res.status === 429) {
    return ["Question limit reached",
      detail || "You have reached the hourly question limit.",
      "The limit keeps this free demo available for everyone. Your earlier answers are still above."];
  }
  if (res.status === 422) {
    return ["Check the question", "Questions need between 1 and 500 characters.", ""];
  }
  return ["Briefly unavailable",
    detail || "The research desk could not be reached just now.",
    "Nothing is wrong with your question. Please try again in a minute."];
}

function finish() {
  els.submit.disabled = false;
  els.result.setAttribute("aria-busy", "false");
  controller = null;
}

async function ask(question) {
  if (controller) controller.abort();
  controller = new AbortController();
  closePanel();

  els.examples.hidden = true;
  els.result.hidden = false;
  els.result.setAttribute("aria-busy", "true");
  els.resultQuestion.textContent = displayQuestion(question);
  els.notice.hidden = true;
  els.answer.hidden = true;
  els.sources.hidden = true;
  renderSteps();
  els.submit.disabled = true;

  const companies = selectedCompanies();
  let res;
  try {
    res = await fetch("/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(companies.length ? { question, companies } : { question }),
      signal: controller.signal,
    });
  } catch (e) {
    if (e.name === "AbortError") return;
    settleSteps();
    showNotice("Connection lost", "The request did not reach the server.", "Check your connection and try again.");
    finish();
    return;
  }
  if (!res.ok) {
    settleSteps();
    showNotice(...(await errorFromResponse(res)));
    finish();
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) handleEvent(JSON.parse(line));
      }
    }
  } catch (e) {
    if (e.name === "AbortError") return;
    settleSteps();
    showNotice("Briefly unavailable", "The answer stream was interrupted.", "Please try again.");
  }
  finish();
}

function handleEvent(ev) {
  if (ev.type === "step") {
    markNode(ev.step);
  } else if (ev.type === "answer") {
    settleSteps();
    renderRunMeta(ev);
    if (ev.refused) {
      showNotice("Not in the reports", tidyAnswer(ev.answer),
        "Try the wording the reports use (for example “revenue from operations” or “turnover rate”), or limit the search to one company above.");
    } else {
      renderAnswer(ev);
    }
  } else if (ev.type === "error") {
    settleSteps();
    showNotice("Briefly unavailable", ev.message || "Something went wrong.", "Please try again in a minute.");
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const question = els.question.value.trim();
  if (!question) { els.question.focus(); return; }
  els.question.value = "";  // the question now heads the answer; the field is free for the next one
  autosize();
  ask(question);
});

autosize();
