import { useState } from "react";
import { api, EpisodeSummary } from "../lib/api";
import { useAsync, pct } from "../lib/hooks";
import { Badge, Card, Empty, PageHeader, Spinner } from "../components/ui";
import { IconTrace } from "../components/icons";

export default function Trajectories() {
  const { data, loading, error } = useAsync(() => api.trajectories(100), []);
  const [open, setOpen] = useState<string | null>(null);

  if (loading) return <Spinner />;
  if (error) return <Empty icon={<IconTrace className="h-8 w-8" />} title="Couldn't reach the API" sub={error} />;
  if (!data?.episodes.length)
    return (
      <Empty
        icon={<IconTrace className="h-8 w-8" />}
        title="No trajectories captured"
        sub="Run an agent (scripts/demo_agents.py) to populate the trajectory store."
      />
    );

  return (
    <div>
      <PageHeader title="Trajectories" sub={`${data.count} captured episodes`} />
      <div className="space-y-2">
        {data.episodes.map((e) => (
          <EpisodeRow key={e.episode_id} e={e} open={open === e.episode_id} onToggle={() => setOpen(open === e.episode_id ? null : e.episode_id)} />
        ))}
      </div>
    </div>
  );
}

function rewardTone(r: number | null): "success" | "warning" | "danger" | "default" {
  if (r == null) return "default";
  if (r >= 0.7) return "success";
  if (r >= 0.4) return "warning";
  return "danger";
}

function EpisodeRow({ e, open, onToggle }: { e: EpisodeSummary; open: boolean; onToggle: () => void }) {
  const detail = useAsync(() => api.trajectory(e.episode_id), [open ? e.episode_id : ""]);
  return (
    <Card>
      <button onClick={onToggle} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        <div className="flex-1 truncate">
          <div className="truncate text-sm font-medium text-fg">{e.task_input}</div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-faint">
            <span className="font-mono">{e.episode_id.slice(0, 14)}…</span>
            <span>· {e.collector}</span>
            <span>· {e.n_turns} turns · {e.n_steps} steps</span>
            {e.partial && <Badge tone="warning">partial</Badge>}
          </div>
        </div>
        {e.reward != null && <Badge tone={rewardTone(e.reward)}>reward {pct(e.reward)}</Badge>}
      </button>
      {open && (
        <div className="border-t border-border px-4 py-3 text-sm">
          {detail.loading ? (
            <span className="text-muted">Loading…</span>
          ) : detail.data ? (
            <TrajectoryDetail data={detail.data as any} />
          ) : (
            <span className="text-danger">Failed to load</span>
          )}
        </div>
      )}
    </Card>
  );
}

function TrajectoryDetail({ data }: { data: any }) {
  return (
    <div className="space-y-3">
      {data.final_output && (
        <div>
          <div className="mb-1 text-xs text-muted">Final answer</div>
          <div className="rounded-lg bg-surface-2 px-3 py-2 text-sm">{data.final_output}</div>
        </div>
      )}
      {(data.turns ?? []).map((t: any) => (
        <div key={t.turn_index}>
          {(t.steps ?? []).length > 0 && (
            <div className="space-y-1">
              {t.steps.map((s: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <Badge>{s.type}</Badge>
                  {s.tool_name && <span className="font-mono text-muted">{s.tool_name}</span>}
                  {s.source_fidelity && s.source_fidelity !== "full" && (
                    <span className="text-faint">({s.source_fidelity})</span>
                  )}
                  {s.error && <span className="text-danger">{s.error}</span>}
                </div>
              ))}
            </div>
          )}
          {t.reasoning_content && (
            <div className="mt-2 rounded-lg border border-border px-3 py-2 text-xs text-muted">
              <span className="text-faint">reasoning · </span>
              {t.reasoning_content}
            </div>
          )}
        </div>
      ))}
      {data.labels?.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {data.labels.map((l: any, i: number) => (
            <Badge key={i}>
              {l.source}: {pct(l.score)}
            </Badge>
          ))}
          {data.fused_reward && <Badge tone="accent">fused {pct(data.fused_reward.reward)}</Badge>}
        </div>
      )}
    </div>
  );
}
