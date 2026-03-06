import { useRoute, Link } from "wouter";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import {
  useDataLabImportProcess,
  useDataLabImportProcessClone,
  useDataLabImportRuns,
} from "@/hooks/use-datalab";
import { formatDate } from "@/lib/utils";
import { Loader2, Copy, Play, Shapes } from "lucide-react";

export default function ImportProcessDetail() {
  const [, params] = useRoute("/datalab/processes/imports/:id");
  const processId = params?.id;

  const { data: process, isLoading, error } = useDataLabImportProcess(processId);
  const { data: runs, isLoading: runsLoading } = useDataLabImportRuns(1, 20, {
    import_process: processId,
  });
  const cloneMutation = useDataLabImportProcessClone();

  const structuralUnits = process?.structural_units ?? [];
  const derivations = process?.semantic_derivations ?? [];

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">{process?.name || "Import Process"}</h1>
            <p className="text-muted-foreground mt-2">
              Persistent shape-aware import definition with reusable mappings.
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => processId && cloneMutation.mutate({ id: processId })}
              disabled={cloneMutation.isPending}
            >
              {cloneMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Copy className="mr-2 h-4 w-4" />
              )}
              Clone
            </Button>
            {processId && (
              <Link href={`/datalab/processes/imports/${processId}/run`}>
                <Button>
                  <Play className="mr-2 h-4 w-4" />
                  Run process
                </Button>
              </Link>
            )}
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            Loading process...
          </div>
        ) : error || !process ? (
          <Card>
            <CardContent className="py-10 text-center text-muted-foreground">
              <p className="text-destructive mb-2">Unable to load process</p>
              <p className="text-sm">
                {error instanceof Error ? error.message : "Process not found"}
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card>
              <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div className="space-y-1">
                  <CardTitle className="flex items-center gap-2">
                    {process.name}
                    <Badge variant="outline" className="capitalize">
                      {process.file_type}
                    </Badge>
                    <Badge variant="secondary">v{process.version}</Badge>
                  </CardTitle>
                  <CardDescription>
                    Shape fingerprint:{" "}
                    <span className="font-mono text-xs">{process.shape_fingerprint}</span>
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={process.is_active ? "default" : "secondary"}>
                    {process.is_active ? "Active" : "Inactive"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    Updated {formatDate(process.updated_at || process.created_at)}
                  </span>
                </div>
              </CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold">Shape Description</h4>
                  {renderShapeDescription(process.shape_description)}
                </div>
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold">Summary</h4>
                  <ul className="text-sm text-muted-foreground list-disc list-inside space-y-1">
                    <li>{structuralUnits.length} structural units</li>
                    <li>{derivations.length} semantic derivations</li>
                    <li>File type: {process.file_type.toUpperCase()}</li>
                  </ul>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Structural Units</CardTitle>
                <CardDescription>
                  Logical regions of the source (sheets, tables, or regions) that produce datasets.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {structuralUnits.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No structural units defined.</p>
                ) : (
                  <div className="space-y-3">
                    {structuralUnits.map((unit) => (
                      <div
                        key={unit.id}
                        className="rounded border border-border px-4 py-3 flex flex-col gap-1"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold">{unit.name}</span>
                          <Badge variant="outline" className="capitalize">
                            {unit.kind.replace("_", " ")}
                          </Badge>
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {renderUnitSelector(unit)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Semantic Derivations</CardTitle>
                <CardDescription>
                  Output schemas/mappings derived from each structural unit.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {derivations.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No derivations defined.</p>
                ) : (
                  <div className="space-y-3">
                    {derivations.map((derivation) => (
                      <div
                        key={derivation.id}
                        className="rounded border border-border px-4 py-3 flex flex-col gap-1"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold">{derivation.name}</span>
                          <Badge variant="secondary">
                            {derivation.mapping?.length || 0} mapped columns
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Structural unit: {derivation.structural_unit_id}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between">
                <div>
                  <CardTitle>Runs</CardTitle>
                  <CardDescription>Execution history with shape validation results.</CardDescription>
                </div>
                {processId && (
                  <Link href={`/datalab/processes/imports/${processId}/run`}>
                    <Button size="sm">
                      <Play className="mr-2 h-4 w-4" />
                      Run process
                    </Button>
                  </Link>
                )}
              </CardHeader>
              <CardContent>
                {runsLoading ? (
                  <div className="flex items-center justify-center py-6 text-muted-foreground">
                    <Loader2 className="h-5 w-5 animate-spin mr-2" />
                    Loading runs...
                  </div>
                ) : !runs?.results?.length ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <Shapes className="h-8 w-8 mx-auto mb-2 opacity-60" />
                    <p>No runs yet for this process.</p>
                  </div>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>File</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Shape Match</TableHead>
                        <TableHead>ResultSets</TableHead>
                        <TableHead>Started</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {runs.results.map((run) => (
                        <TableRow key={run.id}>
                          <TableCell>{run.raw_dataset_filename || run.raw_dataset}</TableCell>
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
                          <TableCell>
                            {(run.resultset_ids || []).length
                              ? (run.resultset_ids || []).join(", ")
                              : "—"}
                          </TableCell>
                          <TableCell>{formatDate(run.started_at)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </DataLabWorkspace>
  );
}

function renderShapeDescription(shape?: any) {
  if (!shape) {
    return <p className="text-sm text-muted-foreground">No shape information available.</p>;
  }

  if (shape.file_type === "csv" || shape.file_type === "excel") {
    return (
      <div className="text-sm text-muted-foreground space-y-1">
        {shape.columns && (
          <p>
            Columns ({shape.column_count ?? shape.columns.length}):{" "}
            <span className="font-mono">{shape.columns.join(", ")}</span>
          </p>
        )}
        {shape.sheets && <p>Sheets: {shape.sheets.join(", ")}</p>}
      </div>
    );
  }

  if (shape.file_type === "pdf") {
    return (
      <div className="text-sm text-muted-foreground space-y-1">
        {shape.page_patterns && (
          <p>
            Page patterns: header {shape.page_patterns.header?.length ?? 0}, detail{" "}
            {shape.page_patterns.detail?.length ?? 0}, footer{" "}
            {shape.page_patterns.footer?.length ?? 0} (pages {shape.page_patterns.page_count})
          </p>
        )}
        {shape.tables && shape.tables.length > 0 && (
          <ul className="list-disc list-inside">
            {shape.tables.map((t: any, idx: number) => (
              <li key={idx} className="font-mono">
                Page {t.page}: {t.column_count} cols ({(t.columns || []).join(", ")}) rows≈
                {t.row_count_estimate}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  return <p className="text-sm text-muted-foreground">Shape: {JSON.stringify(shape)}</p>;
}

function renderUnitSelector(unit: any) {
  if (unit.kind === "excel_sheet" && unit.selector?.sheet) {
    return <>Sheet: {unit.selector.sheet}</>;
  }
  if ((unit.kind === "pdf_table" || unit.kind === "pdf_region") && unit.selector) {
    const pageSel = unit.selector.page_selector
      ? `${unit.selector.page_selector.type}${unit.selector.page_selector.value ? `:${unit.selector.page_selector.value}` : ""}`
      : "page?";
    const bbox = unit.selector.bbox ? ` bbox [${unit.selector.bbox.join(", ")}]` : "";
    return (
      <>
        Page selector: {pageSel}
        {bbox}
      </>
    );
  }
  return unit.selector ? JSON.stringify(unit.selector) : "No selector";
}
