import { useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export function DatasetViewer({ id }: { id: string }) {
  const { data: rs, isLoading, error } = useDataLabResultSet(id);
  const schema = rs?.schema_json ?? [];
  const preview = rs?.preview_json ?? [];
  const lineage = rs?.lineage_json || {};
  const columns = useMemo(() => schema.map((c) => c.name), [schema]);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin mr-2" />
        Loading dataset...
      </div>
    );
  }
  if (error || !rs) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground">
        Unable to load dataset.
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">{rs.name || "Dataset"}</h2>
          <p className="text-sm text-muted-foreground">
            {rs.row_count.toLocaleString()} rows • {schema.length} columns • {rs.storage}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="capitalize">
            {rs.origin}
          </Badge>
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
                <div className="text-sm text-muted-foreground">No preview data.</div>
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
                            <TableCell key={c} className="max-w-[200px] truncate">
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
              <CardDescription>Column definitions</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2 md:grid-cols-2">
              {schema.map((col) => (
                <div key={col.name} className="p-3 border rounded-md">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{col.name}</span>
                    <Badge variant="outline">{col.type}</Badge>
                  </div>
                  {col.nullable && <div className="text-xs text-muted-foreground mt-1">nullable</div>}
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
                <div>
                  <span className="font-medium text-foreground">Import Process:</span>{" "}
                  {lineage.import_process_name || lineage.import_process_id}
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
