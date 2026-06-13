import { api, Generation } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { Badge, Card, Empty, PageHeader, Spinner } from "../components/ui";
import { IconBranch, IconDot } from "../components/icons";

export default function Lineage() {
  const { data, loading, error } = useAsync(() => api.lineage(), []);

  if (loading) return <Spinner />;
  if (error) return <Empty icon={<IconBranch className="h-8 w-8" />} title="Couldn't reach the API" sub={error} />;
  if (!data?.generations.length)
    return (
      <Empty
        icon={<IconBranch className="h-8 w-8" />}
        title="No lineage yet"
        sub="Generations appear here once a parent is registered and children are promoted."
      />
    );

  const currentGen = data.current?.generation;
  const ordered = [...data.generations].sort((a, b) => a.generation - b.generation);

  return (
    <div>
      <PageHeader
        title="Lineage"
        sub="The promoted path of agent generations. Each generation pins a playbook and its gate result."
        right={
          data.current && (
            <Badge tone="accent">
              <IconDot className="h-3 w-3" /> live: G{data.current.generation}
            </Badge>
          )
        }
      />

      <div className="relative pl-6">
        <div className="absolute left-[9px] top-2 bottom-2 w-px bg-border" />
        <div className="space-y-3">
          {ordered
            .slice()
            .reverse()
            .map((g) => (
              <GenerationCard key={g.generation} g={g} live={g.generation === currentGen} />
            ))}
        </div>
      </div>
    </div>
  );
}

function GenerationCard({ g, live }: { g: Generation; live: boolean }) {
  return (
    <div className="relative">
      <div
        className={`absolute -left-[19px] top-5 h-3.5 w-3.5 rounded-full border-2 ${
          live ? "border-accent bg-accent" : "border-border bg-surface"
        }`}
      />
      <Card className={`p-4 ${live ? "ring-1 ring-accent/40" : ""}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-base font-semibold">G{g.generation}</span>
            {live && <Badge tone="accent">live</Badge>}
            {g.parent_generation != null && (
              <span className="text-xs text-faint">from G{g.parent_generation}</span>
            )}
          </div>
          <span className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-muted">
            {g.playbook_hash}
          </span>
        </div>
        {(g.gate_summary || g.note) && (
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {g.gate_summary && <span>{g.gate_summary}</span>}
            {g.note && <span className="text-faint">· {g.note}</span>}
          </div>
        )}
      </Card>
    </div>
  );
}
