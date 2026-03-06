import { useMemo, useState } from "react";
import { Link } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Loader2, Eye, Camera, Wand2, Workflow, BarChart3 } from "lucide-react";
import { formatDate } from "@/lib/utils";
import { useDataLabResultSets, useDataLabResultSetMaterialize, useDataLabSnapshots } from "@/hooks/use-datalab";

export default function DataLabDatasets() {
  const [tab, setTab] = useState<"resultsets" | "snapshots">("resultsets");
  const { data: resultsets, isLoading: isLoadingResultsets } = useDataLabResultSets(undefined, 1, 50);
  const { data: snapshots, isLoading: isLoadingSnapshots } = useDataLabSnapshots();
  const materializeMutation = useDataLabResultSetMaterialize();

  const items = useMemo(() => {
    if (tab === "snapshots") {
      return (snapshots || []).map((s) => ({
        id: s.id,
        name: s.name,
        origin: s.resultset.origin,
        row_count: s.resultset.row_count,
        columns: s.resultset.schema_json?.length ?? 0,
        storage: "snapshot",
        created_at: s.created_at,
        viewHref: `/datalab/datasets/${s.resultset.id}`,
        canMaterialize: false,
      }));
    }

    return (resultsets?.results || []).map((r) => ({
      id: r.id,
      name: r.name || "Unnamed Dataset",
      origin: r.origin,
      row_count: r.row_count,
      columns: r.schema_json?.length ?? 0,
      storage: r.storage,
      created_at: r.created_at,
      viewHref: `/datalab/datasets/${r.id}`,
      canMaterialize: r.storage === "memory",
    }));
  }, [resultsets, snapshots, tab]);

  const isLoading = tab === "snapshots" ? isLoadingSnapshots : isLoadingResultsets;

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">Datasets</h1>
              <p className="text-muted-foreground mt-2">
                Central hub for ResultSets and Snapshots. Everything in Data Lab exists to create or use a dataset.
              </p>
            </div>
          </div>

          <Card>
            <CardHeader className="py-3">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <CardTitle className="text-lg">All Datasets</CardTitle>
                  <CardDescription className="text-sm">
                    {tab === "snapshots"
                      ? `${snapshots?.length ?? 0} snapshots`
                      : `${resultsets?.count ?? 0} resultsets`}
                  </CardDescription>
                </div>
                <Tabs value={tab} onValueChange={(v) => setTab(v as any)}>
                  <TabsList>
                    <TabsTrigger value="resultsets">ResultSets</TabsTrigger>
                    <TabsTrigger value="snapshots">Snapshots</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {isLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : items.length === 0 ? (
                <div className="text-center py-10 text-muted-foreground">
                  No datasets yet. Create one from Files, CRM, Imports, Scripts, or Pipelines.
                </div>
              ) : (
                <div className="rounded-md border overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-muted">
                      <tr className="border-b">
                        <th className="p-2 text-left font-medium">Name</th>
                        <th className="p-2 text-left font-medium">Origin</th>
                        <th className="p-2 text-right font-medium">Rows</th>
                        <th className="p-2 text-right font-medium">Cols</th>
                        <th className="p-2 text-left font-medium">Storage</th>
                        <th className="p-2 text-left font-medium">Created</th>
                        <th className="p-2 text-right font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((d) => (
                        <tr key={d.id} className="border-b last:border-b-0">
                          <td className="p-2 font-medium max-w-[260px] truncate" title={d.name}>
                            {d.name}
                          </td>
                          <td className="p-2">
                            <Badge variant="outline">{d.origin}</Badge>
                          </td>
                          <td className="p-2 text-right font-mono">{(d.row_count ?? 0).toLocaleString()}</td>
                          <td className="p-2 text-right font-mono">{d.columns}</td>
                          <td className="p-2">
                            <Badge variant={d.storage === "parquet" ? "default" : "secondary"}>{d.storage}</Badge>
                          </td>
                          <td className="p-2">{formatDate(d.created_at)}</td>
                          <td className="p-2 text-right whitespace-nowrap space-x-1">
                            <Link href={d.viewHref}>
                              <Button size="sm" variant="ghost">
                                <Eye className="mr-2 h-4 w-4" />
                                View
                              </Button>
                            </Link>

                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span>
                                  <Button size="sm" variant="ghost" disabled>
                                    <BarChart3 className="mr-2 h-4 w-4" />
                                    Visualize
                                  </Button>
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>Coming soon: Dataset → Visualize → Panel</TooltipContent>
                            </Tooltip>

                            <Tooltip>
                              <TooltipTrigger asChild>
                                <span>
                                  <Button size="sm" variant="ghost" disabled>
                                    <Workflow className="mr-2 h-4 w-4" />
                                    Use in process
                                  </Button>
                                </span>
                              </TooltipTrigger>
                              <TooltipContent>Coming soon: Use this dataset in Scripts/Pipelines/Flows</TooltipContent>
                            </Tooltip>

                            {d.canMaterialize ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                disabled={materializeMutation.isPending}
                                onClick={() => materializeMutation.mutate(d.id)}
                              >
                                <Wand2 className="mr-2 h-4 w-4" />
                                Materialize
                              </Button>
                            ) : (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span>
                                    <Button size="sm" variant="ghost" disabled>
                                      <Camera className="mr-2 h-4 w-4" />
                                      Snapshot
                                    </Button>
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>Create snapshots from Dataset Detail</TooltipContent>
                              </Tooltip>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
      </div>
    </DataLabWorkspace>
  );
}

