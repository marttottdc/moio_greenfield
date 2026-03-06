import { useMemo, useState } from "react";
import { useLocation, useRoute } from "wouter";
import { ScrollArea } from "@/components/ui/scroll-area";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { StatCard } from "@/components/datalab/stat-card";
import { DatasetViewer } from "@/components/datalab/dataset-viewer";
import { ResultSetViewer } from "@/components/datalab/resultset-viewer";
import { GeneratorEditor } from "@/components/datalab/generator-editor";
import { ScriptEditor } from "@/components/datalab/script-editor";
import { ImportProcessEditor } from "@/components/datalab/importprocess-editor";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  useDataLabImportRuns,
  useDataLabPipelines,
  useDataLabResultSets,
  useDataLabDatasets,
  useDataLabScripts,
  useDataLabImportProcesses,
} from "@/hooks/use-datalab";
import {
  Layers,
  PlayCircle,
  Workflow,
  Code2,
  ArrowRight,
  ArrowLeft,
  Table2,
  Database,
  FileCode2,
  Wrench,
  BarChart3,
  Search,
  Plus,
} from "lucide-react";

// Tab types
// "datasets" = durable versioned data (from pipelines/promotion) - the main product
// "resultsets" = intermediate outputs (from scripts/imports) - accessible via components
type TabType = "datasets" | "generators" | "components" | "runs";
type ComponentView = "scripts" | "resultsets" | "import-processes" | "custom-tables" | null;

export default function DataLabWorkbench() {
  const [location, setLocation] = useLocation();

  // Route matching for detail views
  const [isDataset, datasetParams] = useRoute("/datalab/dataset/:id");
  const [isResultSet, resultSetParams] = useRoute("/datalab/resultset/:id");
  const [isGeneratorNew] = useRoute("/datalab/generator/new");
  const [isGenerator, generatorParams] = useRoute("/datalab/generator/:id");
  const [isScriptNew] = useRoute("/datalab/script/new");
  const [isScript, scriptParams] = useRoute("/datalab/script/:id");
  const [isImportProcessNew] = useRoute("/datalab/import-process/new");
  const [isImportProcess, importProcessParams] = useRoute("/datalab/import-process/:id");

  // Determine if we're in a detail view
  const isDetailView =
    isDataset || isResultSet || isGenerator || isGeneratorNew || isScript || isScriptNew || isImportProcess || isImportProcessNew;

  const detailId =
    (isDataset ? datasetParams?.id : undefined) ??
    (isResultSet ? resultSetParams?.id : undefined) ??
    (isGenerator && !isGeneratorNew ? generatorParams?.id : undefined) ??
    (isScript && !isScriptNew ? scriptParams?.id : undefined) ??
    (isImportProcess && !isImportProcessNew ? importProcessParams?.id : undefined) ??
    undefined;

  // State
  const [activeTab, setActiveTab] = useState<TabType>("datasets");
  const [componentView, setComponentView] = useState<ComponentView>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const handleSelect = (type: string, id?: string) => {
    if (type === "dataset" && id) return setLocation(`/datalab/dataset/${id}`);
    if (type === "resultset" && id) return setLocation(`/datalab/resultset/${id}`);
    if (type === "generator") return setLocation(id ? `/datalab/generator/${id}` : "/datalab/generator/new");
    if (type === "script") return setLocation(id ? `/datalab/script/${id}` : "/datalab/script/new");
    if (type === "import-process") return setLocation(id ? `/datalab/import-process/${id}` : "/datalab/import-process/new");
    return setLocation("/datalab");
  };

  const handleBackFromComponentView = () => {
    setComponentView(null);
    setSearchQuery("");
  };

  // Data fetching
  const { data: datasetsData } = useDataLabDatasets(1, 50);  // Durable datasets
  const { data: resultSetsData } = useDataLabResultSets(undefined, 1, 50);  // Intermediate
  const { data: pipelines } = useDataLabPipelines();
  const { data: scripts } = useDataLabScripts();
  const { data: importRuns } = useDataLabImportRuns(1, 20);
  const { data: importProcesses } = useDataLabImportProcesses(1, 50);

  const stats = useMemo(() => ({
    datasets: datasetsData?.count ?? 0,
    resultsets: resultSetsData?.count ?? 0,
    generators: pipelines?.length ?? 0,
    scripts: scripts?.length ?? 0,
    runs: importRuns?.count ?? 0,
    importProcesses: importProcesses?.results?.length ?? 0,
  }), [datasetsData, resultSetsData, pipelines, scripts, importRuns, importProcesses]);

  const tabItems = [
    { id: "datasets" as TabType, label: "Datasets", icon: Database },
    { id: "generators" as TabType, label: "Generators", icon: Workflow },
    { id: "components" as TabType, label: "Components", icon: Wrench },
    { id: "runs" as TabType, label: "Runs", icon: BarChart3 },
  ];

  // Render detail views
  const renderDetailView = () => {
    if (isDataset && detailId) return <DatasetViewer id={detailId} />;
    if (isResultSet && detailId) return <ResultSetViewer id={detailId} onSelect={handleSelect} />;
    if (isGenerator || isGeneratorNew) return <GeneratorEditor id={detailId} onSelect={handleSelect} />;
    if (isScript || isScriptNew) return <ScriptEditor id={detailId} onSelect={handleSelect} />;
    if (isImportProcess || isImportProcessNew) return <ImportProcessEditor id={detailId} onCreated={(newId) => handleSelect("import-process", newId)} />;
    return null;
  };

  // Filter helper
  const filterBySearch = (items: any[], fields: string[]) => {
    if (!searchQuery.trim()) return items;
    const q = searchQuery.toLowerCase();
    return items.filter((item) =>
      fields.some((f) => (item[f] || "").toLowerCase().includes(q))
    );
  };

  // Render left navigation
  const renderLeftNav = () => {
    // Component object list view (replaces tabs when drilling into a component type)
    if (componentView) {
      return (
        <>
          <div className="p-3 border-b border-border">
            <button
              onClick={handleBackFromComponentView}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Components
            </button>
            <h2 className="font-semibold text-sm capitalize">
              {componentView === "import-processes" ? "Import Processes" : componentView}
            </h2>
          </div>
          <div className="p-2 border-b border-border">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search..."
                className="pl-8 h-8 text-sm"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-2">
              {componentView === "scripts" && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full mb-2"
                    onClick={() => handleSelect("script")}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    New Script
                  </Button>
                  {filterBySearch(scripts || [], ["name", "slug"]).map((s) => (
                    <button
                      key={s.id}
                      onClick={() => handleSelect("script", s.id)}
                      className="w-full text-left p-2 rounded hover:bg-muted/50 transition-colors mb-1"
                    >
                      <div className="font-medium text-sm">{s.name}</div>
                      <div className="text-xs text-muted-foreground">{s.slug}</div>
                    </button>
                  ))}
                  {(scripts || []).length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-4">No scripts yet</p>
                  )}
                </>
              )}
              {componentView === "resultsets" && (
                <>
                  {filterBySearch(resultSetsData?.results || [], ["name", "id"]).map((rs) => (
                    <button
                      key={rs.id}
                      onClick={() => handleSelect("resultset", rs.id)}
                      className="w-full text-left p-2 rounded hover:bg-muted/50 transition-colors mb-1"
                    >
                      <div className="font-medium text-sm">{rs.name || "Untitled"}</div>
                      <div className="text-xs text-muted-foreground">
                        {rs.row_count?.toLocaleString() || 0} rows • {rs.origin}
                      </div>
                    </button>
                  ))}
                  {(resultSetsData?.results || []).length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-4">No result sets yet</p>
                  )}
                </>
              )}
              {componentView === "import-processes" && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full mb-2"
                    onClick={() => handleSelect("import-process")}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    New Import Process
                  </Button>
                  {filterBySearch(importProcesses?.results || [], ["name", "file_type"]).map((p) => (
                    <button
                      key={p.id}
                      onClick={() => handleSelect("import-process", p.id)}
                      className="w-full text-left p-2 rounded hover:bg-muted/50 transition-colors mb-1"
                    >
                      <div className="font-medium text-sm">{p.name}</div>
                      <div className="text-xs text-muted-foreground">Type: {p.file_type}</div>
                    </button>
                  ))}
                  {(importProcesses?.results || []).length === 0 && (
                    <p className="text-xs text-muted-foreground text-center py-4">No import processes yet</p>
                  )}
                </>
              )}
              {componentView === "custom-tables" && (
                <p className="text-xs text-muted-foreground text-center py-4">Coming soon</p>
              )}
            </div>
          </ScrollArea>
        </>
      );
    }

    // Default tab navigation
    return (
      <>
        <div className="p-3 border-b border-border">
          <h2 className="font-semibold text-sm">Data Lab</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Data Studio workbench</p>
        </div>
        <div className="p-2 space-y-1">
          {tabItems.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                setActiveTab(tab.id);
                setLocation("/datalab");
              }}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors ${
                !isDetailView && activeTab === tab.id
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-muted/50"
              }`}
            >
              <tab.icon className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </>
    );
  };

  return (
    <div className="h-full flex">
      {/* Left Navigation Rail */}
      <div className="w-64 border-r border-border bg-background flex flex-col shrink-0">
        {renderLeftNav()}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col bg-muted/20 overflow-hidden">
        {isDetailView ? (
          renderDetailView()
        ) : componentView ? (
          // Placeholder when viewing a component list (no object selected yet)
          <ComponentPlaceholder componentView={componentView} />
        ) : (
          <ScrollArea className="flex-1">
            <div className="p-4 space-y-4">
              {activeTab === "datasets" && (
                <DatasetsWorkspace
                  datasets={datasetsData?.results || []}
                  stats={stats}
                  onSelect={handleSelect}
                />
              )}
              {activeTab === "generators" && (
                <GeneratorsWorkspace
                  generators={pipelines || []}
                  stats={stats}
                  onSelect={handleSelect}
                />
              )}
              {activeTab === "components" && (
                <ComponentsWorkspace
                  stats={stats}
                  onOpenComponent={setComponentView}
                />
              )}
              {activeTab === "runs" && (
                <RunsWorkspace
                  runs={importRuns?.results || []}
                  stats={stats}
                />
              )}
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );
}

// Workspace Components
function DatasetsWorkspace({
  datasets,
  stats,
  onSelect,
}: {
  datasets: any[];
  stats: any;
  onSelect: (type: string, id?: string) => void;
}) {
  return (
    <div className="space-y-4">
      <GlassPanel className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Datasets" value={stats.datasets.toString()} helper="Durable data" icon={Database} accent="bg-primary/10 text-primary" />
        <StatCard label="Generators" value={stats.generators.toString()} helper="Pipelines" icon={Workflow} accent="bg-emerald-100 text-emerald-600" />
        <StatCard label="Result Sets" value={stats.resultsets.toString()} helper="Intermediate" icon={Table2} accent="bg-slate-100 text-slate-600" />
        <StatCard label="Runs" value={stats.runs.toString()} helper="Executions" icon={PlayCircle} accent="bg-indigo-100 text-indigo-600" />
      </GlassPanel>

      <GlassPanel className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">All Datasets</h3>
          <button
            onClick={() => onSelect("generator")}
            className="text-sm text-primary flex items-center gap-1 hover:gap-2 transition-all"
          >
            New Generator <ArrowRight className="h-3 w-3" />
          </button>
        </div>
        {datasets.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-sm text-muted-foreground mb-2">
              No datasets yet.
            </p>
            <p className="text-xs text-muted-foreground">
              Create a Generator (Pipeline) to produce durable datasets, or promote a ResultSet.
            </p>
          </div>
        ) : (
          <div className="divide-y">
            {datasets.map((ds) => (
              <button
                key={ds.id}
                onClick={() => onSelect("dataset", ds.id)}
                className="w-full text-left py-3 px-2 hover:bg-muted/50 rounded transition-colors flex items-center justify-between"
              >
                <div>
                  <div className="font-medium text-sm">{ds.name || "Untitled"}</div>
                  <div className="text-xs text-muted-foreground">
                    {ds.row_count?.toLocaleString() || 0} rows • {ds.schema_json?.length || 0} cols
                  </div>
                </div>
                <span className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">Dataset</span>
              </button>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}

function GeneratorsWorkspace({
  generators,
  stats,
  onSelect,
}: {
  generators: any[];
  stats: any;
  onSelect: (type: string, id?: string) => void;
}) {
  return (
    <div className="space-y-4">
      <GlassPanel className="p-4 grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard label="Generators" value={stats.generators.toString()} helper="Total" icon={Workflow} accent="bg-emerald-100 text-emerald-600" />
        <StatCard label="Active" value={generators.filter((g) => g.is_active).length.toString()} helper="Enabled" icon={PlayCircle} accent="bg-green-100 text-green-600" />
        <StatCard label="Scripts" value={stats.scripts.toString()} helper="Available" icon={Code2} accent="bg-amber-100 text-amber-600" />
      </GlassPanel>

      <GlassPanel className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">All Generators</h3>
          <button
            onClick={() => onSelect("generator")}
            className="text-sm text-primary flex items-center gap-1 hover:gap-2 transition-all"
          >
            New Generator <ArrowRight className="h-3 w-3" />
          </button>
        </div>
        {generators.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No generators yet. Create one to build durable datasets.
          </p>
        ) : (
          <div className="divide-y">
            {generators.map((g) => (
              <button
                key={g.id}
                onClick={() => onSelect("generator", g.id)}
                className="w-full text-left py-3 px-2 hover:bg-muted/50 rounded transition-colors flex items-center justify-between"
              >
                <div>
                  <div className="font-medium text-sm">{g.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {g.steps_json?.length || 0} steps • {g.params_json?.length || 0} params
                  </div>
                </div>
                <span className={`text-xs px-2 py-1 rounded ${g.is_active ? "bg-green-100 text-green-700" : "bg-muted"}`}>
                  {g.is_active ? "Active" : "Inactive"}
                </span>
              </button>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}

function ComponentsWorkspace({
  stats,
  onOpenComponent,
}: {
  stats: any;
  onOpenComponent: (view: ComponentView) => void;
}) {
  const componentTypes = [
    {
      id: "scripts" as ComponentView,
      label: "Scripts",
      description: "Python scripts for automation logic with approval workflow",
      icon: Code2,
      count: stats.scripts,
      bgClass: "bg-amber-50",
      iconClass: "text-amber-600",
    },
    {
      id: "resultsets" as ComponentView,
      label: "Result Sets",
      description: "Intermediate outputs from scripts/imports - use as script inputs",
      icon: Table2,
      count: stats.resultsets,
      bgClass: "bg-slate-50",
      iconClass: "text-slate-600",
    },
    {
      id: "import-processes" as ComponentView,
      label: "Import Processes",
      description: "Define how files are inspected, normalized, and mapped",
      icon: FileCode2,
      count: stats.importProcesses,
      bgClass: "bg-violet-50",
      iconClass: "text-violet-600",
    },
    {
      id: "custom-tables" as ComponentView,
      label: "Custom Tables",
      description: "Authoritative tables with explicit schema (coming soon)",
      icon: Database,
      count: 0,
      bgClass: "bg-slate-50",
      iconClass: "text-slate-600",
      disabled: true,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4">
        {componentTypes.map((type) => (
          <ComponentTypeCard
            key={type.id}
            type={type}
            onManage={() => type.id && !type.disabled && onOpenComponent(type.id)}
          />
        ))}
      </div>
    </div>
  );
}

function ComponentTypeCard({
  type,
  onManage,
}: {
  type: {
    id: ComponentView;
    label: string;
    description: string;
    icon: any;
    count: number;
    bgClass: string;
    iconClass: string;
    disabled?: boolean;
  };
  onManage?: () => void;
}) {
  const Icon = type.icon;

  return (
    <GlassPanel
      className={`p-6 space-y-4 ${type.disabled ? "opacity-60" : "hover-elevate cursor-pointer"}`}
      onClick={!type.disabled ? onManage : undefined}
    >
      <div className="flex items-start justify-between gap-4">
        <div
          className={`w-12 h-12 rounded-lg ${type.bgClass} flex items-center justify-center shrink-0`}
        >
          <Icon className={`h-6 w-6 ${type.iconClass}`} />
        </div>
        {type.count > 0 && (
          <span className="text-xs px-2 py-1 rounded-full border bg-background">
            {type.count}
          </span>
        )}
      </div>

      <div className="space-y-1">
        <h3 className="font-semibold">{type.label}</h3>
        <p className="text-sm text-muted-foreground line-clamp-2">{type.description}</p>
      </div>

      <div className="flex justify-end">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onManage?.();
          }}
          disabled={type.disabled}
          className={`text-sm px-3 py-1.5 rounded-md border transition-colors ${
            type.disabled
              ? "text-muted-foreground cursor-not-allowed"
              : "hover:bg-muted"
          }`}
        >
          Manage
        </button>
      </div>
    </GlassPanel>
  );
}

function ComponentPlaceholder({ componentView }: { componentView: ComponentView }) {
  const config: Record<string, { icon: any; label: string }> = {
    scripts: { icon: Code2, label: "script" },
    resultsets: { icon: Layers, label: "result set" },
    "import-processes": { icon: FileCode2, label: "import process" },
    "custom-tables": { icon: Database, label: "custom table" },
  };

  const { icon: Icon, label } = config[componentView || "scripts"] || config.scripts;

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-muted mb-4">
          <Icon className="h-8 w-8 text-muted-foreground" />
        </div>
        <p className="text-sm text-muted-foreground">Select a {label} to view details</p>
      </div>
    </div>
  );
}

function RunsWorkspace({ runs, stats }: { runs: any[]; stats: any }) {
  return (
    <div className="space-y-4">
      <GlassPanel className="p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Runs" value={stats.runs.toString()} helper="All time" icon={PlayCircle} accent="bg-indigo-100 text-indigo-600" />
        <StatCard label="Success" value={runs.filter((r) => r.status === "success").length.toString()} helper="Completed" icon={PlayCircle} accent="bg-green-100 text-green-600" />
        <StatCard label="Failed" value={runs.filter((r) => r.status === "failed").length.toString()} helper="Errors" icon={PlayCircle} accent="bg-red-100 text-red-600" />
        <StatCard label="Pending" value={runs.filter((r) => r.status === "pending" || r.status === "running").length.toString()} helper="In progress" icon={PlayCircle} accent="bg-amber-100 text-amber-600" />
      </GlassPanel>

      <GlassPanel className="p-4">
        <h3 className="font-semibold mb-4">Recent Runs</h3>
        {runs.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">No runs yet.</p>
        ) : (
          <div className="divide-y">
            {runs.map((r) => (
              <div key={r.id} className="py-3 px-2 flex items-center justify-between">
                <div>
                  <div className="font-medium text-sm">{r.import_process_name || r.import_process?.slice(0, 8)}</div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(r.started_at).toLocaleString()}
                  </div>
                </div>
                <span
                  className={`text-xs px-2 py-1 rounded capitalize ${
                    r.status === "success"
                      ? "bg-green-100 text-green-700"
                      : r.status === "failed"
                      ? "bg-red-100 text-red-700"
                      : "bg-amber-100 text-amber-700"
                  }`}
                >
                  {r.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </GlassPanel>
    </div>
  );
}
