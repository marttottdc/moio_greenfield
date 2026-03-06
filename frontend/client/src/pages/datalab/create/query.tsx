import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "wouter";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { useDataLabCRMViews, useDataLabCRMQuery } from "@/hooks/use-datalab";
import { Loader2, Play, ArrowLeft } from "lucide-react";

export default function CreateDatasetFromCRM() {
  const { toast } = useToast();
  const [location, setLocation] = useLocation();
  const { data: views, isLoading } = useDataLabCRMViews();
  const queryMutation = useDataLabCRMQuery();
  const [viewKey, setViewKey] = useState<string | undefined>();
  const [limit, setLimit] = useState<number>(500);
  const [filters, setFilters] = useState<Record<string, any>>({});

  const selectedView = useMemo(
    () => views?.find((v) => v.key === viewKey),
    [views, viewKey]
  );

  useEffect(() => {
    if (selectedView) {
      const defaultFilters = selectedView.default_filters_json || {};
      setFilters(defaultFilters);
    }
  }, [selectedView]);

  const handleRun = () => {
    if (!viewKey) {
      toast({ variant: "destructive", description: "Select a CRM view first." });
      return;
    }
    queryMutation.mutate(
      {
        view_key: viewKey,
        filters,
        limit,
        materialize: true,
      },
      {
        onSuccess: (res) => {
          toast({ description: "Dataset created from CRM" });
          setLocation(`/datalab/dataset/${res.resultset_id}`);
        },
        onError: (err: any) => {
          toast({
            variant: "destructive",
            description: err?.message || "CRM query failed",
          });
        },
      }
    );
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Create Dataset from CRM</h1>
          <p className="text-muted-foreground mt-2">
            Select a CRM view, optionally adjust filters, and materialize as a dataset.
          </p>
        </div>
        <Link href="/datalab">
          <Button variant="ghost">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to datasets
          </Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>CRM View</CardTitle>
          <CardDescription>Select a view to query</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {isLoading ? (
            <div className="flex items-center text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
              Loading views...
            </div>
          ) : (
            <Select value={viewKey} onValueChange={(v) => setViewKey(v)}>
              <SelectTrigger className="w-full md:w-80">
                <SelectValue placeholder="Choose a CRM view" />
              </SelectTrigger>
              <SelectContent>
                {views?.map((v) => (
                  <SelectItem key={v.key} value={v.key}>
                    {v.label || v.key}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {selectedView && (
            <div className="text-xs text-muted-foreground">
              {selectedView.description || "No description"}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
          <CardDescription>Set optional filters (based on view)</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Limit</Label>
            <Input
              type="number"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            />
          </div>
          {/* Simple key-value filters for now */}
          <div className="space-y-2">
            <Label>Filters (JSON)</Label>
            <Input
              value={JSON.stringify(filters)}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value || "{}");
                  setFilters(parsed);
                } catch {
                  // ignore
                }
              }}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Create</CardTitle>
          <CardDescription>Run query and materialize as dataset</CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={handleRun} disabled={queryMutation.isPending || !viewKey}>
            {queryMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Creating...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" />
                Create Dataset
              </>
            )}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
