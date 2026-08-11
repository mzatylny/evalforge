const byId = (id) => document.getElementById(id);
const formatPercent = (value) => `${(value * 100).toFixed(1)}%`;
const formatDelta = (value) => `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)} pp`;
const headers = () => ({ "X-EvalForge-Key": byId("apiKey").value });

function setBar(id, value) {
  byId(id).style.width = `${Math.max(2, Math.min(100, value * 100))}%`;
}

function render(data) {
  if (!data.experiment || !data.decision) return;
  const experiment = data.experiment;
  const baseline = experiment.baseline;
  const candidate = experiment.candidate;
  const decision = data.decision;

  byId("successRate").textContent = formatPercent(candidate.success_rate);
  byId("successDelta").textContent = `${formatDelta(experiment.success_delta)} vs baseline`;
  byId("qualityScore").textContent = candidate.mean_score.toFixed(3);
  byId("scoreDelta").textContent = `${experiment.score_delta >= 0 ? "+" : ""}${experiment.score_delta.toFixed(3)} paired delta`;
  byId("latency").textContent = `${Math.round(candidate.p95_latency_ms)} ms`;
  byId("cost").textContent = `$${candidate.mean_cost_usd.toFixed(4)}`;

  byId("decisionBadge").textContent = decision.status.replaceAll("_", " ");
  byId("decisionBadge").className = `decision-badge ${decision.status}`;
  byId("decisionCallout").textContent = decision.reasons.length
    ? decision.reasons.join(" ")
    : "All release checks passed. The candidate is eligible for controlled promotion.";
  byId("checks").innerHTML = Object.entries(decision.checks)
    .map(([name, passed]) => `<div class="check ${passed ? "" : "failed"}"><span>${name.replaceAll("_", " ")}</span><b>${passed ? "PASS" : "FAIL"}</b></div>`)
    .join("");

  byId("successCompare").textContent = `${formatPercent(baseline.success_rate)} → ${formatPercent(candidate.success_rate)}`;
  byId("scoreCompare").textContent = `${baseline.mean_score.toFixed(3)} → ${candidate.mean_score.toFixed(3)}`;
  byId("confidenceInterval").textContent = `[${experiment.score_delta_ci95[0].toFixed(3)}, ${experiment.score_delta_ci95[1].toFixed(3)}]`;
  setBar("baselineSuccessBar", baseline.success_rate);
  setBar("candidateSuccessBar", candidate.success_rate);
  setBar("baselineScoreBar", baseline.mean_score);
  setBar("candidateScoreBar", candidate.mean_score);

  byId("auditStatus").className = `pill ${data.audit_chain_valid ? "good" : "bad"}`;
  byId("auditStatus").innerHTML = `<span class="status-dot"></span>${data.audit_chain_valid ? "Evidence verified" : "Evidence invalid"}`;
  byId("traceCount").textContent = `${data.counts.traces} traces`;
  byId("traceRows").innerHTML = data.traces.map((trace) => {
    const safe = (value) => String(value).replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[char]));
    const policy = trace.policy_violations.length ? `<span class="policy-fail">${trace.policy_violations.length} violation</span>` : '<span class="policy-ok">clear</span>';
    return `<tr><td>${safe(trace.scenario_id)}</td><td>${safe(trace.variant)}</td><td>${safe(trace.model)}</td><td>${safe(trace.tool_calls.join(" → ") || "none")}</td><td>${Math.round(trace.latency_ms)} ms</td><td>$${trace.cost_usd.toFixed(4)}</td><td>${policy}</td></tr>`;
  }).join("");
}

async function loadDashboard() {
  const response = await fetch("/api/v1/dashboard", { headers: headers() });
  if (response.status === 401) return;
  if (!response.ok) throw new Error("Dashboard request failed");
  render(await response.json());
}

async function runDemo() {
  const button = byId("runDemo");
  const message = byId("runMessage");
  button.disabled = true;
  button.textContent = "Evaluating…";
  message.textContent = "Replaying baseline and candidate across 40 matched scenarios.";
  try {
    const response = await fetch("/api/v1/experiments/demo", { method: "POST", headers: headers() });
    if (!response.ok) throw new Error(response.status === 401 ? "Check the API key." : "Evaluation failed.");
    await loadDashboard();
    message.textContent = "Evaluation complete. The gate decision is backed by replayable evidence.";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Run canary evaluation";
  }
}

byId("runDemo").addEventListener("click", runDemo);
loadDashboard().catch(() => {});
