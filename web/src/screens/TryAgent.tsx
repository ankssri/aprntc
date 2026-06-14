import { useState } from "react";
import { api, AgentInfo, AgentRunResult } from "../lib/api";
import { useAsync, pct } from "../lib/hooks";
import { Badge, Button, Card, Empty, PageHeader, Spinner } from "../components/ui";
import {
  IconBolt,
  IconPlay,
  IconQuote,
  IconSparkle,
  IconThumbDown,
  IconThumbUp,
} from "../components/icons";

export default function TryAgent() {
  const { data, loading, error } = useAsync(() => api.agents(), []);
  const [agentId, setAgentId] = useState("byteplus");
  const [task, setTask] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AgentRunResult | null>(null);
  const [runErr, setRunErr] = useState<string | null>(null);

  if (loading) return <Spinner />;
  if (error) return <Empty icon={<IconBolt className="h-8 w-8" />} title="Couldn't reach the API" sub={error} />;
  if (!data?.available)
    return (
      <Empty
        icon={<IconBolt className="h-8 w-8" />}
        title="Agent runtime not connected"
        sub="The backend needs ModelArk keys (.env) to run agents live."
      />
    );

  const agents = data.agents;
  const active = agents.find((a) => a.id === agentId) ?? agents[0];

  const run = async (t: string) => {
    const q = t.trim();
    if (!q) return;
    setRunning(true);
    setRunErr(null);
    setResult(null);
    try {
      setResult(await api.runAgent(agentId, q));
    } catch (e: any) {
      setRunErr(e.message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Try an agent"
        sub="Ask a question — the agent runs live, and the full trajectory is captured to the store."
      />

      <div className="mb-4 flex gap-2">
        {agents.map((a) => (
          <AgentTab key={a.id} agent={a} active={a.id === agentId} onClick={() => { setAgentId(a.id); setResult(null); }} />
        ))}
      </div>

      <p className="mb-3 text-sm text-muted">{active.description}</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(task);
        }}
        className="mb-3 flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2"
      >
        <input
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder={`Ask the ${active.name} agent…`}
          className="flex-1 bg-transparent text-sm text-fg outline-none placeholder:text-faint"
        />
        <Button variant="primary" disabled={running || !task.trim()}>
          {running ? "Running…" : <><IconPlay className="h-4 w-4" /> Run</>}
        </Button>
      </form>

      <div className="mb-6 flex flex-wrap gap-2">
        {active.examples.map((ex) => (
          <button
            key={ex}
            onClick={() => { setTask(ex); run(ex); }}
            disabled={running}
            className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-muted transition hover:bg-surface-2 hover:text-fg disabled:opacity-50"
          >
            {ex}
          </button>
        ))}
      </div>

      {running && <Spinner />}
      {runErr && <Empty icon={<IconBolt className="h-8 w-8" />} title="Run failed" sub={runErr} />}
      {result && !running && <Result r={result} />}
    </div>
  );
}

function AgentTab({ agent, active, onClick }: { agent: AgentInfo; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-medium transition ${
        active
          ? "border-accent bg-accent/10 text-accent"
          : "border-border bg-surface text-muted hover:bg-surface-2 hover:text-fg"
      }`}
    >
      <IconSparkle className="h-4 w-4" />
      {agent.name}
    </button>
  );
}

function rewardTone(r: number): "success" | "warning" | "danger" {
  if (r >= 0.7) return "success";
  if (r >= 0.4) return "warning";
  return "danger";
}

function Result({ r }: { r: AgentRunResult }) {
  const [vote, setVote] = useState<"up" | "down" | null>(null);
  const [sending, setSending] = useState(false);

  const sendVote = async (v: "up" | "down") => {
    if (sending || vote === v) return;
    setSending(true);
    try {
      await api.feedback(r.episode_id, v);
      setVote(v);
    } catch {
      /* feedback is best-effort; ignore UI errors */
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-muted">Answer</span>
          {r.reward != null && <Badge tone={rewardTone(r.reward)}>reward {pct(r.reward)}</Badge>}
        </div>
        <p className="text-sm text-fg">{r.answer}</p>
        {r.reward_rationale && (
          <p className="mt-2 text-[11px] text-faint">scored: {r.reward_rationale}</p>
        )}

        {/* user feedback — explicit signal that outranks the judge in fusion */}
        <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
          <span className="text-[11px] text-faint">Was this helpful?</span>
          <button
            onClick={() => sendVote("up")}
            disabled={sending}
            aria-label="thumbs up"
            className={`rounded-lg border p-1.5 transition disabled:opacity-50 ${
              vote === "up"
                ? "border-success bg-success/10 text-success"
                : "border-border text-muted hover:bg-surface-2 hover:text-fg"
            }`}
          >
            <IconThumbUp className="h-4 w-4" />
          </button>
          <button
            onClick={() => sendVote("down")}
            disabled={sending}
            aria-label="thumbs down"
            className={`rounded-lg border p-1.5 transition disabled:opacity-50 ${
              vote === "down"
                ? "border-danger bg-danger/10 text-danger"
                : "border-border text-muted hover:bg-surface-2 hover:text-fg"
            }`}
          >
            <IconThumbDown className="h-4 w-4" />
          </button>
          {vote && <span className="text-[11px] text-faint">thanks — feedback recorded</span>}
        </div>
      </Card>

      {r.cited.length > 0 && (
        <div>
          <div className="mb-2 text-sm font-medium text-muted">Sources cited</div>
          <Card className="divide-y divide-border">
            {r.cited.map((c, i) => (
              <div key={i} className="flex items-center gap-2 px-4 py-2.5 text-sm">
                <IconQuote className="h-4 w-4 shrink-0 text-faint" />
                <span className="text-fg">{c}</span>
              </div>
            ))}
          </Card>
        </div>
      )}

      {r.steps.length > 0 && (
        <div>
          <div className="mb-2 text-sm font-medium text-muted">Tool steps</div>
          <Card className="divide-y divide-border">
            {r.steps.map((s, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <Badge>{s.type}</Badge>
                {s.tool_name && <span className="font-mono text-xs text-fg">{s.tool_name}</span>}
                {s.tool_args != null && (
                  <span className="truncate font-mono text-[11px] text-faint">
                    {JSON.stringify(s.tool_args).slice(0, 60)}
                  </span>
                )}
                {s.duration_ms != null && (
                  <span className="ml-auto text-[11px] text-faint">{s.duration_ms} ms</span>
                )}
              </div>
            ))}
          </Card>
        </div>
      )}

      {r.reasoning && (
        <div>
          <div className="mb-2 text-sm font-medium text-muted">Reasoning trace</div>
          <Card className="p-4">
            <p className="text-xs leading-relaxed text-muted">{r.reasoning}</p>
          </Card>
        </div>
      )}

      <p className="text-center text-[11px] text-faint">
        Captured as episode <span className="font-mono">{r.episode_id.slice(0, 16)}…</span> — see it on the Trajectories screen.
      </p>
    </div>
  );
}
