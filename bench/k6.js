import http from "k6/http";
import { check } from "k6";
import { SharedArray } from "k6/data";

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

// per-VU: same prompt must always yield the same signature
const seenSignatures = {};

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
  const res = http.post(
    "http://localhost:8000/v1/generate",
    JSON.stringify({ prompt: prompt, max_tokens: 64 }),
    { headers: { "Content-Type": "application/json" } }
  );
  let body = {};
  try {
    body = res.json();
  } catch (e) {
    body = {};
  }
  const sig = (body && body.signature) || "";
  const firstSeen = !(prompt in seenSignatures);
  const stable = firstSeen || seenSignatures[prompt] === sig;
  if (firstSeen) seenSignatures[prompt] = sig;

  check(res, {
    "status 200": (r) => r.status === 200,
    "completion non-empty": () =>
      typeof body.completion === "string" && body.completion.length > 0,
    "signature well-formed": () => /^[0-9a-f]{64}$/.test(sig),
    "signature stable for prompt": () => stable,
  });
}

export function handleSummary(data) {
  const t = data.metrics.http_req_duration.values;
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
