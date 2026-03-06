import { useParams, Link } from "wouter";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabPipelines, useDataLabPipelineRuns } from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, History, Play, CheckCircle2, XCircle, Clock } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export default function PipelineRuns() {
  const { id } = useParams<{ id: string }>();
  const { data: pipelines } = useDataLabPipelines();
  const { data: runs, isLoading } = useDataLabPipelineRuns(id || "");

  const pipeline = pipelines?.find((p) => p.id === id);

  if (!pipeline && id) {
    return (
      <PageLayout>
        <div className="text-center py-12">
          <h2 className="text-2xl font-bold mb-2">Pipeline Not Found</h2>
          <Link href="/datalab/pipelines">
            <Button>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Pipelines
            </Button>
          </Link>
        </div>
      </PageLayout>
    );
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "success":
        return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />;
      case "running":
        return <Clock className="h-4 w-4 text-blue-500 animate-spin" />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "success":
        return <Badge variant="default" className="bg-green-500">Success</Badge>;
      case "failed":
        return <Badge variant="destructive">Failed</Badge>;
      case "running":
        return <Badge variant="default" className="bg-blue-500">Running</Badge>;
      default:
        return <Badge variant="secondary">Pending</Badge>;
    }
  };

  return (
    <PageLayout>
      <div className="space-y-6">
        <div>
          <Link href="/datalab/pipelines">
            <Button variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Pipeline Run History</h1>
          <p className="text-muted-foreground mt-2">
            {pipeline?.name || "All Pipeline Runs"}
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Execution History</CardTitle>
            <CardDescription>
              {runs?.length ? `${runs.length} total runs` : "No runs yet"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : !runs || runs.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <History className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No pipeline runs yet</p>
                <p className="text-sm mt-2">Execute the pipeline to see run history</p>
                {id && (
                  <Link href={`/datalab/pipelines/${id}/run`}>
                    <Button className="mt-4">
                      <Play className="mr-2 h-4 w-4" />
                      Run Pipeline
                    </Button>
                  </Link>
                )}
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Status</TableHead>
                    <TableHead>Pipeline</TableHead>
                    <TableHead>Started</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Outputs</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((run) => (
                    <TableRow key={run.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {getStatusIcon(run.status)}
                          {getStatusBadge(run.status)}
                        </div>
                      </TableCell>
                      <TableCell className="font-medium">
                        {run.pipeline_name}
                      </TableCell>
                      <TableCell>{formatDate(run.started_at)}</TableCell>
                      <TableCell>
                        {run.duration_seconds
                          ? `${run.duration_seconds.toFixed(2)}s`
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {Object.keys(run.outputs_json || {}).length} outputs
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {run.status === "success" && run.outputs_json && (
                          <div className="flex gap-2">
                            {Object.entries(run.outputs_json).map(([key, resultsetId]) => (
                              <Link
                                key={key}
                                href={`/datalab/resultsets/${resultsetId}`}
                              >
                                <Button variant="ghost" size="sm">
                                  View {key}
                                </Button>
                              </Link>
                            ))}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
