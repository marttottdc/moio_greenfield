import { Link } from "wouter";
import { Copy, Loader2, Play, Plus, Shapes } from "lucide-react";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDataLabImportProcessClone, useDataLabImportProcesses } from "@/hooks/use-datalab";
import { formatDate } from "@/lib/utils";

export default function ImportProcessesList() {
  const { data, isLoading, error } = useDataLabImportProcesses();
  const cloneMutation = useDataLabImportProcessClone();

  const processes = data?.results ?? [];

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Import Processes</h1>
            <p className="text-muted-foreground mt-2">
              Reusable, shape-validated imports for CSV, Excel, and PDF
            </p>
          </div>
          <Link href="/datalab/processes/imports/new">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Import Process
            </Button>
          </Link>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>All Import Processes</CardTitle>
            <CardDescription>
              {processes.length
                ? `${processes.length} processes`
                : "Define reusable import processes and run them on files"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-10 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                Loading processes...
              </div>
            ) : error ? (
              <div className="text-center py-8 text-muted-foreground">
                <p className="text-destructive mb-2">Failed to load import processes</p>
                <p className="text-sm">
                  {error instanceof Error ? error.message : "Unknown error"}
                </p>
                <Button variant="outline" className="mt-4" onClick={() => window.location.reload()}>
                  Retry
                </Button>
              </div>
            ) : processes.length === 0 ? (
              <div className="text-center py-10 text-muted-foreground">
                <Shapes className="h-10 w-10 mx-auto mb-3 opacity-60" />
                <p className="font-medium">No import processes yet</p>
                <p className="text-sm mt-1">
                  Create a process to capture shape + mappings and reuse it on any matching file.
                </p>
                <Link href="/datalab/processes/imports/new">
                  <Button className="mt-4">
                    <Plus className="mr-2 h-4 w-4" />
                    New Import Process
                  </Button>
                </Link>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>File Type</TableHead>
                    <TableHead>Structural Units</TableHead>
                    <TableHead>Fingerprint</TableHead>
                    <TableHead>Version</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {processes.map((process) => {
                    const suCount = process.structural_units?.length ?? 0;
                    const fingerprint =
                      process.shape_fingerprint?.length > 12
                        ? `${process.shape_fingerprint.slice(0, 12)}…`
                        : process.shape_fingerprint ?? "—";
                    return (
                      <TableRow key={process.id}>
                        <TableCell className="font-medium">{process.name}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="capitalize">
                            {process.file_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant="secondary">{suCount} units</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {fingerprint}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">v{process.version ?? 1}</Badge>
                        </TableCell>
                        <TableCell>{formatDate(process.updated_at || process.created_at)}</TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            <Link href={`/datalab/processes/imports/${process.id}`}>
                              <Button variant="ghost" size="sm">
                                View
                              </Button>
                            </Link>
                            <Link href={`/datalab/processes/imports/${process.id}/run`}>
                              <Button variant="ghost" size="sm">
                                <Play className="mr-1 h-4 w-4" />
                                Run
                              </Button>
                            </Link>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={cloneMutation.isPending}
                              onClick={() => cloneMutation.mutate({ id: process.id })}
                            >
                              {cloneMutation.isPending ? (
                                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                              ) : (
                                <Copy className="mr-1 h-4 w-4" />
                              )}
                              Clone
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </DataLabWorkspace>
  );
}
