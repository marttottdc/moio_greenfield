import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/hooks/use-toast";
import {
  useDataLabFiles,
  useDataLabImportPreview,
  useDataLabImportExecute,
  useDataLabPipelines,
  useDataLabScripts,
  useDataLabPipelineCreate,
} from "@/hooks/use-datalab";
import { analyzeCSVFile, analyzeExcelFile } from "@/lib/fileAnalyzer";
import type { ImportContract, Pipeline } from "@/lib/moio-types";
import { Loader2, Plus, ArrowRight } from "lucide-react";

type Stage = "source" | "import" | "transform" | "output";

export function GeneratorEditor({
  id,
  onSelect,
}: {
  id?: string;
  onSelect: (view: "dataset" | "generator" | "script" | "welcome", id?: string) => void;
}) {
  const { toast } = useToast();
  const { data: files } = useDataLabFiles(1, 20);
  const { data: pipelines } = useDataLabPipelines();
  const { data: scripts } = useDataLabScripts();
  const previewMutation = useDataLabImportPreview();
  const executeMutation = useDataLabImportExecute();
  const createPipelineMutation = useDataLabPipelineCreate();

  const [stage, setStage] = useState<Stage>("source");
  const [fileId, setFileId] = useState<string | undefined>();
  const [fileObj, setFileObj] = useState<File | null>(null);
  const [detected, setDetected] = useState<any>(null);
  const [fileType, setFileType] = useState<"csv" | "excel" | "pdf">("csv");
  const [mapping, setMapping] = useState<any[]>([]);
  const [datasetName, setDatasetName] = useState("");
  const [outputMode, setOutputMode] = useState<"create" | "update">("create");
  const [targetDatasetId, setTargetDatasetId] = useState<string | undefined>();
  const [selectedScripts, setSelectedScripts] = useState<string[]>([]);
  const [newGeneratorName, setNewGeneratorName] = useState("");

  const pipeline: Pipeline | undefined = useMemo(
    () => (pipelines || []).find((p) => p.id === id),
    [pipelines, id]
  );

  useEffect(() => {
    if (pipeline) {
      // seed with pipeline data when available
      setDatasetName(pipeline.name);
    }
  }, [pipeline]);

  const handleCreateGenerator = () => {
    const name = (newGeneratorName || "").trim();
    if (!name) {
      toast({ variant: "destructive", description: "Generator name is required." });
      return;
    }
    createPipelineMutation.mutate(
      { name, description: "Dataset generator", steps_json: [], params_json: [] },
      {
        onSuccess: (p) => {
          toast({ description: "Generator created" });
          onSelect("generator", p.id);
        },
        onError: (err: any) => {
          toast({
            variant: "destructive",
            description: err?.message || "Failed to create generator",
          });
        },
      }
    );
  };

  const handleLocalAnalyze = async (file: File) => {
    const ext = file.name.toLowerCase();
    try {
      if (ext.endsWith(".csv")) {
        const analysis = await analyzeCSVFile(file);
        setDetected(analysis);
        setFileType("csv");
        setMapping(
          (analysis.detected_schema || []).map((col) => ({
            source: col.name,
            target: col.name,
            type: col.type,
          }))
        );
      } else if (ext.endsWith(".xlsx") || ext.endsWith(".xls")) {
        const analysis = await analyzeExcelFile(file);
        setDetected(analysis);
        setFileType("excel");
        setMapping(
          (analysis.detected_schema || []).map((col) => ({
            source: col.name,
            target: col.name,
            type: col.type,
          }))
        );
      } else {
        setFileType("pdf");
      }
      if (!datasetName) {
        setDatasetName(`Generator ${file.name.replace(/\.[^/.]+$/, "")}`);
      }
      setStage("import");
    } catch (err) {
      toast({
        variant: "destructive",
        description: err instanceof Error ? err.message : "Failed to analyze file",
      });
    }
  };

  const buildContract = (): ImportContract => ({
    version: "1",
    parser: {
      type: fileType,
      delimiter: detected?.delimiter,
      header_row: detected?.detected_header_row ?? detected?.header_row ?? 0,
      skip_rows: detected?.suggested_skip_rows ?? detected?.skip_rows ?? 0,
      sheet: detected?.detected_sheets?.[0]?.name,
    },
    mapping: mapping.length ? mapping : [],
    output: {
      name: datasetName || "Generated Dataset",
    },
  });

  const handlePreview = async () => {
    if (!fileId) {
      toast({ variant: "destructive", description: "Select or upload a file first." });
      return;
    }
    const contract = buildContract();
    await previewMutation.mutateAsync(
      { source: { file_id: fileId }, contract },
      {
        onSuccess: (data) => {
          setDetected((prev: any) => ({
            ...(prev || {}),
            detected_schema: data.detected_schema,
            sample_rows: data.sample_rows,
            row_count: data.row_count,
          }));
          setStage("transform");
        },
        onError: (err: any) => {
          toast({
            variant: "destructive",
            description: err?.message || "Preview failed",
          });
        },
      }
    );
  };

  const handleCreate = async () => {
    if (!fileId) {
      toast({ variant: "destructive", description: "Select or upload a file first." });
      return;
    }
    const contract = buildContract();
    await executeMutation.mutateAsync(
      { source: { file_id: fileId }, contract },
      {
        onSuccess: (res) => {
          toast({ description: "Dataset generated" });
          onSelect("dataset", res.resultset_id);
        },
        onError: (err: any) => {
          toast({
            variant: "destructive",
            description: err?.message || "Failed to generate dataset",
          });
        },
      }
    );
  };

  return (
    <div className="h-full overflow-auto p-6 space-y-4">
      {!id ? (
        <>
          <div>
            <h2 className="text-2xl font-semibold">New Generator</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Create a dataset generator (a Pipeline) and then configure source, import, transforms, and output.
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Create generator</CardTitle>
              <CardDescription>This will create a new Pipeline that you can edit as a generator.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Label>Name</Label>
              <Input
                value={newGeneratorName}
                onChange={(e) => setNewGeneratorName(e.target.value)}
                placeholder="e.g. Monthly Sales Import"
              />
              <Button onClick={handleCreateGenerator} disabled={createPipelineMutation.isPending}>
                {createPipelineMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Plus className="h-4 w-4 mr-2" />
                )}
                Create generator
              </Button>
            </CardContent>
          </Card>
        </>
      ) : (
        <>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">{datasetName || "New Generator"}</h2>
          <p className="text-sm text-muted-foreground">
            Define source, import config, transformation steps, and output behavior.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={handlePreview} disabled={previewMutation.isPending}>
            {previewMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1" />
            ) : (
              <ArrowRight className="h-4 w-4 mr-1" />
            )}
            Preview
          </Button>
          <Button onClick={handleCreate} disabled={executeMutation.isPending}>
            {executeMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1" />
            ) : (
              <ArrowRight className="h-4 w-4 mr-1" />
            )}
            Run & Create
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Source</CardTitle>
            <CardDescription>Select a reference file and analyze shape</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Select value={fileId} onValueChange={(v) => setFileId(v)}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a file" />
              </SelectTrigger>
              <SelectContent>
                {(files?.results ?? []).map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.filename}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              type="file"
              accept=".csv,.xlsx,.xls,.pdf"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  setFileObj(file);
                  handleLocalAnalyze(file);
                }
              }}
            />
            {fileObj && (
              <div className="text-xs text-muted-foreground">
                Selected: {fileObj.name} ({fileObj.size} bytes)
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Import Config</CardTitle>
            <CardDescription>Parser + mapping</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Label>File Type</Label>
            <Select value={fileType} onValueChange={(v) => setFileType(v as any)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="csv">CSV</SelectItem>
                <SelectItem value="excel">Excel</SelectItem>
                <SelectItem value="pdf">PDF</SelectItem>
              </SelectContent>
            </Select>
            <Label>Dataset Name</Label>
            <Input value={datasetName} onChange={(e) => setDatasetName(e.target.value)} />
            <div className="text-xs text-muted-foreground">
              Detected columns: {detected?.detected_schema?.length ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Transform (Pipeline)</CardTitle>
          <CardDescription>Add script steps</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <ScrollArea className="h-40 rounded border border-border p-2">
            <div className="space-y-2">
              {selectedScripts.map((sid, idx) => (
                <div
                  key={`${sid}-${idx}`}
                  className="flex items-center justify-between rounded border border-border px-2 py-1 text-sm"
                >
                  <span>{scripts?.find((s) => s.id === sid)?.name || sid}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setSelectedScripts((prev) => prev.filter((_, i) => i !== idx))}
                  >
                    Remove
                  </Button>
                </div>
              ))}
              {selectedScripts.length === 0 && (
                <div className="text-xs text-muted-foreground">No steps added.</div>
              )}
            </div>
          </ScrollArea>
          <Select
            onValueChange={(sid) => setSelectedScripts((prev) => [...prev, sid])}
            value=""
          >
            <SelectTrigger>
              <SelectValue placeholder="Add script step" />
            </SelectTrigger>
            <SelectContent>
              {(scripts || []).map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Output</CardTitle>
          <CardDescription>Configure how the dataset is produced</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Label>Mode</Label>
          <Select value={outputMode} onValueChange={(v) => setOutputMode(v as "create" | "update")}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="create">Create new dataset each run</SelectItem>
              <SelectItem value="update">Update existing dataset</SelectItem>
            </SelectContent>
          </Select>
          {outputMode === "update" && (
            <>
              <Label>Target Dataset ID</Label>
              <Input value={targetDatasetId || ""} onChange={(e) => setTargetDatasetId(e.target.value)} />
              <div className="text-xs text-muted-foreground">
                Backend should return the dataset id; use merge keys in contract if needed.
              </div>
            </>
          )}
        </CardContent>
      </Card>
        </>
      )}
    </div>
  );
}
