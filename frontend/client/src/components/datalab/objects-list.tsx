import { useMemo, useState } from "react";
import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useDataLabDatasets, useDataLabPipelines, useDataLabScripts, useDataLabImportProcesses } from "@/hooks/use-datalab";
import { Plus, Database, Workflow, Code2, FileCode2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

// "dataset" = durable, versioned data (from pipelines/promotion)
type Selection = { view: "dataset" | "generator" | "script" | "import-process" | "welcome"; id?: string };

export function ObjectsList({
  selected,
}: {
  onSelect: (view: Selection["view"], id?: string) => void;
  selected: Selection;
}) {
  const [search, setSearch] = useState("");
  const { data: datasetsData } = useDataLabDatasets(1, 50);
  const { data: scripts } = useDataLabScripts();
  const { data: pipelines } = useDataLabPipelines();
  const { data: importProcesses } = useDataLabImportProcesses(1, 50);

  const filterMatch = (text?: string) =>
    !search || (text || "").toLowerCase().includes(search.toLowerCase());

  const datasetItems = useMemo(
    () => (datasetsData?.results || []).filter((ds) => filterMatch(ds.name || ds.id)),
    [datasetsData, search]
  );
  const scriptItems = useMemo(
    () => (scripts || []).filter((s) => filterMatch(s.name || s.id)),
    [scripts, search]
  );
  const generatorItems = useMemo(
    () => (pipelines || []).filter((p) => filterMatch(p.name || p.id)),
    [pipelines, search]
  );
  const importProcessItems = useMemo(
    () => (importProcesses?.results || []).filter((p) => filterMatch(p.name || p.id)),
    [importProcesses, search]
  );

  const isActive = (view: Selection["view"], id?: string) =>
    selected.view === view && (!id || selected.id === id);

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="p-3 border-b border-border">
        <Input
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 text-sm"
        />
      </div>
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-3 space-y-5">
          {/* Datasets - durable, versioned data from pipelines */}
          <Section
            title="Datasets"
            icon={<Database className="h-3.5 w-3.5" />}
            count={datasetItems.length}
            addHref="/datalab/generator/new"
            addLabel="Create via generator"
          >
            {datasetItems.slice(0, 8).map((ds) => (
              <ItemRow
                key={ds.id}
                href={`/datalab/dataset/${ds.id}`}
                title={ds.name || "Untitled"}
                meta={`${(ds.row_count ?? 0).toLocaleString()} rows`}
                active={isActive("dataset", ds.id)}
              />
            ))}
            {datasetItems.length === 0 && <EmptyRow text="Create a generator to produce datasets" />}
            {datasetItems.length > 8 && (
              <div className="text-xs text-muted-foreground px-2">+{datasetItems.length - 8} more</div>
            )}
          </Section>

          {/* Generators */}
          <Section
            title="Generators"
            icon={<Workflow className="h-3.5 w-3.5" />}
            count={generatorItems.length}
            addHref="/datalab/generator/new"
          >
            {generatorItems.slice(0, 6).map((p) => (
              <ItemRow
                key={p.id}
                href={`/datalab/generator/${p.id}`}
                title={p.name}
                meta={`${p.steps_json?.length ?? 0} steps`}
                active={isActive("generator", p.id)}
              />
            ))}
            {generatorItems.length === 0 && <EmptyRow />}
          </Section>

          {/* Scripts */}
          <Section
            title="Scripts"
            icon={<Code2 className="h-3.5 w-3.5" />}
            count={scriptItems.length}
            addHref="/datalab/script/new"
          >
            {scriptItems.slice(0, 6).map((s) => (
              <ItemRow
                key={s.id}
                href={`/datalab/script/${s.id}`}
                title={s.name}
                meta={s.slug}
                active={isActive("script", s.id)}
              />
            ))}
            {scriptItems.length === 0 && <EmptyRow />}
          </Section>

          {/* Import Processes (tool/component) */}
          <Section
            title="Import Processes"
            icon={<FileCode2 className="h-3.5 w-3.5" />}
            count={importProcessItems.length}
            addHref="/datalab/import-process/new"
          >
            {importProcessItems.slice(0, 4).map((p) => (
              <ItemRow
                key={p.id}
                href={`/datalab/import-process/${p.id}`}
                title={p.name}
                meta={p.file_type}
                active={isActive("import-process", p.id)}
              />
            ))}
            {importProcessItems.length === 0 && <EmptyRow />}
          </Section>
        </div>
      </ScrollArea>
    </div>
  );
}

function Section({
  title,
  icon,
  count,
  addHref,
  addLabel,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  count?: number;
  addHref?: string;
  addLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          {icon}
          <span>{title}</span>
          {typeof count === "number" && count > 0 && (
            <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded">{count}</span>
          )}
        </div>
        {addHref && (
          <Link href={addHref}>
            <Button size="icon" variant="ghost" className="h-6 w-6" aria-label={addLabel || `Add ${title.toLowerCase()}`}>
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </Link>
        )}
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function ItemRow({
  href,
  title,
  meta,
  badge,
  active,
}: {
  href: string;
  title: string;
  meta?: string;
  badge?: string;
  active?: boolean;
}) {
  return (
    <Link href={href}>
      <a
        className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
          active ? "bg-accent text-accent-foreground" : "hover:bg-muted/60"
        }`}
      >
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium text-[13px]">{title}</div>
          {meta && <div className="truncate text-[11px] text-muted-foreground">{meta}</div>}
        </div>
        {badge && (
          <Badge variant="outline" className="text-[10px] shrink-0 capitalize">
            {badge}
          </Badge>
        )}
      </a>
    </Link>
  );
}

function EmptyRow({ text }: { text?: string }) {
  return <div className="text-xs text-muted-foreground px-2 py-1 italic">{text || "None yet"}</div>;
}
