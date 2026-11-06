import http from "k6/http";
import { check } from "k6";
import { SharedArray } from "k6/data";
import { Trend } from "k6/metrics";

const workload = new SharedArray("workload", () =>
  JSON.parse(open("./workload.json"))
);
const totalWeight = workload.reduce((sum, item) => sum + item.weight, 0);

export const options = {
  scenarios: {
    steady: {
      executor: "constant-arrival-rate",
      rate: 30,
      timeUnit: "1s",
      duration: "60s",
      preAllocatedVUs: 250,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    checks: ["rate>0.99"],
  },
  summaryTrendStats: ["avg", "p(50)", "p(95)", "p(99)", "max"],
};

// Only the /v1/generate call is reported; conversation setup is excluded.
const generateDuration = new Trend("generate_duration", true);

const BASE_URL = "http://localhost:8000";
const JSON_HEADERS = { headers: { "Content-Type": "application/json" } };

function pickPrompt() {
  let r = Math.random() * totalWeight;
  for (const item of workload) {
    r -= item.weight;
    if (r <= 0) return item;
  }
  return workload[workload.length - 1];
}

export default function () {
  const item = pickPrompt();
  // tail prompts carry a unique request context to mimic real traffic variety
  const prompt = item.weight <= 3 ? `${item.prompt} [ctx ${__VU}-${__ITER}]` : item.prompt;

  // A fresh conversation per iteration keeps the flattened upstream prompt
  // free of prior history, so request size doesn't grow over the run.
  const convo = http.post(`${BASE_URL}/v1/conversations`, "{}", {
    ...JSON_HEADERS,
    tags: { name: "create_conversation" },
  });
  const conversationId = convo.status === 201 ? convo.json("id") : null;

  const res = http.post(
    `${BASE_URL}/v1/generate`,
    JSON.stringify({ conversation_id: conversationId, message: prompt, max_tokens: 64 }),
    { ...JSON_HEADERS, tags: { name: "generate" } }
  );
  generateDuration.add(res.timings.duration);
  let body = {};
  try {
    body = res.json();
  } catch (e) {
    body = {};
  }
  const content = body && body.message ? body.message.content : undefined;

  check(res, {
    "status 200": (r) => r.status === 200,
    "assistant message non-empty": () => typeof content === "string" && content.length > 0,
    "latency_ms reported": () => Number.isInteger(body.latency_ms),
  });
}

export function handleSummary(data) {
  const t = data.metrics.generate_duration.values;
  const err = data.metrics.http_req_failed.values.rate;
  const chk = data.metrics.checks ? data.metrics.checks.values.rate : 1;
  const fmt = (label, value) => `  ${label.padEnd(12)} ${value}\n`;
  let out = "\n=== bench summary (60s @ 30 rps) ===\n";
  out += fmt("p50", `${t["p(50)"].toFixed(0)} ms`);
  out += fmt("p95", `${t["p(95)"].toFixed(0)} ms`);
  out += fmt("p99", `${t["p(99)"].toFixed(0)} ms`);
  out += fmt("error rate", `${(err * 100).toFixed(2)} %`);
  out += fmt("checks", `${(chk * 100).toFixed(2)} %`);
  return { stdout: out };
}
