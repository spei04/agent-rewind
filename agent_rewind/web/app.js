"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  token: "",
  csrf: "",
  user: null,
  runs: [],
  run: null,
  step: 1,
  view: "runs",
  busy: false,
};
function element(tag, text, className) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (className) e.className = className;
  return e;
}
function notice(message) {
  $("notice").textContent = message;
  $("notice").classList.toggle("hidden", !message);
}
function guard(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (error) {
      notice(error.message);
    }
  };
}
async function api(path, body, method) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (state.csrf) headers["X-Rewind-CSRF"] = state.csrf;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(`/api${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
function badge(run) {
  return element(
    "span",
    run.status !== "complete" ? run.status : run.success ? "PASS" : "FAIL",
    `badge ${run.status === "complete" ? (run.success ? "pass" : "fail") : ""}`,
  );
}
function showView(view) {
  state.view = view;
  document
    .querySelectorAll(".view")
    .forEach((e) =>
      e.classList.toggle("hidden", e.id !== `${view}-view` || !state.user),
    );
  document
    .querySelectorAll("[data-view]")
    .forEach((e) => e.classList.toggle("active", e.dataset.view === view));
  $("page-label").textContent = {
    runs: "Runs",
    studies: "Intervention studies",
    jobs: "Execution jobs",
  }[view];
}
async function authenticate() {
  state.user = await api("/me");
  state.csrf = state.user.csrf;
  $("identity").textContent = `${state.user.subject} · ${state.user.role}`;
  $("connection").textContent = "Connected";
  $("logout").classList.remove("hidden");
  $("login-panel").classList.add("hidden");
  showView(state.view);
  await refresh();
}
async function refresh() {
  if (!state.user || state.busy) return;
  state.busy = true;
  try {
    const [runs, studies, jobs] = await Promise.all([
      api("/runs"),
      api("/studies"),
      api("/jobs"),
    ]);
    state.runs = runs;
    renderRuns();
    renderStudies(studies);
    renderJobs(jobs);
    if (state.run && state.run.status === "running")
      await selectRun(state.run.id, false);
  } finally {
    state.busy = false;
  }
}
function renderRuns() {
  $("run-count").textContent = String(state.runs.length);
  $("run-list").replaceChildren();
  if (!state.runs.length)
    $("run-list").append(
      element("div", "No runs recorded yet.", "empty-small"),
    );
  state.runs.forEach((run) => {
    const item = element(
      "button",
      undefined,
      `run-item ${state.run?.id === run.id ? "selected" : ""}`,
    );
    item.append(element("strong", run.name));
    const meta = element("div", undefined, "meta");
    meta.append(
      badge(run),
      element("span", `${run.steps} decisions`),
      element("span", run.parent_id ? "↳ branch" : "source"),
    );
    item.append(meta);
    item.onclick = guard(() => selectRun(run.id));
    $("run-list").append(item);
  });
}
async function selectRun(id, reset = true) {
  state.run = await api(`/runs/${id}`);
  if (reset) state.step = 1;
  state.step = Math.min(state.step, state.run.events.length || 1);
  $("run-empty").classList.add("hidden");
  $("run-detail").classList.remove("hidden");
  $("run-id").textContent = `RUN / ${id.slice(0, 12)}`;
  $("run-title").textContent = state.run.name;
  $("run-status").replaceWith(
    Object.assign(badge(state.run), { id: "run-status" }),
  );
  $("run-meta").replaceChildren(
    ...[
      `${state.run.steps} decisions`,
      `Seed ${state.run.seed}`,
      state.run.policy.model || state.run.policy.adapter,
      state.run.branchable
        ? "Checkpoint restore available"
        : "Restore unavailable",
    ].map((t) => element("span", t)),
  );
  $("ancestry").replaceChildren();
  if (state.run.parent_id) {
    const parent = element("button", state.run.parent_id.slice(0, 12));
    parent.onclick = guard(() => selectRun(state.run.parent_id));
    $("ancestry").append(
      "Branched at decision " + state.run.fork_step + " from ",
      parent,
    );
  }
  $("timeline").replaceChildren();
  state.run.events.forEach((event) => {
    const b = element(
      "button",
      String(event.step).padStart(2, "0"),
      `step ${event.actual_result.exit_code ? "failure" : ""} ${event.intervened ? "intervened" : ""}`,
    );
    b.title = `Decision ${event.step}: ${event.action.tool}`;
    b.setAttribute("aria-label", b.title);
    b.onclick = () => selectStep(event.step);
    $("timeline").append(b);
  });
  $("evaluation").textContent = JSON.stringify(
    state.run.evaluation || { status: state.run.status },
    null,
    2,
  );
  const operator = state.user.role !== "viewer";
  $("branch").disabled =
    !operator || !state.run.branchable || state.run.status !== "complete";
  $("investigate").disabled =
    !operator ||
    !state.run.branchable ||
    state.run.status !== "complete" ||
    state.run.success;
  $("compare").classList.toggle("hidden", !state.run.parent_id);
  renderRuns();
  selectStep(state.step);
  showView("runs");
}
function selectStep(step) {
  state.step = step;
  const event = state.run.events[step - 1];
  if (!event) return;
  [...$("timeline").children].forEach((button, i) =>
    button.classList.toggle("selected", i + 1 === step),
  );
  $("decision-title").textContent =
    `Decision ${String(step).padStart(2, "0")} · ${event.action.tool}`;
  $("checkpoint").textContent = event.checkpoint.slice(0, 12);
  $("action-output").textContent = JSON.stringify(event.action, null, 2);
  $("tool-output").textContent = JSON.stringify(event.observed_result, null, 2);
  $("changed-files").textContent = event.changes.length
    ? event.changes.map((c) => `${c.change}: ${c.path}`).join(" · ")
    : "Workspace unchanged";
  resetReplacement();
  $("file-list").replaceChildren();
  $("file-content").textContent =
    "Select a file to inspect the saved contents.";
  if (!$("files-tab").classList.contains("hidden")) guard(loadFiles)();
}
function resetReplacement() {
  const event = state.run?.events[state.step - 1];
  if (event)
    $("replacement").value = JSON.stringify(
      $("intervention-kind").value === "action"
        ? event.action
        : event.observed_result,
      null,
      2,
    );
}
async function loadFiles() {
  const runId = state.run.id,
    step = state.step;
  const files = await api(`/runs/${runId}/files/${step}`);
  if (runId !== state.run.id || step !== state.step) return;
  $("file-list").replaceChildren();
  files.forEach((file) => {
    const b = element("button", file.path);
    b.onclick = guard(async () => {
      const f = await api(
        `/runs/${runId}/files/${step}?path=${encodeURIComponent(file.path)}`,
      );
      if (runId === state.run.id && step === state.step)
        $("file-content").textContent =
          f.content + (f.truncated ? "\n[truncated]" : "");
    });
    $("file-list").append(b);
  });
}
async function queued(path, body) {
  const result = await api(path, body);
  notice(`Job ${result.job_id.slice(0, 12)} queued. A worker will execute it.`);
  await refresh();
}
function effectPlot(evidence) {
  const ns = "http://www.w3.org/2000/svg",
    svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 400 48");
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    evidence.effect === null
      ? "No completed pairs"
      : `Effect ${(evidence.effect * 100).toFixed(1)} percentage points; interval ${evidence.interval.map((x) => (100 * x).toFixed(1)).join(" to ")}`,
  );
  const line = (x1, y1, x2, y2, stroke, width) => {
    const el = document.createElementNS(ns, "line");
    Object.entries({ x1, y1, x2, y2, stroke, "stroke-width": width }).forEach(
      ([k, v]) => el.setAttribute(k, v),
    );
    svg.append(el);
  };
  line(10, 24, 390, 24, "#e4e9e3", 1);
  line(200, 8, 200, 40, "#a4b3a8", 1);
  if (evidence.effect !== null) {
    const x = (v) => 200 + 190 * v;
    line(
      x(evidence.interval[0]),
      24,
      x(evidence.interval[1]),
      24,
      "#669783",
      5,
    );
    const point = document.createElementNS(ns, "circle");
    point.setAttribute("cx", x(evidence.effect));
    point.setAttribute("cy", 24);
    point.setAttribute("r", 5);
    point.setAttribute("fill", "#22644e");
    svg.append(point);
  }
  return svg;
}
function evidenceRow(label, evidence) {
  const row = element("div", undefined, "effect-row");
  row.append(
    element("span", label),
    effectPlot(evidence),
    element(
      "span",
      evidence.effect === null
        ? "—"
        : `${evidence.effect >= 0 ? "+" : ""}${(100 * evidence.effect).toFixed(1)} pp`,
    ),
  );
  return row;
}
function renderStudies(studies) {
  $("studies-list").replaceChildren();
  if (!studies.length) {
    const empty = element("div", undefined, "panel empty");
    empty.append(
      element("h2", "No intervention studies yet."),
      element(
        "p",
        "Open a failed run and choose “Investigate failure” to start.",
      ),
    );
    $("studies-list").append(empty);
  }
  studies.forEach((study) => {
    const card = element("article", undefined, "panel study-card"),
      head = element("div", undefined, "detail-heading");
    head.append(
      element("h2", `Study ${study.id.slice(0, 8)}`),
      element("span", study.status, "badge"),
    );
    card.append(head);
    const source = element(
      "button",
      `Open source ${study.source_run.slice(0, 8)}`,
      "quiet",
    );
    source.onclick = guard(() => selectRun(study.source_run));
    card.append(source);
    card.append(
      element(
        "p",
        "Screening estimates are exploratory. Only fresh confirmation trials support the final claim.",
      ),
    );
    (study.candidates || []).forEach((c) => {
      if (c.evidence)
        card.append(
          evidenceRow(
            `D${c.intervention.step} · ${c.intervention.label}`,
            c.evidence,
          ),
        );
    });
    if (study.confirmation?.evidence) {
      const e = study.confirmation.evidence;
      card.append(
        element("h3", `Confirmation: ${e.verdict}`),
        evidenceRow("Fresh trial effect", e),
        element(
          "p",
          `${e.n} complete pairs · ${e.missing} missing · 95% conservative interval. ${study.seed_support ? "Provider seed requested; exact determinism is not guaranteed." : "Provider seeds unavailable; pairs use randomized execution order."}`,
        ),
      );
      const links = element("div", undefined, "pair-links");
      (study.confirmation.pairs || []).slice(0, 12).forEach((p, i) => {
        ["control", "treatment"].forEach((arm) => {
          if (p[`${arm}_run`]) {
            const b = element(
              "button",
              `${i + 1} ${arm} ${p[`${arm}_success`] ? "PASS" : "FAIL"}`,
            );
            b.onclick = guard(() => selectRun(p[`${arm}_run`]));
            links.append(b);
          }
        });
      });
      card.append(links);
    }
    card.append(element("p", study.claim_scope, "hint"));
    const download = element("button", "Download study JSON", "quiet");
    download.onclick = () => {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(study, null, 2)], {
          type: "application/json",
        }),
      );
      const a = element("a");
      a.href = url;
      a.download = `study-${study.id}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    card.append(download);
    $("studies-list").append(card);
  });
}
function renderJobs(jobs) {
  $("jobs-list").replaceChildren();
  if (!jobs.length)
    $("jobs-list").append(
      element("div", "No execution jobs yet.", "empty-small"),
    );
  jobs.forEach((job) => {
    const row = element("div", undefined, "job-row"),
      left = element("div");
    left.append(
      element("strong", `${job.kind} / ${job.id.slice(0, 12)}`),
      element(
        "small",
        `${job.status} · reserved $${(job.reserved / 1e6).toFixed(3)} of $${(job.budget / 1e6).toFixed(2)}`,
      ),
    );
    if (job.error) left.append(element("small", job.error));
    row.append(left);
    if (job.result?.run_id) {
      const b = element("button", "Open run →", "quiet");
      b.onclick = guard(() => selectRun(job.result.run_id));
      row.append(b);
    } else if (["queued", "running"].includes(job.status)) {
      const b = element("button", "Cancel", "quiet");
      b.disabled = state.user.role === "viewer";
      b.onclick = guard(async () => {
        await api(`/jobs/${job.id}/cancel`, {});
        await refresh();
      });
      row.append(b);
    }
    $("jobs-list").append(row);
  });
}
$("login-form").onsubmit = guard(async (e) => {
  e.preventDefault();
  state.token = $("api-key").value.trim();
  $("api-key").value = "";
  try {
    await authenticate();
    notice("");
  } catch (error) {
    state.token = "";
    throw error;
  }
});
$("logout").onclick = guard(async () => {
  if (!state.token)
    await fetch("/auth/logout", {
      method: "POST",
      headers: { "X-Rewind-CSRF": state.csrf },
    });
  location.reload();
});
$("refresh").onclick = guard(refresh);
document
  .querySelectorAll("[data-view]")
  .forEach((b) => (b.onclick = () => showView(b.dataset.view)));
for (const id of ["new-run", "empty-record"])
  $(id).onclick = () => {
    if (!state.user) {
      notice("Connect with a service API key or organization login first.");
      return;
    }
    $("task-dialog").showModal();
  };
document
  .querySelectorAll(".close-dialog")
  .forEach((b) => (b.onclick = () => b.closest("dialog").close()));
$("task-upload").onchange = guard(async () => {
  const file = $("task-upload").files[0];
  if (file) {
    if (file.size > 8 * 1024 * 1024) throw new Error("Manifest exceeds 8 MiB.");
    $("task-json").value = await file.text();
  }
});
$("task-form").onsubmit = guard(async (e) => {
  e.preventDefault();
  await queued("/runs", JSON.parse($("task-json").value));
  $("task-dialog").close();
});
$("intervention-kind").onchange = resetReplacement;
$("branch").onclick = guard(async () => {
  const kind = $("intervention-kind").value;
  const intervention = {
    step: state.step,
    kind,
    label: `Manual ${kind} at decision ${state.step}`,
  };
  intervention[kind === "action" ? "action" : "result"] = JSON.parse(
    $("replacement").value,
  );
  await queued("/branches", {
    parent_id: state.run.id,
    intervention,
    seed: Number($("branch-seed").value),
    budget_usd: Number($("branch-budget").value),
  });
});
$("investigate").onclick = () => $("study-dialog").showModal();
$("study-form").onsubmit = guard(async (e) => {
  e.preventDefault();
  await queued("/investigations", {
    run_id: state.run.id,
    screening_trials: Number($("screen-trials").value),
    confirmation_trials: Number($("confirm-trials").value),
    budget_usd: Number($("study-budget").value),
    seed: 42,
  });
  $("study-dialog").close();
  showView("studies");
});
document.querySelectorAll("[data-tab]").forEach(
  (b) =>
    (b.onclick = guard(async () => {
      document
        .querySelectorAll("[data-tab]")
        .forEach((t) => t.classList.toggle("selected", t === b));
      $("observation-tab").classList.toggle(
        "hidden",
        b.dataset.tab !== "observation",
      );
      $("files-tab").classList.toggle("hidden", b.dataset.tab !== "files");
      if (b.dataset.tab === "files") await loadFiles();
    })),
);
document.addEventListener("keydown", (e) => {
  if (
    !state.run ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) ||
    document.querySelector("dialog[open]")
  )
    return;
  if (e.key === "ArrowLeft") selectStep(Math.max(1, state.step - 1));
  if (e.key === "ArrowRight")
    selectStep(Math.min(state.run.events.length, state.step + 1));
});
authenticate().catch(() => {});
setInterval(() => {
  if (state.user && !document.hidden) guard(refresh)();
}, 4000);

$("compare").onclick = guard(async () => {
  const result = await api(
    `/compare?left=${state.run.parent_id}&right=${state.run.id}`,
  );
  $("compare-output").textContent = JSON.stringify(result, null, 2);
  $("compare-dialog").showModal();
});
