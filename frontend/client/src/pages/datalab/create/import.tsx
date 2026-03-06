import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "wouter";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import {
  useDataLabFiles,
  useDataLabFileUpload,
  useDataLabImportPreview,
  useDataLabImportExecute,
} from "@/hooks/use-datalab";
import { analyzeCSVFile, analyzeExcelFile } from "@/lib/fileAnalyzer";
import { dataLabApi } from "@/lib/api";
import { Loader2, Upload, ArrowRight, CheckCircle2 } from "lucide-react";
import type { ImportContract } from "@/lib/moio-types";

type Step = "source" | "configure" | "preview" | "finish";

export default function CreateImportDataset() {
  const { toast } = useToast();
  const [location, setLocation] = useLocation();
  const [step, setStep] = useState<Step>("source");
  const [fileId, setFileId] = useState<string | undefined>();
  const [selectedFileObj, setSelectedFileObj] = useState<File | null>(null);
  const [fileType, setFileType] = useState<"csv" | "excel" | "pdf">("csv");
  const [detected, setDetected] = useState<any>(null);
  const [datasetName, setDatasetName] = useState("");
  const [mapping, setMapping] = useState<any[]>([]);

  const { data: files } = useDataLabFiles(1, 20);
  const uploadMutation = useDataLabFileUpload();
  const previewMutation = useDataLabImportPreview();
  const executeMutation = useDataLabImportExecute();

  const selectedFileMeta = useMemo(
    () => files?.results.find((f) => f.id === fileId),
    [files, fileId]
  );

  useEffect(() => {
    if (selectedFileMeta && !datasetName) {
      const base = selectedFileMeta.filename.replace(/\.[^/.]+$/, "");
      setDatasetName(`Import ${base}`);
    }
  }, [selectedFileMeta, datasetName]);

  const handleLocalAnalyze = async (file: File) => {
    const ext = file.name.toLowerCase();
    try {
      if (ext.endsWith(".csv")) {
        const analysis = await analyzeCSVFile(file);
        setDetected(analysis);
        setFileType("csv");
        if (!datasetName) setDatasetName(`Import ${file.name.replace(/\.[^/.]+$/, "")}`);
        setMapping(
          (analysis.detected_schema || []).map((col) => ({
            source: col.name,
            target: col.name,
            type: col.type,
          }))
        );
        setStep("configure");
      } else if (ext.endsWith(".xlsx") || ext.endsWith(".xls")) {
        const analysis = await analyzeExcelFile(file);
        setDetected(analysis);
        setFileType("excel");
        if (!datasetName) setDatasetName(`Import ${file.name.replace(/\.[^/.]+$/, "")}`);
        setMapping(
          (analysis.detected_schema || []).map((col) => ({
            source: col.name,
            target: col.name,
            type: col.type,
          }))
        );
        setStep("configure");
      } else {
        setFileType("pdf");
        setStep("configure");
      }
    } catch (err) {
      toast({
        variant: "destructive",
        description: err instanceof Error ? err.message : "Failed to analyze file",
      });
    }
  };

  const handleUpload = async (file: File) => {
    const uploaded = await uploadMutation.mutateAsync({ file });
    setFileId(uploaded.id);
    await handleLocalAnalyze(file);
  };

  const buildContract = (): ImportContract => {
    const parserCommon = {
      header_row: detected?.header_row ?? 0,
      skip_rows: detected?.skip_rows ?? 0,
      delimiter: detected?.delimiter,
      sheet: detected?.sheets?.[0],
    };
    return {
      version: "1",
      parser: {
        type: fileType,
        delimiter: parserCommon.delimiter,
        header_row: parserCommon.header_row,
        skip_rows: parserCommon.skip_rows,
        sheet: parserCommon.sheet,
      },
      mapping: mapping.length
        ? mapping
        : (detected?.detected_schema || []).map((col: any) => ({
            source: col.name,
            target: col.name,
            type: col.type === "number" ? "decimal" : col.type === "date" ? "date" : "string",
          })),
      output: {
        name: datasetName || "New Dataset",
      },
    };
  };

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
          setStep("preview");
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
          toast({ description: "Dataset created" });
          setLocation(`/datalab/dataset/${res.resultset_id}`);
        },
        onError: (err: any) => {
          toast({
            variant: "destructive",
            description: err?.message || "Create dataset failed",
          });
        },
      }
    );
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Create Dataset from File</h1>
          <p className="text-muted-foreground mt-2">
            Upload or pick an existing file, configure parsing, and create a dataset.
          </p>
        </div>
        <Link href="/datalab">
          <Button variant="ghost">Back to datasets</Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Step 1: Source</CardTitle>
          <CardDescription>Upload a new file or select an existing one.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4 items-center">
            <div>
              <Input
                type="file"
                accept=".csv,.xlsx,.xls,.pdf"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    setSelectedFileObj(file);
                    handleUpload(file);
                  }
                }}
              />
            </div>
            <div className="text-sm text-muted-foreground">or select existing:</div>
            <Select value={fileId} onValueChange={(v) => setFileId(v)}>
              <SelectTrigger className="w-64">
                <SelectValue placeholder="Choose existing file" />
              </SelectTrigger>
              <SelectContent>
                {(files?.results ?? []).map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.filename}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {selectedFileObj && (
            <div className="text-xs text-muted-foreground">
              Selected: {selectedFileObj.name} ({selectedFileObj.size} bytes)
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Step 2: Configure</CardTitle>
          <CardDescription>Adjust parsing settings (auto-detected when possible).</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
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
          </div>
          <div className="space-y-2">
            <Label>Dataset Name</Label>
            <Input value={datasetName} onChange={(e) => setDatasetName(e.target.value)} />
          </div>
          {fileType === "csv" && (
            <div className="space-y-2">
              <Label>Delimiter</Label>
              <Input
                value={detected?.delimiter || ""}
                onChange={(e) =>
                  setDetected((prev: any) => ({ ...(prev || {}), delimiter: e.target.value }))
                }
              />
            </div>
          )}
          {fileType !== "pdf" && (
            <>
              <div className="space-y-2">
                <Label>Header Row</Label>
                <Input
                  type="number"
                  value={detected?.header_row ?? 0}
                  onChange={(e) =>
                    setDetected((prev: any) => ({ ...(prev || {}), header_row: Number(e.target.value) }))
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>Skip Rows</Label>
                <Input
                  type="number"
                  value={detected?.skip_rows ?? 0}
                  onChange={(e) =>
                    setDetected((prev: any) => ({ ...(prev || {}), skip_rows: Number(e.target.value) }))
                  }
                />
              </div>
            </>
          )}
          {fileType === "excel" && (
            <div className="space-y-2">
              <Label>Sheet</Label>
              <Input
                value={detected?.sheets?.[0] || ""}
                onChange={(e) =>
                  setDetected((prev: any) => ({ ...(prev || {}), sheets: [e.target.value] }))
                }
              />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Step 3: Preview</CardTitle>
          <CardDescription>Run a preview to validate schema.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button onClick={handlePreview} disabled={previewMutation.isPending || !fileId}>
            {previewMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Previewing...
              </>
            ) : (
              <>
                <ArrowRight className="h-4 w-4 mr-2" />
                Run Preview
              </>
            )}
          </Button>
          {detected?.sample_rows && (
            <div className="text-sm text-muted-foreground">
              Preview rows: {detected.sample_rows.length} • columns: {detected.detected_schema?.length}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Step 4: Create</CardTitle>
          <CardDescription>Execute and create the dataset.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={handleCreate} disabled={executeMutation.isPending || !fileId}>
            {executeMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Creating...
              </>
            ) : (
              <>
                <CheckCircle2 className="h-4 w-4 mr-2" />
                Create Dataset
              </>
            )}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
