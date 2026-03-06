import { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  useDataLabImportRuns,
  useDataLabResultSet,
  useDataLabPipelines,
  useDataLabScripts,
} from "@/hooks/use-datalab";
import { formatDate } from "@/lib/utils";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Circle } from "lucide-react";

type View = "dataset" | "generator" | "script" | "import-process" | "welcome";

export function PropertiesPanel({
  view,
  id,
  onSelect,
}: {
  view: View;
  id?: string;
  onSelect: (view: View, id?: string) => void;
}) {
  if (view === "dataset" && id) {
    return <DatasetProps id={id} />;
  }
  if (view === "generator" && id) {
    return <GeneratorProps id={id} onSelect={onSelect} />;
  }
  if (view === "script" && id) {
    return <ScriptProps id={id} />;
  }
  if (view === "import-process" && id) {
    return <ImportProcessProps id={id} />;
  }
  return <WelcomeTimeline />;
}

function DatasetProps({ id }: { id: string }) {
  const { data: rs } = useDataLabResultSet(id);
  if (!rs) return <Empty />;
  return (
    <Card className="h-full rounded-none border-0 border-l border-border shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Dataset</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="font-semibold">{rs.name || "Dataset"}</div>
        <div className="text-muted-foreground">
          Rows: {rs.row_count.toLocaleString()} • Cols: {rs.schema_json.length}
        </div>
        <div className="text-muted-foreground">Storage: {rs.storage}</div>
        <div className="text-muted-foreground">Created: {formatDate(rs.created_at)}</div>
        <div className="text-muted-foreground">Origin: {rs.origin}</div>
        <div className="flex gap-2 pt-2">
          <Button size="sm" variant="outline">
            Visualize
          </Button>
          <Button size="sm" variant="outline">
            Snapshot
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function GeneratorProps({ id, onSelect }: { id: string; onSelect: (v: View, id?: string) => void }) {
  const { data: pipelines } = useDataLabPipelines();
  const gen = useMemo(() => (pipelines || []).find((p) => p.id === id), [pipelines, id]);
  if (!gen) return <Empty />;
  return (
    <Card className="h-full rounded-none border-0 border-l border-border shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Generator</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="font-semibold">{gen.name}</div>
        <div className="text-muted-foreground">Steps: {gen.steps_json?.length ?? 0}</div>
        <div className="text-muted-foreground">Params: {gen.params_json?.length ?? 0}</div>
        <div className="flex gap-2 pt-2">
          <Button size="sm" onClick={() => onSelect("generator", id)}>
            Edit
          </Button>
          <Button size="sm" variant="outline">
            Run
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ScriptProps({ id }: { id: string }) {
  const { data: scripts } = useDataLabScripts();
  const script = useMemo(() => (scripts || []).find((s) => s.id === id), [scripts, id]);
  if (!script) return <Empty />;
  return (
    <Card className="h-full rounded-none border-0 border-l border-border shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Script</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="font-semibold">{script.name}</div>
        <div className="text-muted-foreground">Slug: {script.slug}</div>
        <div className="flex gap-2 pt-2">
          <Badge variant="outline">Inputs: {Object.keys(script.input_spec_json || {}).length}</Badge>
          <Badge variant="outline">Outputs: {Object.keys(script.output_spec_json || {}).length}</Badge>
        </div>
      </CardContent>
    </Card>
  );
}

function Empty() {
  return (
    <div className="h-full p-4 text-sm text-muted-foreground">
      Details unavailable for this selection.
    </div>
  );
}

function ImportProcessProps({ id }: { id: string }) {
  // Placeholder: uses pipelines list as proxy until import process detail hook exists
  return (
    <Card className="h-full rounded-none border-0 border-l border-border shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Import Process</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="font-semibold">Process {id}</div>
        <div className="text-muted-foreground">Inspect and edit in the main pane.</div>
      </CardContent>
    </Card>
  );
}

function WelcomeTimeline() {
  const { data: importRuns } = useDataLabImportRuns(1, 12);

  const runs = importRuns?.results ?? [];

  const getStatusColor = (status?: string) => {
    if (!status) return "text-foreground/40";
    const s = status.toLowerCase();
    if (s === "success") return "text-emerald-500";
    if (s === "failed") return "text-red-500";
    if (s === "running" || s === "pending") return "text-amber-500";
    return "text-foreground/40";
  };

  return (
    <div className="h-full p-4">
      <GlassPanel className="p-4 space-y-4 h-full">
        <div>
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Latest activity</p>
          <h2 className="text-lg font-semibold">Timeline</h2>
        </div>
        {runs.length === 0 ? (
          <div className="text-sm text-muted-foreground">No activity yet.</div>
        ) : (
          <div className="space-y-4">
            {runs.map((run) => (
              <div key={run.id} className="flex items-start gap-3">
                <div className="mt-1">
                  <Circle className={`h-3 w-3 ${getStatusColor(run.status)}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">
                    {run.import_process_name || "Import run"}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {run.status} • {formatDate(run.started_at)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
