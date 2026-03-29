const state = {
  runId: null,
  pipeline: null,
  runs: [],
  nodes: {},
  events: [],
  selectedNodeId: null,
  selectedArtifact: "output.txt",
  artifactCache: new Map(),
  eventSource: null,
  validationPipeline: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function setBanner(message, kind = "success") {
  const banner = document.getElementById("banner");
  if (!message) {
    banner.className = "banner hidden";
    banner.textContent = "";
    return;
  }
  banner.className = `banner ${kind}`;
  banner.textContent = message;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function formatDuration(run) {
  if (!run?.started_at || !run?.finished_at) return "-";
  return `${Math.max(0, Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000))}s`;
}

function currentRun() {
  return state.runs.find((run) => run.id === state.runId) || null;
}

function topoLevels(nodes) {
  const levels = {};
  const map = Object.fromEntries(nodes.map((node) => [node.id, node]));
  function depth(id) {
    if (levels[id] !== undefined) return levels[id];
    const deps = map[id]?.depends_on || [];
    levels[id] = deps.length ? 1 + Math.max(...deps.map(depth)) : 0;
    return levels[id];
  }
  nodes.forEach((node) => depth(node.id));
  return levels;
}

function updateTopMetrics() {
  document.getElementById("metric-total").textContent = state.runs.length;
  document.getElementById("metric-queued").textContent = state.runs.filter((run) => run.status === "queued").length;
  document.getElementById("metric-running").textContent = state.runs.filter((run) => ["running", "cancelling"].includes(run.status)).length;
}

function filteredRuns() {
  const query = document.getElementById("run-search").value.trim().toLowerCase();
  if (!query) return state.runs;
  return state.runs.filter((run) =>
    run.id.toLowerCase().includes(query) ||
    run.pipeline.name.toLowerCase().includes(query) ||
    run.status.toLowerCase().includes(query)
  );
}

function renderRuns() {
  const container = document.getElementById("runs");
  const runs = filteredRuns();
  if (!runs.length) {
    container.innerHTML = '<div class="small">No runs yet.</div>';
    return;
  }
  container.innerHTML = runs.map((run) => `
    <div class="run-item ${run.id === state.runId ? "active" : ""}">
      <h3>${escapeHtml(run.pipeline.name)}</h3>
      <div class="small mono">${run.id}</div>
      <div class="small">Status: ${escapeHtml(run.status)} · Started: ${escapeHtml(formatDate(run.started_at || run.created_at))}</div>
      <div class="small">Duration: ${escapeHtml(formatDuration(run))}</div>
      <div class="button-row" style="margin-top:0.65rem">
        <button data-open-run="${run.id}">Open</button>
      </div>
    </div>
  `).join("");

  container.querySelectorAll("button[data-open-run]").forEach((button) => {
    button.onclick = async () => {
      await openRun(button.dataset.openRun);
    };
  });
}

function renderGraph() {
  const container = document.getElementById("graph");
  container.innerHTML = "";
  const pipeline = state.pipeline || state.validationPipeline;
  if (!pipeline?.nodes?.length) {
    container.innerHTML = '<p class="small">Validate or run a pipeline to render the DAG.</p>';
    return;
  }

  const nodes = pipeline.nodes;
  const levels = topoLevels(nodes);
  const levelGroups = {};
  nodes.forEach((node) => {
    const level = levels[node.id] || 0;
    levelGroups[level] ||= [];
    levelGroups[level].push(node);
  });

  const width = Math.max(860, (Object.keys(levelGroups).length + 1) * 240);
  const height = Math.max(420, nodes.length * 140);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "graph-lines");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  container.appendChild(svg);

  const positions = {};
  Object.entries(levelGroups).forEach(([level, group]) => {
    group.forEach((node, index) => {
      positions[node.id] = { x: Number(level) * 240 + 30, y: index * 140 + 30 };
    });
  });

  nodes.forEach((node) => {
    for (const dependency of node.depends_on || []) {
      const from = positions[dependency];
      const to = positions[node.id];
      if (!from || !to) continue;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", `M ${from.x + 190} ${from.y + 42} C ${from.x + 220} ${from.y + 42}, ${to.x - 30} ${to.y + 42}, ${to.x} ${to.y + 42}`);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", "#334155");
      path.setAttribute("stroke-width", "2");
      svg.appendChild(path);
    }
  });

  nodes.forEach((node) => {
    const position = positions[node.id];
    const result = state.nodes[node.id] || { status: "pending", current_attempt: 0, attempts: [] };
    const div = document.createElement("div");
    div.className = `graph-node ${result.status || "pending"} ${state.selectedNodeId === node.id ? "selected" : ""}`;
    div.style.left = `${position.x}px`;
    div.style.top = `${position.y}px`;
    div.innerHTML = `
      <h3>${escapeHtml(node.id)}</h3>
      <p>${escapeHtml(node.agent)} · ${escapeHtml(result.status || "pending")}</p>
      <p>${escapeHtml(node.model || "default model")}</p>
      <p>Attempt ${escapeHtml(String(result.current_attempt || 0))}/${escapeHtml(String((node.retries || 0) + 1))}</p>
    `;
    div.onclick = () => {
      state.selectedNodeId = node.id;
      renderGraph();
      renderDetail();
    };
    container.appendChild(div);
  });
}

function renderRunMeta() {
  const run = currentRun();
  document.getElementById("run-status").textContent = run?.status || "idle";
  document.getElementById("run-meta").textContent = run
    ? `${run.pipeline.name} · created ${formatDate(run.created_at)} · duration ${formatDuration(run)}`
    : state.validationPipeline
      ? `Validated DAG: ${state.validationPipeline.name}`
      : "No run selected";
}

function upsertAttempt(nodeState, attemptNumber, patch) {
  if (!attemptNumber) return;
  nodeState.attempts ||= [];
  let attempt = nodeState.attempts.find((item) => item.number === attemptNumber);
  if (!attempt) {
    attempt = { number: attemptNumber };
    nodeState.attempts.push(attempt);
    nodeState.attempts.sort((left, right) => left.number - right.number);
  }
  Object.assign(attempt, patch);
}

async function fetchArtifact(nodeId, name) {
  if (!state.runId || !nodeId) return "";
  const cacheKey = `${state.runId}:${nodeId}:${name}`;
  if (state.artifactCache.has(cacheKey)) return state.artifactCache.get(cacheKey);
  const content = await api(`/api/runs/${state.runId}/artifacts/${nodeId}/${name}`);
  state.artifactCache.set(cacheKey, content);
  return content;
}

async function renderDetail() {
  const detail = document.getElementById("detail");
  const selected = state.selectedNodeId && state.nodes[state.selectedNodeId];
  document.getElementById("selected-node").textContent = state.selectedNodeId || "None selected";
  if (!selected || !state.selectedNodeId) {
    detail.innerHTML = '<p class="small">Select a node to inspect its output, attempts, artifacts, and parsed timeline.</p>';
    return;
  }

  let artifactText = "";
  try {
    artifactText = await fetchArtifact(state.selectedNodeId, state.selectedArtifact);
  } catch {
    artifactText = selected.output || "";
  }

  const attemptRows = (selected.attempts || []).map((attempt) => `
    <div class="summary-card">
      <div><strong>Attempt ${attempt.number}</strong></div>
      <div class="small">Status: ${escapeHtml(attempt.status)} · Exit: ${escapeHtml(String(attempt.exit_code ?? "-"))}</div>
      <div class="small">Started: ${escapeHtml(formatDate(attempt.started_at))}</div>
      <div class="small">Finished: ${escapeHtml(formatDate(attempt.finished_at))}</div>
    </div>
  `).join("");

  const events = state.events.filter((event) => event.node_id === state.selectedNodeId).slice(-25).reverse();
  detail.innerHTML = `
    <div class="summary-grid">
      <div class="summary-card"><div class="small">Status</div><strong>${escapeHtml(selected.status || "pending")}</strong></div>
      <div class="summary-card"><div class="small">Current attempt</div><strong>${escapeHtml(String(selected.current_attempt || 0))}</strong></div>
      <div class="summary-card"><div class="small">Exit code</div><strong>${escapeHtml(String(selected.exit_code ?? "-"))}</strong></div>
      <div class="summary-card"><div class="small">Success</div><strong>${escapeHtml(String(selected.success ?? "-"))}</strong></div>
    </div>
    <div class="trace-item">
      <h4>Attempts</h4>
      <div class="summary-grid">${attemptRows || '<div class="small">No attempts yet.</div>'}</div>
    </div>
    <div class="trace-item">
      <h4>Artifact: ${escapeHtml(state.selectedArtifact)}</h4>
      <div class="output-box">${escapeHtml(artifactText)}</div>
    </div>
    <div class="trace-item">
      <h4>Success checks</h4>
      <div class="output-box">${escapeHtml((selected.success_details || []).join("\n"))}</div>
    </div>
    <div class="trace-item">
      <h4>Recent events</h4>
      ${events.map((event) => `
        <div class="summary-card">
          <div><strong>${escapeHtml(event.type)}</strong></div>
          <div class="small">${escapeHtml(formatDate(event.timestamp))}</div>
          <div class="output-box">${escapeHtml(JSON.stringify(event.data || {}, null, 2))}</div>
        </div>
      `).join("") || '<div class="small">No node-specific events yet.</div>'}
    </div>
  `;
}

function applyEvent(event) {
  state.events.push(event);
  if (event.type === "run_queued") {
    const run = currentRun();
    if (run) run.status = "queued";
  }
  if (event.type === "run_started") {
    const run = currentRun();
    if (run) run.status = "running";
  }
  if (event.type === "run_cancelling") {
    const run = currentRun();
    if (run) run.status = "cancelling";
  }
  if (event.node_id && !state.nodes[event.node_id]) {
    state.nodes[event.node_id] = { node_id: event.node_id, trace_events: [], attempts: [], status: "pending", current_attempt: 0 };
  }
  if (event.type === "node_started" && event.node_id) {
    state.nodes[event.node_id].status = "running";
  }
  if (event.type === "node_retrying" && event.node_id) {
    state.nodes[event.node_id].status = "retrying";
    state.nodes[event.node_id].current_attempt = event.data.attempt || state.nodes[event.node_id].current_attempt;
    upsertAttempt(state.nodes[event.node_id], event.data.attempt, { status: "retrying" });
  }
  if (event.type === "node_trace" && event.node_id) {
    state.nodes[event.node_id].trace_events ||= [];
    state.nodes[event.node_id].trace_events.push(event.data.trace);
    const attempt = event.data.trace?.attempt;
    if (attempt) state.nodes[event.node_id].current_attempt = attempt;
  }
  if (["node_completed", "node_failed", "node_cancelled"].includes(event.type) && event.node_id) {
    const status = event.type === "node_completed" ? "completed" : event.type === "node_failed" ? "failed" : "cancelled";
    Object.assign(state.nodes[event.node_id], {
      status,
      exit_code: event.data.exit_code,
      success: event.data.success,
      output: event.data.output,
      final_response: event.data.final_response,
      success_details: event.data.success_details,
      current_attempt: event.data.attempt || state.nodes[event.node_id].current_attempt,
    });
    upsertAttempt(state.nodes[event.node_id], event.data.attempt, {
      status,
      exit_code: event.data.exit_code,
      output: event.data.output,
      success: event.data.success,
    });
  }
  if (event.type === "node_skipped" && event.node_id) {
    state.nodes[event.node_id].status = "skipped";
  }
  if (event.type === "run_completed") {
    const run = currentRun();
    if (run) run.status = event.data.status;
  }
  renderRunMeta();
  renderRuns();
  renderGraph();
  renderDetail();
}

function connectStream(runId) {
  if (state.eventSource) state.eventSource.close();
  state.eventSource = new EventSource(`/api/runs/${runId}/stream`);
  state.eventSource.onmessage = (message) => applyEvent(JSON.parse(message.data));
  state.eventSource.onerror = () => {
    if (state.eventSource) state.eventSource.close();
  };
}

async function refreshRuns() {
  state.runs = await api("/api/runs");
  updateTopMetrics();
  renderRuns();
  renderRunMeta();
}

async function openRun(runId) {
  const run = await api(`/api/runs/${runId}`);
  state.runId = run.id;
  state.pipeline = run.pipeline;
  state.nodes = run.nodes;
  state.selectedNodeId = state.selectedNodeId || state.pipeline.nodes?.[0]?.id || null;
  state.events = await api(`/api/runs/${runId}/events`);
  state.artifactCache.clear();
  renderRunMeta();
  renderRuns();
  renderGraph();
  await renderDetail();
  connectStream(run.id);
}

function pipelinePayload() {
  const pipelineText = document.getElementById("pipeline-input").value;
  const baseDir = document.getElementById("pipeline-base-dir").value.trim();
  return baseDir ? { pipeline_text: pipelineText, base_dir: baseDir } : { pipeline_text: pipelineText };
}

async function validatePipeline() {
  const response = await api("/api/runs/validate", { method: "POST", body: JSON.stringify(pipelinePayload()) });
  state.validationPipeline = response.pipeline;
  state.pipeline = null;
  state.nodes = {};
  state.runId = null;
  state.events = [];
  state.selectedNodeId = response.pipeline.nodes?.[0]?.id || null;
  renderRunMeta();
  renderGraph();
  await renderDetail();
  setBanner(`Pipeline validated: ${response.pipeline.name}`, "success");
}

async function runPipeline() {
  const run = await api("/api/runs", { method: "POST", body: JSON.stringify(pipelinePayload()) });
  state.validationPipeline = null;
  await refreshRuns();
  await openRun(run.id);
  setBanner(`Run queued: ${run.id}`, "success");
}

async function cancelRun() {
  if (!state.runId) return;
  await api(`/api/runs/${state.runId}/cancel`, { method: "POST" });
  setBanner(`Cancellation requested for ${state.runId}`, "success");
  await openRun(state.runId);
}

async function rerunRun() {
  if (!state.runId) return;
  const rerun = await api(`/api/runs/${state.runId}/rerun`, { method: "POST" });
  await refreshRuns();
  await openRun(rerun.id);
  setBanner(`Rerun queued: ${rerun.id}`, "success");
}

for (const button of document.querySelectorAll(".artifact-button")) {
  button.onclick = async () => {
    state.selectedArtifact = button.dataset.artifact;
    await renderDetail();
  };
}

document.getElementById("load-example").onclick = async () => {
  const data = await api("/api/examples/default");
  document.getElementById("pipeline-input").value = data.example;
  document.getElementById("pipeline-base-dir").value = data.base_dir || "";
  setBanner(null);
};

document.getElementById("validate-pipeline").onclick = () => validatePipeline().catch((error) => setBanner(error.message, "error"));
document.getElementById("run-pipeline").onclick = () => runPipeline().catch((error) => setBanner(error.message, "error"));
document.getElementById("cancel-run").onclick = () => cancelRun().catch((error) => setBanner(error.message, "error"));
document.getElementById("rerun-run").onclick = () => rerunRun().catch((error) => setBanner(error.message, "error"));
document.getElementById("refresh-runs").onclick = () => refreshRuns().catch((error) => setBanner(error.message, "error"));
document.getElementById("run-search").oninput = renderRuns;

refreshRuns()
  .then(async () => {
    if (state.runs[0]) await openRun(state.runs[0].id);
  })
  .catch((error) => setBanner(error.message, "error"));
