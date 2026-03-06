import { Link } from "wouter";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { History, ArrowRight, Loader2 } from "lucide-react";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDataLabImportRuns } from "@/hooks/use-datalab";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export default function DataLabRuns() {
  const { data: importRuns, isLoading, error } = useDataLabImportRuns();

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">Runs / History</h1>
          <p className="text-muted-foreground mt-2">
            Audit and review process runs. Datasets remain the primary object—runs explain how they were produced.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <History className="h-4 w-4" />
                Import Runs
              </CardTitle>
              <CardDescription>History of datasets created by Imports</CardDescription>
            </CardHeader>
            <CardContent>
              <Link href="/datalab/imports">
                <Button variant="outline" className="w-full">
                  View Imports
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <History className="h-4 w-4" />
                Pipeline Runs
              </CardTitle>
              <CardDescription>Run history is per pipeline</CardDescription>
            </CardHeader>
            <CardContent>
              <Link href="/datalab/pipelines">
                <Button variant="outline" className="w-full">
                  View Pipelines
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <p className="text-xs text-muted-foreground mt-2">
                Open a pipeline to see its run history.
              </p>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Recent Import Runs</CardTitle>
            <CardDescription>Shape-validated executions of Import Processes</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-6 text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin mr-2" />
                Loading runs...
              </div>
            ) : error ? (
              <div className="text-destructive text-sm">Failed to load import runs.</div>
            ) : !importRuns?.results?.length ? (
              <div className="text-sm text-muted-foreground">No import runs yet.</div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Process</TableHead>
                      <TableHead>File</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Shape Match</TableHead>
                      <TableHead>Started</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {importRuns.results.map((run) => (
                      <TableRow key={run.id}>
                        <TableCell className="font-medium">
                          {run.import_process_name || run.import_process}
                        </TableCell>
                        <TableCell className="text-xs">{run.raw_dataset_filename || run.raw_dataset}</TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              run.status === "success"
                                ? "default"
                                : run.status === "failed"
                                ? "destructive"
                                : "secondary"
                            }
                          >
                            {run.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {run.shape_match?.passed ? (
                            <Badge variant="outline">Passed</Badge>
                          ) : (
                            <Badge variant="destructive">Failed</Badge>
                          )}
                        </TableCell>
                        <TableCell>{formatDate(run.started_at)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </DataLabWorkspace>
  );
}

