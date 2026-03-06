import { useState } from "react";
import { useRoute, Link } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import { useDataLabFiles, useDataLabImportProcess, useDataLabImportProcessRun } from "@/hooks/use-datalab";
import { Loader2, Play } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export default function ImportProcessRunner() {
  const [, params] = useRoute("/datalab/processes/imports/:id/run");
  const processId = params?.id;
  const { toast } = useToast();

  const { data: process, isLoading: processLoading } = useDataLabImportProcess(processId);
  const { data: files, isLoading: filesLoading } = useDataLabFiles(1, 50);
  const runMutation = useDataLabImportProcessRun(processId || "");
  const [fileId, setFileId] = useState<string | undefined>();

  const handleRun = () => {
    if (!processId || !fileId) {
      toast({ variant: "destructive", description: "Select a file to run the process." });
      return;
    }
    runMutation.mutate(
      { raw_dataset_id: fileId },
      {
        onSuccess: () => {
          toast({ description: "Process run started" });
        },
        onError: (err: any) => {
          toast({
            variant: "destructive",
            description: err?.message || "Failed to start run",
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
            <h1 className="text-3xl font-bold">Run Import Process</h1>
            <p className="text-muted-foreground mt-2">
              Validate shape and execute the process on a selected file.
            </p>
          </div>
          <Link href={`/datalab/processes/imports/${processId}`}>
            <Button variant="ghost">Back to process</Button>
          </Link>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{process?.name || "Import Process"}</CardTitle>
            <CardDescription>
              {process ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline" className="capitalize">
                    {process.file_type}
                  </Badge>
                  <Badge variant="secondary">v{process.version}</Badge>
                  <span className="text-xs text-muted-foreground">
                    Fingerprint {process.shape_fingerprint}
                  </span>
                </div>
              ) : processLoading ? (
                "Loading process..."
              ) : (
                "Process not found"
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="text-sm font-semibold">Select file</div>
              {filesLoading ? (
                <div className="flex items-center text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Loading files...
                </div>
              ) : (
                <Select value={fileId} onValueChange={setFileId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose a file to run this process on" />
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

            <Button onClick={handleRun} disabled={runMutation.isPending || !fileId || !processId}>
              {runMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Run process
            </Button>
          </CardContent>
        </Card>
      </div>
    </DataLabWorkspace>
  );
}
