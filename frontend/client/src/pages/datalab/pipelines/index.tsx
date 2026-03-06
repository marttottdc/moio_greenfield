import { Link } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabPipelines } from "@/hooks/use-datalab";
import { Workflow, Plus, Loader2, Play, Edit, History } from "lucide-react";
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

export default function DataLabPipelines() {
  const { data: pipelines, isLoading, error } = useDataLabPipelines();

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Pipelines</h1>
            <p className="text-muted-foreground mt-2">
              Build automated data processing workflows
            </p>
          </div>
          <Link href="/datalab/pipelines/new">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Pipeline
            </Button>
          </Link>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>All Pipelines</CardTitle>
            <CardDescription>
              {pipelines?.length ? `${pipelines.length} total pipelines` : "No pipelines yet"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="text-center py-8">
                <div className="text-destructive mb-2">Failed to load pipelines</div>
                <div className="text-sm text-muted-foreground">
                  {error instanceof Error ? error.message : "Unknown error"}
                </div>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => window.location.reload()}
                >
                  Retry
                </Button>
              </div>
            ) : !pipelines || pipelines.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Workflow className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No pipelines created yet</p>
                <p className="text-sm mt-2">Create your first pipeline to get started</p>
                <Link href="/datalab/pipelines/new">
                  <Button className="mt-4">
                    <Plus className="mr-2 h-4 w-4" />
                    New Pipeline
                  </Button>
                </Link>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Steps</TableHead>
                    <TableHead>Parameters</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {pipelines.map((pipeline) => (
                    <TableRow key={pipeline.id}>
                      <TableCell className="font-medium">{pipeline.name}</TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {pipeline.steps_json?.length || 0} steps
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {pipeline.params_json?.length || 0} params
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {pipeline.is_active ? (
                          <Badge variant="default">Active</Badge>
                        ) : (
                          <Badge variant="secondary">Inactive</Badge>
                        )}
                      </TableCell>
                      <TableCell>{formatDate(pipeline.created_at)}</TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          <Link href={`/datalab/pipelines/${pipeline.id}/edit`}>
                            <Button variant="ghost" size="sm">
                              <Edit className="mr-2 h-4 w-4" />
                              Edit
                            </Button>
                          </Link>
                          <Link href={`/datalab/pipelines/${pipeline.id}/run`}>
                            <Button variant="ghost" size="sm">
                              <Play className="mr-2 h-4 w-4" />
                              Run
                            </Button>
                          </Link>
                          <Link href={`/datalab/pipelines/${pipeline.id}/runs`}>
                            <Button variant="ghost" size="sm">
                              <History className="mr-2 h-4 w-4" />
                              History
                            </Button>
                          </Link>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </DataLabWorkspace>
  );
}
