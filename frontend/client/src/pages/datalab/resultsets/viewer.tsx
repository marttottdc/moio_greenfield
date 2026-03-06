import { useParams, Link } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabResultSet } from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, Database } from "lucide-react";
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

export default function ResultSetViewer() {
  const { id } = useParams<{ id: string }>();
  const { data: resultset, isLoading, error } = useDataLabResultSet(id);
  const lineage = resultset?.lineage_json || {};

  if (isLoading) {
    return (
      <DataLabWorkspace>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </DataLabWorkspace>
    );
  }

  if (error || !resultset) {
    return (
      <DataLabWorkspace>
        <div className="text-center py-12">
          <Database className="h-12 w-12 mx-auto mb-4 opacity-50 text-muted-foreground" />
          <h2 className="text-2xl font-bold mb-2">ResultSet Not Found</h2>
          <p className="text-muted-foreground mb-4">
            The resultset you're looking for doesn't exist or has been deleted.
          </p>
          <Link href="/datalab/datasets">
            <Button>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Datasets
            </Button>
          </Link>
        </div>
      </DataLabWorkspace>
    );
  }

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Link href="/datalab/datasets">
              <Button variant="ghost" size="sm" className="mb-2">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </Link>
            <h1 className="text-3xl font-bold">
              {resultset.name || "Unnamed ResultSet"}
            </h1>
            <p className="text-muted-foreground mt-2">
              {resultset.row_count.toLocaleString()} rows • {resultset.schema_json.length} columns
            </p>
          </div>
          <div className="flex gap-2">
            <Badge variant="outline">{resultset.origin}</Badge>
            <Badge variant={resultset.storage === "parquet" ? "default" : "secondary"}>
              {resultset.storage}
            </Badge>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Schema</CardTitle>
              <CardDescription>Column definitions</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {resultset.schema_json.map((col, idx) => (
                  <div key={idx} className="p-3 border rounded-lg">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{col.name}</span>
                      <div className="flex gap-2">
                        <Badge variant="outline" className="text-xs">
                          {col.type}
                        </Badge>
                        {col.nullable && (
                          <Badge variant="secondary" className="text-xs">
                            nullable
                          </Badge>
                        )}
                      </div>
                    </div>
                    {col.original_type && (
                      <div className="text-xs text-muted-foreground mt-1">
                        Original: {col.original_type}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Metadata</CardTitle>
              <CardDescription>ResultSet information</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="text-sm font-medium mb-1">Created</div>
                <div className="text-sm text-muted-foreground">
                  {formatDate(resultset.created_at)}
                </div>
              </div>
              {resultset.created_by && (
                <div>
                  <div className="text-sm font-medium mb-1">Created By</div>
                  <div className="text-sm text-muted-foreground">
                    {resultset.created_by}
                  </div>
                </div>
              )}
              {resultset.expires_at && (
                <div>
                  <div className="text-sm font-medium mb-1">Expires</div>
                  <div className="text-sm text-muted-foreground">
                    {formatDate(resultset.expires_at)}
                  </div>
                </div>
              )}
              <div>
                <div className="text-sm font-medium mb-1">Storage</div>
                <div className="text-sm text-muted-foreground">
                  {resultset.storage === "parquet" ? "Parquet (S3)" : "Memory"}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Lineage</CardTitle>
              <CardDescription>Origin and upstream process</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <div>
                <span className="font-medium text-foreground">Origin:</span> {resultset.origin}
              </div>
              {lineage.import_process_id && (
                <div className="flex items-center gap-2">
                  <span className="font-medium text-foreground">Import Process:</span>
                  <Link href={`/datalab/processes/imports/${lineage.import_process_id}`}>
                    <Button variant="link" className="px-0">
                      {lineage.import_process_name || lineage.import_process_id}
                    </Button>
                  </Link>
                </div>
              )}
              {lineage.import_run_id && (
                <div>
                  <span className="font-medium text-foreground">Run:</span>{" "}
                  <span className="font-mono text-xs">{lineage.import_run_id}</span>
                </div>
              )}
              {lineage.source_file_id && (
                <div>
                  <span className="font-medium text-foreground">Source file:</span>{" "}
                  <span className="font-mono text-xs">{lineage.source_file_id}</span>
                </div>
              )}
              {!lineage.import_process_id && (
                <div className="text-xs text-muted-foreground">
                  Upstream process details unavailable for this dataset.
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Preview Data</CardTitle>
            <CardDescription>
              First {resultset.preview_json.length} rows (max 200)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {resultset.preview_json.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No preview data available
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {resultset.schema_json.map((col) => (
                        <TableHead key={col.name}>{col.name}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resultset.preview_json.map((row, idx) => (
                      <TableRow key={idx}>
                        {resultset.schema_json.map((col) => (
                          <TableCell key={col.name} className="max-w-[200px] truncate">
                            {String(row[col.name] ?? "")}
                          </TableCell>
                        ))}
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
