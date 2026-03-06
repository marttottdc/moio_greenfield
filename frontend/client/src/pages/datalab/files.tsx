import { useState, useEffect } from "react";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  useDataLabFiles,
  useDataLabFileUpload,
  useDataLabImportProcesses,
} from "@/hooks/use-datalab";
import { Upload, FileText, Loader2, ArrowRight, Database, Trash2, Info } from "lucide-react";
import { Link } from "wouter";
import { useToast } from "@/hooks/use-toast";
import { formatBytes, formatDate } from "@/lib/utils";
import { dataLabApi } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export default function DataLabFiles() {
  const [page, setPage] = useState(1);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useDataLabFiles(page, 20);
  const { data: processData } = useDataLabImportProcesses(1, 50);
  const uploadMutation = useDataLabFileUpload();
  const { toast } = useToast();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const processes = processData?.results ?? [];

  // Refetch files when component mounts to ensure fresh data
  useEffect(() => {
    refetch();
  }, [refetch]);

  // Debug: Log when data changes
  useEffect(() => {
    console.log("Files data updated:", { page, count: data?.count, results: data?.results?.length, files: data?.results });
  }, [data, page]);

  const handleDelete = async (fileId: string) => {
    try {
      setDeletingId(fileId);
      await dataLabApi.deleteFile(fileId);
      await queryClient.invalidateQueries({ queryKey: ["datalab", "files"] });
      await queryClient.refetchQueries({ queryKey: ["datalab", "files", 1, 20] });
      toast({ title: "File deleted" });
    } catch (err) {
      toast({
        title: "Delete failed",
        description: err instanceof Error ? err.message : "Failed to delete file",
        variant: "destructive",
      });
    } finally {
      setDeletingId(null);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setUploadProgress(0);
    try {
      const uploadedFile = await uploadMutation.mutateAsync({
        file,
        onProgress: (progress) => {
          setUploadProgress(progress);
        },
      });
      
      console.log("File uploaded successfully:", uploadedFile);
      
      // Reset input first
      event.target.value = "";
      
      // Reset to page 1 to see the new file (newest files are typically on page 1)
      setPage(1);
      
      // Wait a brief moment for backend to process, then refetch
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Invalidate all file queries and refetch page 1
      await queryClient.invalidateQueries({ queryKey: ["datalab", "files"] });
      await queryClient.refetchQueries({ queryKey: ["datalab", "files", 1, 20] });
      
      toast({
        title: "File uploaded",
        description: `${file.name} has been uploaded successfully.`,
      });
      setUploadProgress(null);
    } catch (error) {
      console.error("File upload error:", error);
      toast({
        title: "Upload failed",
        description: error instanceof Error ? error.message : "Failed to upload file",
        variant: "destructive",
      });
      setUploadProgress(null);
    }
  };

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Files</h1>
            <p className="text-muted-foreground mt-2">
              Upload and manage raw data files (CSV, Excel)
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Files are stored but not processed. Use "New Import" to process files into ResultSets.
            </p>
          </div>
          <div className="flex items-center gap-2">
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
        </div>

        {uploadProgress !== null && (
          <Card>
            <CardContent className="pt-6">
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Uploading...</span>
                  <span>{Math.round(uploadProgress)}%</span>
                </div>
                <div className="w-full bg-secondary rounded-full h-2">
                  <div
                    className="bg-primary h-2 rounded-full transition-all"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <Card className="border-blue-200 bg-blue-50/40 dark:bg-blue-950/10 dark:border-blue-900">
          <CardHeader className="py-3">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4" />
              <div>
                <CardTitle className="text-base">Raw Files</CardTitle>
                <CardDescription className="text-sm">
                  Upload CSV or Excel, then create an Import to process them.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader className="py-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Uploaded Files</CardTitle>
                <CardDescription className="text-sm">
                  {data?.count ? `${data.count} files` : "No files uploaded yet"}
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="text-center py-8 text-destructive">
                Failed to load files. Please try again.
              </div>
            ) : !data?.results || data.results.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No files uploaded yet</p>
                <p className="text-sm mt-2">Upload a CSV or Excel file to get started</p>
              </div>
            ) : (
              <>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                    <TableRow>
                      <TableHead className="py-2">Filename</TableHead>
                      <TableHead className="py-2">Size</TableHead>
                      <TableHead className="py-2">Uploaded</TableHead>
                      <TableHead className="py-2">Info</TableHead>
                      <TableHead className="py-2">Matching Processes</TableHead>
                      <TableHead className="py-2 text-right">Actions</TableHead>
                    </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.results.map((file) => (
                        <TableRow key={file.id} className="h-10">
                          <TableCell className="font-medium truncate max-w-[220px]">{file.filename}</TableCell>
                          <TableCell className="whitespace-nowrap">{formatBytes(file.size)}</TableCell>
                          <TableCell className="whitespace-nowrap">{formatDate(file.created_at)}</TableCell>
                          <TableCell>
                            <div className="text-xs text-muted-foreground space-y-1">
                              {file.metadata?.detected_type && <div className="flex items-center gap-1"><Info className="h-3 w-3" /> {file.metadata.detected_type}</div>}
                              {file.metadata?.columns && Array.isArray(file.metadata.columns) && (
                                <div className="line-clamp-1">
                                  Cols: {file.metadata.columns.slice(0, 6).join(", ")}
                                  {file.metadata.columns.length > 6 && "…"}
                                </div>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="max-w-[220px]">
                            <MatchingProcesses
                              processes={processes}
                              fileType={inferFileType(file)}
                              fileId={file.id}
                            />
                          </TableCell>
                          <TableCell className="text-right space-x-1 whitespace-nowrap">
                            <Link href={`/datalab/imports/new?file_id=${file.id}`}>
                              <Button variant="ghost" size="sm">
                                Import
                              </Button>
                            </Link>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive"
                              onClick={() => handleDelete(file.id)}
                              disabled={deletingId === file.id}
                            >
                              {deletingId === file.id ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                <Trash2 className="h-4 w-4" />
                              )}
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {(data.next || data.previous) && (
                  <div className="flex items-center justify-between mt-4">
                    <Button
                      variant="outline"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={!data.previous}
                    >
                      Previous
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      Page {page}
                    </span>
                    <Button
                      variant="outline"
                      onClick={() => setPage((p) => p + 1)}
                      disabled={!data.next}
                    >
                      Next
                    </Button>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </DataLabWorkspace>
  );
}

function inferFileType(file: any): "csv" | "excel" | "pdf" | undefined {
  const contentType = (file?.content_type || "").toLowerCase();
  const detected = (file?.metadata?.detected_type || "").toLowerCase();
  const name = (file?.filename || "").toLowerCase();
  if (contentType.includes("pdf") || detected.includes("pdf") || name.endsWith(".pdf")) return "pdf";
  if (
    contentType.includes("excel") ||
    detected.includes("excel") ||
    name.endsWith(".xlsx") ||
    name.endsWith(".xls")
  )
    return "excel";
  if (contentType.includes("csv") || detected.includes("csv") || name.endsWith(".csv")) return "csv";
  return undefined;
}

function MatchingProcesses({
  processes,
  fileType,
  fileId,
}: {
  processes: any[];
  fileType?: "csv" | "excel" | "pdf";
  fileId: string;
}) {
  if (!fileType) {
    return <span className="text-xs text-muted-foreground">Unknown type</span>;
  }
  const matching = processes.filter((p) => p.file_type === fileType);
  if (!matching.length) {
    return <span className="text-xs text-muted-foreground">No matching processes</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      {matching.slice(0, 3).map((p) => (
        <div key={p.id} className="flex items-center gap-2 text-xs">
          <Badge variant="outline" className="truncate max-w-[140px]">
            {p.name}
          </Badge>
          <Link href={`/datalab/processes/imports/${p.id}/run?file_id=${fileId}`}>
            <Button variant="ghost" size="sm" className="h-7 px-2">
              <ArrowRight className="h-3 w-3 mr-1" />
              Run
            </Button>
          </Link>
        </div>
      ))}
      {matching.length > 3 && (
        <span className="text-[11px] text-muted-foreground">+{matching.length - 3} more</span>
      )}
    </div>
  );
}
