import { useState } from "react";
import { useParams, Link, useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDataLabCRMView, useDataLabCRMQuery } from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, Play, Database } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";

export default function CRMQueryBuilder() {
  const { viewKey } = useParams<{ viewKey: string }>();
  const [, setLocation] = useLocation();
  // Decode the viewKey from URL (it's URL encoded to handle dots)
  const decodedKey = viewKey ? decodeURIComponent(viewKey) : undefined;
  const { data: view, isLoading: viewLoading, error: viewError } = useDataLabCRMView(decodedKey);
  const queryMutation = useDataLabCRMQuery();
  const { toast } = useToast();

  const [filters, setFilters] = useState<Record<string, any>>({});
  const [limit, setLimit] = useState<number | undefined>(1000);
  const [materialize, setMaterialize] = useState(false);

  const handleFilterChange = (key: string, value: any) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value || undefined,
    }));
  };

  const handleExecute = async () => {
    if (!view?.key) return;

    try {
      const result = await queryMutation.mutateAsync({
        view_key: view.key,
        filters: Object.keys(filters).length > 0 ? filters : undefined,
        limit,
        materialize,
      });

      toast({
        title: "Query executed",
        description: `Retrieved ${result.row_count.toLocaleString()} rows successfully.`,
      });

      setLocation(`/datalab/resultsets/${result.resultset_id}`);
    } catch (error) {
      toast({
        title: "Query failed",
        description: error instanceof Error ? error.message : "Failed to execute query",
        variant: "destructive",
      });
    }
  };

  if (viewLoading) {
    return (
      <DataLabWorkspace>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </DataLabWorkspace>
    );
  }

  if (viewError) {
    return (
      <DataLabWorkspace>
        <div className="text-center py-12">
          <Database className="h-12 w-12 mx-auto mb-4 opacity-50 text-muted-foreground" />
          <h2 className="text-2xl font-bold mb-2">View Not Found</h2>
          <p className="text-muted-foreground mb-2">
            The CRM view "{decodedKey}" could not be found.
          </p>
          <p className="text-sm text-muted-foreground mb-4">
            {viewError instanceof Error ? viewError.message : "Unknown error"}
          </p>
          <Link href="/datalab/datasources">
            <Button>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Data Sources
            </Button>
          </Link>
        </div>
      </DataLabWorkspace>
    );
  }

  if (!view) {
    return (
      <DataLabWorkspace>
        <div className="text-center py-12">
          <Database className="h-12 w-12 mx-auto mb-4 opacity-50 text-muted-foreground" />
          <h2 className="text-2xl font-bold mb-2">View Not Found</h2>
          <p className="text-muted-foreground mb-4">
            The CRM view "{decodedKey}" doesn't exist or couldn't be loaded.
          </p>
          <Link href="/datalab/datasources">
            <Button>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Data Sources
            </Button>
          </Link>
        </div>
      </DataLabWorkspace>
    );
  }

  return (
    <DataLabWorkspace>
      <div className="space-y-6 max-w-4xl">
        <div>
          <Link href="/datalab/datasources">
            <Button variant="ghost" size="sm" className="mb-2">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">{view.label}</h1>
          <p className="text-muted-foreground mt-2">{view.description || view.key}</p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle>Query Configuration</CardTitle>
              <CardDescription>Configure filters and options for your query</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Filters */}
              {view.allowed_filters_json.length > 0 ? (
                <div>
                  <Label className="text-base font-semibold mb-4 block">Filters</Label>
                  <div className="space-y-4">
                    {view.allowed_filters_json.map((filterKey) => {
                      // Try to infer filter type from view schema
                      const schemaField = view.schema_json.find((col) => col.name === filterKey);
                      const fieldType = schemaField?.type || "string";

                      return (
                        <div key={filterKey}>
                          <Label htmlFor={filterKey} className="capitalize">
                            {filterKey.replace(/_/g, " ")}
                          </Label>
                          {fieldType === "date" || filterKey.includes("date") ? (
                            <Input
                              id={filterKey}
                              type="date"
                              value={filters[filterKey] || ""}
                              onChange={(e) => handleFilterChange(filterKey, e.target.value)}
                              placeholder={`Filter by ${filterKey}`}
                            />
                          ) : fieldType === "boolean" ? (
                            <Select
                              value={filters[filterKey] || ""}
                              onValueChange={(value) => handleFilterChange(filterKey, value)}
                            >
                              <SelectTrigger>
                                <SelectValue placeholder={`Select ${filterKey}`} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="">All</SelectItem>
                                <SelectItem value="true">True</SelectItem>
                                <SelectItem value="false">False</SelectItem>
                              </SelectContent>
                            </Select>
                          ) : (
                            <Input
                              id={filterKey}
                              value={filters[filterKey] || ""}
                              onChange={(e) => handleFilterChange(filterKey, e.target.value)}
                              placeholder={`Filter by ${filterKey}`}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  No filters available for this view
                </div>
              )}

              {/* Query Options */}
              <div className="space-y-4 pt-4 border-t">
                <div>
                  <Label htmlFor="limit">Row Limit</Label>
                  <Input
                    id="limit"
                    type="number"
                    min={1}
                    max={10000}
                    value={limit || ""}
                    onChange={(e) =>
                      setLimit(e.target.value ? parseInt(e.target.value) : undefined)
                    }
                    placeholder="1000"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Maximum number of rows to retrieve (default: 1000)
                  </p>
                </div>

                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="materialize"
                    checked={materialize}
                    onChange={(e) => setMaterialize(e.target.checked)}
                    className="rounded border-gray-300"
                  />
                  <Label htmlFor="materialize" className="cursor-pointer">
                    Force materialization to Parquet
                  </Label>
                </div>
                <p className="text-xs text-muted-foreground">
                  Materialize large datasets to Parquet storage for better performance
                </p>
              </div>

              <Button
                onClick={handleExecute}
                disabled={queryMutation.isPending}
                className="w-full"
                size="lg"
              >
                {queryMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Executing Query...
                  </>
                ) : (
                  <>
                    <Play className="mr-2 h-4 w-4" />
                    Execute Query
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Schema</CardTitle>
              <CardDescription>Available columns</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {view.schema_json.map((col, idx) => (
                  <div key={idx} className="p-2 border rounded text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{col.name}</span>
                      <Badge variant="outline" className="text-xs">
                        {col.type}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Default Filters Info */}
        {view.default_filters_json && Object.keys(view.default_filters_json).length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Default Filters</CardTitle>
              <CardDescription>These filters are applied by default</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(view.default_filters_json).map(([key, value]) => (
                  <div key={key} className="text-sm">
                    <span className="font-medium">{key}:</span>{" "}
                    <span className="text-muted-foreground">{String(value)}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </DataLabWorkspace>
  );
}
