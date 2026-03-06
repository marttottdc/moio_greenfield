import { Link } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabResultSets } from "@/hooks/use-datalab";
import { Database, Plus, Loader2 } from "lucide-react";
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

export default function DataLabImports() {
  const { data, isLoading } = useDataLabResultSets("import", 1, 20);

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Imports</h1>
            <p className="text-muted-foreground mt-2">
              Processed data imports that created ResultSets
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              Imports are executed processes that transform files into queryable ResultSets.
            </p>
          </div>
          <Link href="/datalab/imports/new">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Import
            </Button>
          </Link>
        </div>

        <Card className="border-green-200 bg-green-50/50 dark:bg-green-950/20 dark:border-green-900">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-5 w-5" />
              Processed Imports
            </CardTitle>
            <CardDescription>
              These are completed imports that created ResultSets. Each import processed a file and generated queryable data.
            </CardDescription>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Import History</CardTitle>
            <CardDescription>
              {data?.count ? `${data.count} total imports` : "No imports yet"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : !data?.results || data.results.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Database className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No imports yet</p>
                <p className="text-sm mt-2">Create your first import to get started</p>
                <Link href="/datalab/imports/new">
                  <Button className="mt-4">
                    <Plus className="mr-2 h-4 w-4" />
                    New Import
                  </Button>
                </Link>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Rows</TableHead>
                    <TableHead>Storage</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.results.map((resultset) => (
                    <TableRow key={resultset.id}>
                      <TableCell className="font-medium">
                        {resultset.name || "Unnamed Import"}
                      </TableCell>
                      <TableCell>
                        {resultset.row_count.toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <Badge variant={resultset.storage === "parquet" ? "default" : "secondary"}>
                          {resultset.storage}
                        </Badge>
                      </TableCell>
                      <TableCell>{formatDate(resultset.created_at)}</TableCell>
                      <TableCell>
                        <Link href={`/datalab/resultsets/${resultset.id}`}>
                          <Button variant="ghost" size="sm">
                            View
                          </Button>
                        </Link>
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
