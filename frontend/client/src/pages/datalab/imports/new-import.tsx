import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useDataLabFiles,
  useDataLabFileUpload,
  useDataLabImportPreview,
  useDataLabImportExecute,
  useDataLabImportInspectShape,
} from "@/hooks/use-datalab";
import { Upload, Loader2, ChevronRight, ChevronLeft, CheckCircle2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import type { ImportContract, ColumnDefinition, DataLabFile } from "@/lib/moio-types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { analyzeLocalFile, generatePreliminaryMapping, FileAnalysisResult } from "@/lib/fileAnalyzer";
import { dataLabApi } from "@/lib/api";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";

type ImportStep = "file" | "configure" | "preview" | "mapping" | "execute";

export default function NewImport() {
  const [, setLocation] = useLocation();
  const [step, setStep] = useState<ImportStep>("file");
  const [selectedFile, setSelectedFile] = useState<DataLabFile | null>(null);
  const [contract, setContract] = useState<Partial<ImportContract>>({
    version: "1",
    parser: {
      type: "csv",
      header_row: 0,
      delimiter: ",",
      date_format: "YYYY-MM-DD",
      datetime_format: "YYYY-MM-DD HH:mm:ss",
    },
    mapping: [],
    output: {
      name: "",
    },
  });
  const [analyzingFile, setAnalyzingFile] = useState(false);
  const [fileAnalysis, setFileAnalysis] = useState<FileAnalysisResult | null>(null);
  const [previewData, setPreviewData] = useState<{
    detected_schema: ColumnDefinition[];
    sample_rows: Record<string, any>[];
    row_count: number;
    warnings: string[];
  } | null>(null);

  const { data: files, isLoading: filesLoading } = useDataLabFiles(1, 50);
  const uploadMutation = useDataLabFileUpload();
  const previewMutation = useDataLabImportPreview();
  const executeMutation = useDataLabImportExecute();
  const inspectMutation = useDataLabImportInspectShape();
  const { toast } = useToast();
  const [shapeInspection, setShapeInspection] = useState<any | null>(null);

  // Pre-select file if file_id is in query params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const fileId = params.get("file_id");
    if (fileId && files?.results) {
      const file = files.results.find((f) => f.id === fileId);
      if (file) {
        setSelectedFile(file);
      }
    }
  }, [files]);

  // When selecting an existing file (from list or query param), fetch from backend and analyze
  useEffect(() => {
    if (selectedFile && !fileAnalysis && !analyzingFile) {
      analyzeExistingFileById(selectedFile.id, selectedFile.filename, selectedFile.content_type);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFile?.id]);

  const runLocalAnalysis = async (file: File) => {
    try {
      setAnalyzingFile(true);
      const analysis = await analyzeLocalFile(file);
      setFileAnalysis(analysis);

      // Auto-update contract with detected values and preliminary mapping
      const mapping = generatePreliminaryMapping(analysis.detected_schema);
      const fileType = file.name.toLowerCase().endsWith(".csv") ? "csv" : "excel";

      setContract((prev) => ({
        ...prev,
        parser: {
          ...prev.parser!,
          type: fileType,
          header_row: analysis.detected_header_row ?? prev.parser?.header_row ?? 0,
          skip_rows: analysis.suggested_skip_rows ?? prev.parser?.skip_rows ?? 0,
          ...(fileType === "csv" && { delimiter: analysis.detected_delimiter || "," }),
          ...(fileType === "excel" &&
            analysis.detected_sheets &&
            analysis.detected_sheets.length > 0 && { sheet: analysis.detected_sheets[0].name }),
        },
        mapping,
        output: {
          name: prev.output?.name || file.name.replace(/\.[^/.]+$/, ""),
        },
      }));

      // Move to configure step to show detected info
      setStep("configure");
    } catch (error) {
      console.error("File analysis error:", error);
      toast({
        title: "Analysis failed",
        description: error instanceof Error ? error.message : "Failed to analyze file. You can still configure manually.",
        variant: "destructive",
      });
      setFileAnalysis(null);
    } finally {
      setAnalyzingFile(false);
    }
  };

  const analyzeExistingFileById = async (fileId: string, filename: string, contentType?: string) => {
    try {
      setAnalyzingFile(true);
      const blob = await dataLabApi.getFileContent(fileId);
      const file = new File([blob], filename, { type: contentType || blob.type || "application/octet-stream" });
      await runLocalAnalysis(file);
    } catch (error) {
      console.error("File download/analysis error:", error);
      toast({
        title: "Analysis failed",
        description: error instanceof Error ? error.message : "Failed to download or analyze file. Configure manually or re-upload.",
        variant: "destructive",
      });
    } finally {
      setAnalyzingFile(false);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Clear previous analysis while uploading
    setFileAnalysis(null);

    try {
      setAnalyzingFile(true);
      const uploaded = await uploadMutation.mutateAsync({ file });
      setSelectedFile(uploaded);
      toast({
        title: "File uploaded",
        description: `${file.name} has been uploaded successfully.`,
      });
      event.target.value = "";

       // After successful upload, analyze locally to generate mapping/config
      await runLocalAnalysis(file);
    } catch (error) {
      toast({
        title: "Upload failed",
        description: error instanceof Error ? error.message : "Failed to upload file",
        variant: "destructive",
      });
    } finally {
      setAnalyzingFile(false);
    }
  };
  const handleInspectShape = async () => {
    if (!selectedFile) return;
    try {
      setAnalyzingFile(true);
      const result = await inspectMutation.mutateAsync(selectedFile.id);
      setShapeInspection(result);
      toast({ title: "PDF shape inspected", description: result.fingerprint ? "Fingerprint detected" : undefined });
    } catch (err) {
      toast({
        title: "Shape inspection failed",
        description: err instanceof Error ? err.message : "Failed to inspect PDF shape",
        variant: "destructive",
      });
    } finally {
      setAnalyzingFile(false);
    }
  };


  const handlePreview = async () => {
    if (!selectedFile || !contract.parser) return;

    // Ensure we have mapping; if not, attempt to build from fileAnalysis
    let mappingToUse = contract.mapping || [];
    if ((!mappingToUse || mappingToUse.length === 0) && fileAnalysis) {
      mappingToUse = generatePreliminaryMapping(fileAnalysis.detected_schema);
      setContract((prev) => ({ ...prev, mapping: mappingToUse }));
    }

    if (!mappingToUse || mappingToUse.length === 0) {
      toast({
        title: "Preview failed",
        description: "Mapping is required. Please analyze the file first or add mapping manually.",
        variant: "destructive",
      });
      return;
    }

    // Preflight: ensure the file is downloadable from backend (avoid S3 NoSuchKey)
    try {
      await dataLabApi.getFileContent(selectedFile.id);
    } catch (err) {
      toast({
        title: "Preview failed",
        description: "No se pudo acceder al archivo en el backend (S3). Reintenta o vuelve a subir el archivo.",
        variant: "destructive",
      });
      return;
    }

    // Compose the full contract with configured parser settings
    const fileType = contract.parser.type;
    const fullContract: ImportContract = {
      version: "1",
      parser: {
        type: fileType,
        header_row: contract.parser.header_row ?? 0,
        ...(fileType === "csv" && contract.parser.delimiter && { delimiter: contract.parser.delimiter }),
        ...(fileType === "excel" && contract.parser.sheet !== undefined && { sheet: contract.parser.sheet }),
      },
      mapping: mappingToUse as any,
      output: {
        name: contract.output?.name || selectedFile.filename.replace(/\.[^/.]+$/, ""),
      },
    };

    console.log("Composed import contract for preview:", JSON.stringify(fullContract, null, 2));

    try {
      const preview = await previewMutation.mutateAsync({
        source: { file_id: selectedFile.id },
        contract: fullContract,
      });
      setPreviewData(preview);
      setStep("preview");
    } catch (error) {
      console.error("Preview error:", error);
      toast({
        title: "Preview failed",
        description: error instanceof Error ? error.message : "Failed to preview import",
        variant: "destructive",
      });
    }
  };

  const handleExecute = async () => {
    if (!selectedFile || !contract.parser || !contract.mapping) return;

    try {
      const result = await executeMutation.mutateAsync({
        source: { file_id: selectedFile.id },
        contract: contract as ImportContract,
        rebuild: false,
      });
      toast({
        title: "Import successful",
        description: `Imported ${result.row_count.toLocaleString()} rows successfully.`,
      });
      setLocation(`/datalab/resultsets/${result.resultset_id}`);
    } catch (error) {
      toast({
        title: "Import failed",
        description: error instanceof Error ? error.message : "Failed to execute import",
        variant: "destructive",
      });
    }
  };

  // Auto-generate mapping from detected schema
  const generateMapping = () => {
    if (!previewData) return;
    
    // Generate mapping from detected schema
    const mapping = previewData.detected_schema.map((col) => ({
      source: col.name,
      target: col.name.toLowerCase().replace(/\s+/g, "_"),
      type: col.type,
      clean: [] as string[],
    }));

    // Update contract with mapping and default output name if not set
    setContract((prev) => ({
      ...prev,
      mapping,
      output: {
        name: prev.output?.name || selectedFile?.filename.replace(/\.[^/.]+$/, "") || "import",
      },
    }));
    setStep("mapping");
  };

  return (
    <DataLabWorkspace>
      <div className="space-y-6 max-w-4xl">
        <div>
          <h1 className="text-3xl font-bold">New Import</h1>
          <p className="text-muted-foreground mt-2">
            Import data from CSV or Excel files
          </p>
        </div>

        {/* Progress Steps */}
        <div className="flex items-center justify-between mb-8">
          {(["file", "configure", "preview", "mapping", "execute"] as ImportStep[]).map((s, idx) => (
            <div key={s} className="flex items-center flex-1">
              <div className="flex flex-col items-center">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center ${
                    step === s
                      ? "bg-primary text-primary-foreground"
                      : idx < (["file", "configure", "preview", "mapping", "execute"] as ImportStep[]).indexOf(step)
                      ? "bg-primary/20 text-primary"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {idx < (["file", "configure", "preview", "mapping", "execute"] as ImportStep[]).indexOf(step) ? (
                    <CheckCircle2 className="h-5 w-5" />
                  ) : (
                    <span>{idx + 1}</span>
                  )}
                </div>
                <span className="text-xs mt-2 capitalize">{s}</span>
              </div>
              {idx < 3 && (
                <div
                  className={`flex-1 h-1 mx-2 ${
                    idx < (["file", "configure", "preview", "mapping", "execute"] as ImportStep[]).indexOf(step)
                      ? "bg-primary"
                      : "bg-muted"
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step 1: File Selection */}
        {step === "file" && (
          <Card>
            <CardHeader>
              <CardTitle>Select File</CardTitle>
              <CardDescription>Choose a file to import or upload a new one</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Upload New File</Label>
                <Input
                  type="file"
                  id="file-upload"
                  className="hidden"
                  accept=".csv,.xlsx,.xls"
                  onChange={handleFileUpload}
                  disabled={uploadMutation.isPending}
                />
                <Button
                  onClick={() => document.getElementById("file-upload")?.click()}
                  disabled={uploadMutation.isPending}
                  variant="outline"
                  className="w-full"
                >
                  {uploadMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="mr-2 h-4 w-4" />
                      Upload File
                    </>
                  )}
                </Button>
              </div>

              {files && files.results && files.results.length > 0 && (
                <div>
                  <Label>Or Select Existing File</Label>
                  <div className="mt-2 space-y-2 max-h-60 overflow-y-auto">
                    {files.results.map((file) => (
                      <div
                        key={file.id}
                        className={`p-3 border rounded-lg cursor-pointer hover:bg-muted ${
                          selectedFile?.id === file.id ? "border-primary bg-primary/5" : ""
                        }`}
                        onClick={() => setSelectedFile(file)}
                      >
                        <div className="font-medium">{file.filename}</div>
                        <div className="text-sm text-muted-foreground">
                          {file.content_type} • {(file.size / 1024).toFixed(2)} KB
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {selectedFile && (
                <div className="p-4 bg-muted rounded-lg">
                  <div className="font-medium">Selected: {selectedFile.filename}</div>
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => setLocation("/datalab/imports")}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => {
                    if (selectedFile) {
                      // For previously uploaded files we may not have local bytes; proceed to configure
                      if (!fileAnalysis && !analyzingFile) {
                        toast({
                          title: "Analysis unavailable",
                          description: "For existing files, configure parser settings manually or re-upload to analyze locally.",
                        });
                      }
                      setStep("configure");
                    }
                  }}
                  disabled={!selectedFile || analyzingFile}
                  className="ml-auto"
                >
                  {analyzingFile ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      Analyze File
                      <ChevronRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 2: Configure Parser */}
        {step === "configure" && selectedFile && (
          <Card>
            <CardHeader>
              <CardTitle>File Analysis & Configuration</CardTitle>
              <CardDescription>
                Detected file structure for: {selectedFile.filename}
              </CardDescription>
              {analyzingFile && (
                <div className="mt-3 inline-flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Analyzing file...
                </div>
              )}
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Show detected information */}
              {fileAnalysis && (
                <div className="p-4 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg space-y-2">
                  <div className="font-semibold text-blue-900 dark:text-blue-100">Detected File Structure</div>
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted-foreground">Total Rows:</span>{" "}
                      <span className="font-medium">{fileAnalysis.row_count.toLocaleString()}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Columns:</span>{" "}
                      <span className="font-medium">{fileAnalysis.detected_schema.length}</span>
                    </div>
                    {fileAnalysis.detected_delimiter && (
                      <div>
                        <span className="text-muted-foreground">Detected Delimiter:</span>{" "}
                        <span className="font-medium">"{fileAnalysis.detected_delimiter}"</span>
                      </div>
                    )}
                  </div>
                  <div className="mt-3">
                    <div className="text-xs font-medium text-muted-foreground mb-2">Detected Columns:</div>
                    <div className="flex flex-wrap gap-2">
                      {fileAnalysis.detected_schema.map((col, idx) => (
                        <div
                          key={idx}
                          className="px-2 py-1 bg-white dark:bg-gray-800 rounded text-xs border"
                        >
                          <span className="font-medium">{col.name}</span>{" "}
                          <span className="text-muted-foreground">({col.type})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* PDF shape inspection */}
              {contract.parser?.type === "pdf" && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <Label className="text-sm">PDF Shape</Label>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleInspectShape}
                      disabled={analyzingFile}
                    >
                      {analyzingFile ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Inspecting...
                        </>
                      ) : (
                        "Inspect shape"
                      )}
                    </Button>
                  </div>
                  {shapeInspection && (
                    <div className="rounded-lg border p-3 bg-muted/40 space-y-2 text-sm">
                      {shapeInspection.fingerprint && (
                        <div className="font-mono text-xs break-all">
                          Fingerprint: {shapeInspection.fingerprint}
                        </div>
                      )}
                      {shapeInspection.description?.page_patterns && (
                        <div>
                          <div className="font-semibold mb-1">Page Patterns</div>
                          <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                            <div>Header: {JSON.stringify(shapeInspection.description.page_patterns.header)}</div>
                            <div>Detail: {JSON.stringify(shapeInspection.description.page_patterns.detail)}</div>
                            <div>Footer: {JSON.stringify(shapeInspection.description.page_patterns.footer)}</div>
                            <div>Page count: {shapeInspection.description.page_patterns.page_count}</div>
                          </div>
                        </div>
                      )}
                      {shapeInspection.description?.tables && shapeInspection.description.tables.length > 0 && (
                        <div>
                          <div className="font-semibold mb-1">Detected Tables</div>
                          <div className="space-y-1 text-xs text-muted-foreground">
                            {shapeInspection.description.tables.map((t: any, idx: number) => (
                              <div key={idx} className="flex items-center gap-2">
                                <span className="font-medium">Page {t.page}</span>
                                <span>Cols: {t.column_count}</span>
                                <span>Rows est.: {t.row_count_estimate}</span>
                                {t.columns && <span className="truncate">[{t.columns.join(", ")}]</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {contract.parser?.type === "excel" && (
                <div>
                  <Label>Sheet</Label>
                  {fileAnalysis?.detected_sheets && fileAnalysis.detected_sheets.length > 0 ? (
                    <Select
                      value={
                        typeof contract.parser?.sheet === "string"
                          ? contract.parser.sheet
                          : contract.parser?.sheet?.toString() || fileAnalysis.detected_sheets[0].name
                      }
                      onValueChange={(value) => {
                        setContract((prev) => ({
                          ...prev,
                          parser: {
                            ...prev.parser!,
                            sheet: isNaN(Number(value)) ? value : Number(value),
                          },
                        }));
                      }}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {fileAnalysis.detected_sheets.map((sheet) => (
                          <SelectItem key={sheet.index} value={sheet.name}>
                            {sheet.name} (Index: {sheet.index})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      type="text"
                      placeholder="Sheet1 or 0 (leave empty for first sheet)"
                      value={typeof contract.parser?.sheet === "string" ? contract.parser.sheet : contract.parser?.sheet?.toString() || ""}
                      onChange={(e) => {
                        const value = e.target.value;
                        setContract((prev) => ({
                          ...prev,
                          parser: {
                            ...prev.parser!,
                            sheet: value ? (isNaN(Number(value)) ? value : Number(value)) : undefined,
                          },
                        }));
                      }}
                    />
                  )}
                  <p className="text-xs text-muted-foreground mt-1">
                    {fileAnalysis?.detected_sheets && fileAnalysis.detected_sheets.length > 0
                      ? `Detected ${fileAnalysis.detected_sheets.length} sheet(s) in file`
                      : "Enter sheet name (e.g., \"Sheet1\") or index (e.g., \"0\" for first sheet)"}
                  </p>
                </div>
              )}

              {contract.parser?.type === "csv" && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Delimiter</Label>
                    <Input
                      type="text"
                      placeholder=","
                      value={contract.parser?.delimiter || ","}
                      onChange={(e) => {
                        setContract((prev) => ({
                          ...prev,
                          parser: {
                            ...prev.parser!,
                            delimiter: e.target.value || ",",
                          },
                        }));
                      }}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      {fileAnalysis?.detected_delimiter && (
                        <span className="text-blue-600 dark:text-blue-400">
                          Detected: "{fileAnalysis.detected_delimiter}" (you can change this)
                        </span>
                      )}
                      {!fileAnalysis?.detected_delimiter && (
                        <>Common delimiters: , (comma), ; (semicolon), \t (tab)</>
                      )}
                    </p>
                  </div>
                  <div>
                    <Label>Skip Rows</Label>
                    <Input
                      type="number"
                      min="0"
                      value={contract.parser?.skip_rows ?? 0}
                      onChange={(e) => {
                        const value = parseInt(e.target.value, 10);
                        setContract((prev) => ({
                          ...prev,
                          parser: {
                            ...prev.parser!,
                            skip_rows: Number.isNaN(value) ? 0 : value,
                          },
                        }));
                      }}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Number of initial rows to skip before headers/data.
                    </p>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Header Row</Label>
                  <Input
                    type="number"
                    min="0"
                    value={contract.parser?.header_row ?? 0}
                    onChange={(e) => {
                      setContract((prev) => ({
                        ...prev,
                        parser: {
                          ...prev.parser!,
                          header_row: parseInt(e.target.value, 10) || 0,
                        },
                      }));
                    }}
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Row number (0-indexed) where column headers are located. Use 0 if first row contains headers.
                    {fileAnalysis?.detected_header_row !== undefined && (
                      <span className="ml-2 text-blue-600 dark:text-blue-400">
                        Sugerido: {fileAnalysis.detected_header_row}
                      </span>
                    )}
                  </p>
                </div>

                <div>
                  <Label>Skip Rows</Label>
                  <Input
                    type="number"
                    min="0"
                    value={contract.parser?.skip_rows ?? 0}
                    onChange={(e) => {
                      const value = parseInt(e.target.value, 10);
                      setContract((prev) => ({
                        ...prev,
                        parser: {
                          ...prev.parser!,
                          skip_rows: Number.isNaN(value) ? 0 : value,
                        },
                      }));
                    }}
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Rows to skip before reading headers/data.
                    {fileAnalysis?.suggested_skip_rows !== undefined && (
                      <span className="ml-2 text-blue-600 dark:text-blue-400">
                        Sugerido: {fileAnalysis.suggested_skip_rows}
                      </span>
                    )}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Date format (para columnas date)</Label>
                  <Input
                    type="text"
                    placeholder="YYYY-MM-DD"
                    value={contract.parser?.date_format || ""}
                    onChange={(e) =>
                      setContract((prev) => ({
                        ...prev,
                        parser: { ...prev.parser!, date_format: e.target.value || undefined },
                      }))
                    }
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Formato esperado para fechas (ej: YYYY-MM-DD, DD/MM/YYYY).
                  </p>
                </div>
                <div>
                  <Label>Datetime format (para columnas datetime)</Label>
                  <Input
                    type="text"
                    placeholder="YYYY-MM-DD HH:mm:ss"
                    value={contract.parser?.datetime_format || ""}
                    onChange={(e) =>
                      setContract((prev) => ({
                        ...prev,
                        parser: { ...prev.parser!, datetime_format: e.target.value || undefined },
                      }))
                    }
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Formato esperado para fechas con hora (ej: YYYY-MM-DD HH:mm:ss).
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Start Row (optional)</Label>
                  <Input
                    type="number"
                    min="0"
                    value={contract.parser?.range?.start_row ?? ""}
                    onChange={(e) => {
                      const value = e.target.value === "" ? undefined : parseInt(e.target.value, 10);
                      setContract((prev) => ({
                        ...prev,
                        parser: {
                          ...prev.parser!,
                          range: { ...prev.parser?.range, start_row: value },
                        },
                      }));
                    }}
                  />
                </div>
                <div>
                  <Label>End Row (optional)</Label>
                  <Input
                    type="number"
                    min="0"
                    value={contract.parser?.range?.end_row ?? ""}
                    onChange={(e) => {
                      const value = e.target.value === "" ? undefined : parseInt(e.target.value, 10);
                      setContract((prev) => ({
                        ...prev,
                        parser: {
                          ...prev.parser!,
                          range: { ...prev.parser?.range, end_row: value },
                        },
                      }));
                    }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Start Column (optional, e.g., A)</Label>
                  <Input
                    type="text"
                    value={contract.parser?.range?.start_col ?? ""}
                    onChange={(e) => {
                      const value = e.target.value || undefined;
                      setContract((prev) => ({
                        ...prev,
                        parser: {
                          ...prev.parser!,
                          range: { ...prev.parser?.range, start_col: value },
                        },
                      }));
                    }}
                  />
                </div>
                <div>
                  <Label>End Column (optional, e.g., D)</Label>
                  <Input
                    type="text"
                    value={contract.parser?.range?.end_col ?? ""}
                    onChange={(e) => {
                      const value = e.target.value || undefined;
                      setContract((prev) => ({
                        ...prev,
                        parser: {
                          ...prev.parser!,
                          range: { ...prev.parser?.range, end_col: value },
                        },
                      }));
                    }}
                  />
                </div>
              </div>

              {/* Show sample data preview */}
              {fileAnalysis && fileAnalysis.sample_rows.length > 0 && (
                <div>
                  <Label>Sample Data Preview</Label>
                  <div className="mt-2 border rounded-lg overflow-auto max-h-96">
                    <table className="w-full text-xs border-collapse">
                      <thead className="sticky top-0 bg-muted">
                        <tr className="border-b">
                          {fileAnalysis.detected_schema.map((col) => (
                            <th key={col.name} className="px-2 py-2 text-left font-semibold whitespace-nowrap">
                              {col.name}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {fileAnalysis.sample_rows.slice(0, 5).map((row, idx) => (
                          <tr key={idx} className={idx % 2 === 0 ? "bg-muted/40" : ""}>
                            {fileAnalysis.detected_schema.map((col) => {
                              const isNumeric = col.type === "integer" || col.type === "decimal";
                              const isBoolean = col.type === "boolean";
                              const alignClass = isBoolean ? "text-center" : isNumeric ? "text-right font-mono" : "text-left";
                              return (
                                <td
                                  key={col.name}
                                  className={`px-2 py-1 whitespace-nowrap max-w-[220px] truncate ${alignClass}`}
                                  title={String(row[col.name] ?? "")}
                                >
                                  {String(row[col.name] ?? "")}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="flex gap-2">
                <Button variant="outline" onClick={() => {
                  setFileAnalysis(null);
                  setStep("file");
                }}>
                  <ChevronLeft className="mr-2 h-4 w-4" />
                  Back
                </Button>
                <Button
                  onClick={handlePreview}
                  disabled={previewMutation.isPending || analyzingFile}
                  className="ml-auto"
                >
                  {previewMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Refreshing Preview...
                    </>
                  ) : analyzingFile ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Analyzing...
                    </>
                  ) : (
                    <>
                      Refresh Preview
                      <ChevronRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 3: Preview */}
        {step === "preview" && previewData && (
          <Card>
            <CardHeader>
                <CardTitle>Preview Data</CardTitle>
                <CardDescription>
                  Detected {(previewData.row_count ?? 0).toLocaleString()} rows with{" "}
                  {previewData.detected_schema.length} columns
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Detected Schema</Label>
                <div className="mt-2 space-y-2">
                  {previewData.detected_schema.map((col, idx) => (
                    <div key={idx} className="p-2 border rounded text-sm">
                      <span className="font-medium">{col.name}</span>{" "}
                      <span className="text-muted-foreground">({col.type})</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <Label>Sample Data (first 5 rows)</Label>
                <div className="mt-2 border rounded-lg overflow-auto max-h-96">
                  <table className="w-full text-xs border-collapse">
                    <thead className="sticky top-0 bg-muted">
                      <tr className="border-b">
                        {previewData.detected_schema.map((col) => (
                          <th key={col.name} className="px-2 py-2 text-left font-semibold whitespace-nowrap">
                            {col.name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {previewData.sample_rows.slice(0, 5).map((row, idx) => (
                        <tr key={idx} className={idx % 2 === 0 ? "bg-muted/40" : ""}>
                          {previewData.detected_schema.map((col) => {
                            const isNumeric = col.type === "integer" || col.type === "decimal";
                            const isBoolean = col.type === "boolean";
                            const alignClass = isBoolean ? "text-center" : isNumeric ? "text-right font-mono" : "text-left";
                            return (
                              <td
                                key={col.name}
                                className={`px-2 py-1 whitespace-nowrap max-w-[220px] truncate ${alignClass}`}
                                title={String(row[col.name] ?? "")}
                              >
                                {String(row[col.name] ?? "")}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {previewData.warnings.length > 0 && (
                <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                  <div className="font-medium mb-2">Warnings</div>
                  <ul className="list-disc list-inside space-y-1 text-sm">
                    {previewData.warnings.map((warning, idx) => (
                      <li key={idx}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setStep("configure")}>
                  <ChevronLeft className="mr-2 h-4 w-4" />
                  Back
                </Button>
                <Button onClick={generateMapping} className="ml-auto">
                  Configure Mapping
                  <ChevronRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step 3: Mapping */}
        {step === "mapping" && contract.mapping && (
          <Card>
            <CardHeader>
              <CardTitle>Column Mapping</CardTitle>
              <CardDescription>
                Configure how source columns map to target columns
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-4">
                {contract.mapping.map((map, idx) => (
                  <div key={idx} className="p-4 border rounded-lg space-y-2">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Source Column</Label>
                        <Input value={map.source} disabled />
                      </div>
                      <div>
                        <Label>Target Column</Label>
                        <Input
                          value={map.target}
                          onChange={(e) => {
                            const newMapping = [...contract.mapping!];
                            newMapping[idx] = { ...map, target: e.target.value };
                            setContract((prev) => ({ ...prev, mapping: newMapping }));
                          }}
                        />
                      </div>
                    </div>
                    <div>
                      <Label>Data Type</Label>
                      <Select
                        value={map.type}
                        onValueChange={(value: any) => {
                          const newMapping = [...contract.mapping!];
                          newMapping[idx] = { ...map, type: value };
                          setContract((prev) => ({ ...prev, mapping: newMapping }));
                        }}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="string">String</SelectItem>
                          <SelectItem value="integer">Integer</SelectItem>
                          <SelectItem value="decimal">Decimal</SelectItem>
                          <SelectItem value="boolean">Boolean</SelectItem>
                          <SelectItem value="date">Date</SelectItem>
                          <SelectItem value="datetime">DateTime</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                ))}
              </div>

              <div>
                <Label>ResultSet Name</Label>
                <Input
                  value={contract.output?.name || ""}
                  onChange={(e) =>
                    setContract((prev) => ({
                      ...prev,
                      output: { ...prev.output, name: e.target.value },
                    }))
                  }
                  placeholder="My Import"
                />
              </div>

              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setStep("preview")}>
                  <ChevronLeft className="mr-2 h-4 w-4" />
                  Back
                </Button>
                <Button
                  onClick={handleExecute}
                  disabled={executeMutation.isPending || !contract.output?.name}
                  className="ml-auto"
                >
                  {executeMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Importing...
                    </>
                  ) : (
                    <>
                      Execute Import
                      <ChevronRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </DataLabWorkspace>
  );
}
