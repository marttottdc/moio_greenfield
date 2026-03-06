import { Link, useRoute } from "wouter";
import { useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDataLabResultSet } from "@/hooks/use-datalab";
import { Loader2, ArrowLeft } from "lucide-react";
import { formatDate } from "@/lib/utils";

export default function DatasetDetail() {
  const [, params] = useRoute("/datalab/dataset/:id");
  const id = params?.id;
  const { data: rs, isLoading, error } = useDataLabResultSet(id);

  const schema = rs?.schema_json ?? [];
  const preview = rs?.preview_json ?? [];
  const lineage = rs?.lineage_json || {};

  const columns = useMemo(() => schema.map((c) => c.name), [schema]);

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !rs) {
    return (
      <div className="p-6">
        <div className="text-destructive">Dataset not found.</div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link href="/datalab">
            <Button variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">{rs.name || "Dataset"}</h1>
          <p className="text-muted-foreground mt-1">
            {rs.row_count.toLocaleString()} rows • {schema.length} cols • {rs.storage}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="capitalize">
            {rs.origin}
          </Badge>
          <Button variant="outline" size="sm">
            Visualize
          </Button>
          <Button size="sm">Create Snapshot</Button>
        </div>
      </div>

      <Tabs defaultValue="preview">
        <TabsList>
          <TabsTrigger value="preview">Preview</TabsTrigger>
          <TabsTrigger value="schema">Schema</TabsTrigger>
          <TabsTrigger value="lineage">Lineage</TabsTrigger>
        </TabsList>

        <TabsContent value="preview">
          <Card>
            <CardHeader>
              <CardTitle>Preview</CardTitle>
              <CardDescription>First {preview.length} rows</CardDescription>
            </CardHeader>
            <CardContent>
              {preview.length === 0 ? (
                <div className="text-muted-foreground text-sm">No preview data.</div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {columns.map((c) => (
                          <TableHead key={c}>{c}</TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {preview.map((row, idx) => (
                        <TableRow key={idx}>
                          {columns.map((c) => (
                            <TableCell key={c} className="max-w-[180px] truncate">
                              {String(row[c] ?? "")}
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
        </TabsContent>

        <TabsContent value="schema">
          <Card>
            <CardHeader>
              <CardTitle>Schema</CardTitle>
              <CardDescription>Columns and types</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2 md:grid-cols-2">
              {schema.map((col) => (
                <div key={col.name} className="p-3 border rounded-md">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{col.name}</span>
                    <Badge variant="outline">{col.type}</Badge>
                  </div>
                  {col.nullable && (
                    <div className="text-xs text-muted-foreground mt-1">nullable</div>
                  )}
                  {col.original_type && (
                    <div className="text-xs text-muted-foreground mt-1">
                      Original: {col.original_type}
                    </div>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="lineage">
          <Card>
            <CardHeader>
              <CardTitle>Lineage</CardTitle>
              <CardDescription>Origin and upstream metadata</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <div>
                <span className="font-medium text-foreground">Origin:</span> {rs.origin}
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
              <div>
                <span className="font-medium text-foreground">Created:</span>{" "}
                {formatDate(rs.created_at)}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
