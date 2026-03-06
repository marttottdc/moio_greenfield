import { useEffect, useMemo, useState } from "react";
import { useLocation, Link } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import {
  useDataLabFiles,
  useDataLabImportProcessCreate,
  useDataLabProcessShapeInspect,
} from "@/hooks/use-datalab";
import { Loader2, ArrowRight, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

type Step = "select" | "inspect" | "confirm";

export default function NewImportProcess() {
  const [location, setLocation] = useLocation();
  const { toast } = useToast();
  const [fileId, setFileId] = useState<string | undefined>();
  const [fileType, setFileType] = useState<"csv" | "excel" | "pdf">("csv");
  const [name, setName] = useState<string>("");
  const [step, setStep] = useState<Step>("select");

  const { data: files, isLoading: filesLoading } = useDataLabFiles(1, 50);
  const inspectMutation = useDataLabProcessShapeInspect();
  const createMutation = useDataLabImportProcessCreate();

  const selectedFile = useMemo(
    () => files?.results.find((f) => f.id === fileId),
    [files, fileId]
  );

  useEffect(() => {
    if (selectedFile && !name) {
      const base = selectedFile.filename.replace(/\.[^/.]+$/, "");
      setName(`${base} process`);
    }
  }, [selectedFile, name]);

  const handleInspect = () => {
    if (!fileId || !fileType) {
      toast({ variant: "destructive", description: "Select a file and type first." });
      return;
    }
    setStep("inspect");
    inspectMutation.mutate(
      { file_id: fileId, file_type: fileType },
      {
        onError: (err: any) => {
          toast({
            variant: "destructive",
            description: err?.message || "Shape inspection failed",
          });
        },
      }
    );
  };

  const handleCreate = () => {
    if (!fileId || !fileType || !name.trim()) {
      toast({ variant: "destructive", description: "Name, file, and type are required." });
      return;
    }
    createMutation.mutate(
      { name: name.trim(), file_type: fileType, file_id: fileId },
      {
        onSuccess: (process) => {
          toast({ description: "Import process created" });
          setLocation(`/datalab/processes/imports/${process.id}`);
        },
        onError: (err: any) => {
          toast({
            variant: "destructive",
            description: err?.message || "Failed to create process",
          });
        },
      }
    );
  };

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">New Import Process</h1>
            <p className="text-muted-foreground mt-2">
              Inspect a file shape, define a reusable process, and run it on matching files.
            </p>
          </div>
          <Link href="/datalab/processes/imports">
            <Button variant="ghost">Back to processes</Button>
          </Link>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Steps</CardTitle>
            <CardDescription>Inspect shape → confirm → create reusable process</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 md:grid-cols-3">
              <StepBadge active={step === "select"} label="Select source file" />
              <StepBadge active={step === "inspect"} label="Inspect shape" />
              <StepBadge active={step === "confirm"} label="Confirm & save" />
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="file">File</Label>
                  {filesLoading ? (
                    <div className="flex items-center text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading files...
                    </div>
                  ) : (
                    <Select value={fileId} onValueChange={setFileId}>
                      <SelectTrigger>
                        <SelectValue placeholder="Choose a file to inspect" />
                      </SelectTrigger>
                      <SelectContent>
                        {(files?.results ?? []).map((f) => (
                          <SelectItem key={f.id} value={f.id}>
                            {f.filename}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>

                <div className="space-y-2">
                  <Label>File type</Label>
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
                </div>

                <div className="space-y-2">
                  <Label htmlFor="name">Process name</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Monthly Sales PDF"
                  />
                </div>

                <div className="flex gap-2">
                  <Button onClick={handleInspect} disabled={inspectMutation.isPending || !fileId}>
                    {inspectMutation.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <ArrowRight className="mr-2 h-4 w-4" />
                    )}
                    Inspect shape
                  </Button>
                  {inspectMutation.data && (
                    <Button
                      variant="secondary"
                      onClick={() => setStep("confirm")}
                      disabled={!inspectMutation.data}
                    >
                      Continue
                    </Button>
                  )}
                </div>
              </div>

              <div className="rounded border border-border p-4 bg-muted/30 space-y-3 min-h-[200px]">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  Shape preview
                  {inspectMutation.data && (
                    <Badge variant="outline">Fingerprint {inspectMutation.data.fingerprint}</Badge>
                  )}
                </h3>
                {inspectMutation.isPending && (
                  <div className="flex items-center text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin mr-2" /> Inspecting...
                  </div>
                )}
                {inspectMutation.data ? (
                  <ShapeSummary description={inspectMutation.data.description} fileType={fileType} />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Run inspection to view detected structure, sheets, or tables.
                  </p>
                )}
              </div>
            </div>

            {inspectMutation.data && (
              <div className="flex justify-end">
                <Button
                  onClick={handleCreate}
                  disabled={createMutation.isPending}
                  variant="default"
                >
                  {createMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle2 className="mr-2 h-4 w-4" />
                  )}
                  Save process
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </DataLabWorkspace>
  );
}

function StepBadge({ active, label }: { active: boolean; label: string }) {
  return (
    <div
      className={`rounded border px-3 py-2 text-sm ${
        active ? "border-primary bg-primary/5 text-primary" : "border-border text-muted-foreground"
      }`}
    >
      {label}
    </div>
  );
}

function ShapeSummary({
  description,
  fileType,
}: {
  description: any;
  fileType: "csv" | "excel" | "pdf";
}) {
  if (!description) {
    return <p className="text-sm text-muted-foreground">No description returned.</p>;
  }

  if (fileType === "csv" || fileType === "excel") {
    return (
      <div className="text-sm text-muted-foreground space-y-1">
        {description.columns && (
          <p>
            Columns ({description.column_count ?? description.columns.length}):{" "}
            <span className="font-mono text-xs">{description.columns.join(", ")}</span>
          </p>
        )}
        {description.sheets && <p>Sheets: {description.sheets.join(", ")}</p>}
      </div>
    );
  }

  if (fileType === "pdf") {
    return (
      <div className="text-sm text-muted-foreground space-y-1">
        {description.page_patterns && (
          <p>
            Page patterns header {description.page_patterns.header?.length ?? 0}, detail{" "}
            {description.page_patterns.detail?.length ?? 0}, footer{" "}
            {description.page_patterns.footer?.length ?? 0} (pages {description.page_patterns.page_count})
          </p>
        )}
        {description.tables && description.tables.length > 0 && (
          <ul className="list-disc list-inside text-xs font-mono">
            {description.tables.map((t: any, idx: number) => (
              <li key={idx}>
                Page {t.page}: {t.column_count} cols ({(t.columns || []).join(", ")}) rows≈
                {t.row_count_estimate}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return <p className="text-sm text-muted-foreground">{JSON.stringify(description)}</p>;
}
