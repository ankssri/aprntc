import { useState } from "react";
import { api, Lesson } from "../lib/api";
import { useAsync, pct } from "../lib/hooks";
import { Badge, Card, Empty, PageHeader, Spinner } from "../components/ui";
import { IconBook, IconSearch } from "../components/icons";

const TYPE_TONE: Record<string, "success" | "warning" | "accent" | "default"> = {
  directive: "success",
  failure_pattern: "warning",
  exemplar: "accent",
  routing_heuristic: "default",
};

export default function Lessons() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("refund");
  const { data, loading, error } = useAsync(() => api.lessons(submitted, 12), [submitted]);

  return (
    <div>
      <PageHeader title="Experience memory" sub="Distilled, generation-versioned lessons retrieved by semantic search." />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query || submitted);
        }}
        className="mb-5 flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2"
      >
        <IconSearch className="h-4 w-4 text-faint" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search lessons… (showing "${submitted}")`}
          className="flex-1 bg-transparent text-sm text-fg outline-none placeholder:text-faint"
        />
      </form>

      {loading ? (
        <Spinner />
      ) : error ? (
        <Empty icon={<IconBook className="h-8 w-8" />} title="Couldn't reach the API" sub={error} />
      ) : !data?.available ? (
        <Empty
          icon={<IconBook className="h-8 w-8" />}
          title="Memory not connected"
          sub="Wire a VikingDB MemoryStore into the API to browse lessons."
        />
      ) : data.error ? (
        <Empty icon={<IconBook className="h-8 w-8" />} title="Memory search failed" sub={data.error} />
      ) : !data.lessons.length ? (
        <Empty icon={<IconBook className="h-8 w-8" />} title="No lessons found" sub={`Nothing matched "${submitted}".`} />
      ) : (
        <div className="space-y-2">
          {data.lessons.map((l, i) => (
            <LessonRow key={(l.lesson_id as string) ?? i} l={l} />
          ))}
        </div>
      )}
    </div>
  );
}

function LessonRow({ l }: { l: Lesson }) {
  const type = (l.lesson_type as string) ?? "directive";
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 text-sm text-fg">{(l.content as string) ?? "—"}</div>
        <Badge tone={TYPE_TONE[type] ?? "default"}>{type}</Badge>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-faint">
        {l.lesson_id && <span className="font-mono">{String(l.lesson_id).slice(0, 16)}</span>}
        {l.reward != null && <span>reward {pct(l.reward as number)}</span>}
        {l.score != null && <span>match {pct(l.score as number)}</span>}
      </div>
    </Card>
  );
}
