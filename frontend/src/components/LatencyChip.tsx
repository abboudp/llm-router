import { formatLatency } from "../lib/format";

export function LatencyChip({ latencyMs }: { latencyMs: number }) {
  return (
    <span className="latency-chip" data-testid="latency-chip">
      {formatLatency(latencyMs)}
    </span>
  );
}
