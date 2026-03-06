import { Link } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabScripts } from "@/hooks/use-datalab";
import { Code, Plus, Loader2, Play, Edit } from "lucide-react";
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

export default function DataLabScripts() {
  const { data: scripts, isLoading } = useDataLabScripts();

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Scripts</h1>
            <p className="text-muted-foreground mt-2">
              Create and manage Python scripts for data transformation
            </p>
          </div>
          <Link href="/datalab/scripts/new">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Script
            </Button>
          </Link>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>All Scripts</CardTitle>
            <CardDescription>
              {scripts?.length ? `${scripts.length} total scripts` : "No scripts yet"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : !scripts || scripts.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Code className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No scripts created yet</p>
                <p className="text-sm mt-2">Create your first script to get started</p>
                <Link href="/datalab/scripts/new">
                  <Button className="mt-4">
                    <Plus className="mr-2 h-4 w-4" />
                    New Script
                  </Button>
                </Link>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Slug</TableHead>
                    <TableHead>Inputs</TableHead>
                    <TableHead>Outputs</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scripts.map((script) => (
                    <TableRow key={script.id}>
                      <TableCell className="font-medium">{script.name}</TableCell>
                      <TableCell>
                        <code className="text-xs bg-muted px-2 py-1 rounded">
                          {script.slug}
                        </code>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {Object.keys(script.input_spec_json || {}).length} inputs
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {Object.keys(script.output_spec_json || {}).length} outputs
                        </Badge>
                      </TableCell>
                      <TableCell>{formatDate(script.updated_at)}</TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          <Link href={`/datalab/scripts/${script.id}/edit`}>
                            <Button variant="ghost" size="sm">
                              <Edit className="mr-2 h-4 w-4" />
                              Edit
                            </Button>
                          </Link>
                          <Link href={`/datalab/scripts/${script.id}/execute`}>
                            <Button variant="ghost" size="sm">
                              <Play className="mr-2 h-4 w-4" />
                              Run
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
