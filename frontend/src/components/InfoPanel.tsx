import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Info } from "../api/types";
import { formatUptime } from "../lib/time";

/** Best-effort app metadata (name + version) fetched from /v1/info for the sidebar footer. */
export function InfoPanel() {
  const [info, setInfo] = useState<Info | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api
      .getInfo()
      .then((result) => {
        if (!cancelled) setInfo(result);
      })
      .catch(() => {
        /* info is a nice-to-have; leave the panel empty if it fails */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!info) return null;

  return (
    <div
      className="info-panel"
      data-testid="info-panel"
      title={`Available models: ${info.models.join(", ")}`}
    >
      <span className="info-panel-name">{info.name}</span>
      <span className="info-panel-version">v{info.version}</span>
      <span className="info-panel-uptime">up {formatUptime(info.uptime_s)}</span>
    </div>
  );
}
