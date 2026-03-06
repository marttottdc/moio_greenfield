import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabCRMViews } from "@/hooks/use-datalab";
import { Database, Search, Loader2, ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useState } from "react";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";

export default function DataLabDataSources() {
  const { data: views, isLoading, error } = useDataLabCRMViews();
  const [searchQuery, setSearchQuery] = useState("");

  const filteredViews = views?.filter((view) =>
    view.label.toLowerCase().includes(searchQuery.toLowerCase()) ||
    view.key.toLowerCase().includes(searchQuery.toLowerCase()) ||
    view.description?.toLowerCase().includes(searchQuery.toLowerCase())
  ) || [];

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Data Sources</h1>
            <p className="text-muted-foreground mt-2">
              Query CRM data and external sources
            </p>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>CRM Views</CardTitle>
            <CardDescription>
              Available CRM data views you can query
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search views..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>

            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="text-center py-8">
                <div className="text-destructive mb-2">Failed to load CRM views</div>
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
            ) : !views || views.length === 0 ? (
              <div className="space-y-4">
                <div className="text-center py-8 text-muted-foreground">
                  <Database className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p className="font-medium">No active CRM views found</p>
                  <p className="text-sm mt-2">
                    The API returned an empty list. This could mean:
                  </p>
                  <ul className="text-sm mt-2 text-left max-w-md mx-auto space-y-1 list-disc list-inside">
                    <li>No views are configured for your tenant</li>
                    <li>All views are currently inactive</li>
                    <li>Views need to be registered in the backend</li>
                  </ul>
                </div>
                <Card className="border-blue-200 bg-blue-50/50 dark:bg-blue-950/20 dark:border-blue-900">
                  <CardHeader>
                    <CardTitle className="text-base">Expected Default CRM Views</CardTitle>
                    <CardDescription>
                      These views are typically available by default in Data Lab
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3 text-sm">
                      <div className="flex items-start gap-3">
                        <Database className="h-4 w-4 mt-0.5 text-muted-foreground" />
                        <div>
                          <div className="font-medium">crm.deals.v1</div>
                          <div className="text-muted-foreground">All active (open) deals</div>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <Database className="h-4 w-4 mt-0.5 text-muted-foreground" />
                        <div>
                          <div className="font-medium">crm.sales.by_day.v1</div>
                          <div className="text-muted-foreground">Daily aggregated sales (won deals)</div>
                        </div>
                      </div>
                      <div className="flex items-start gap-3">
                        <Database className="h-4 w-4 mt-0.5 text-muted-foreground" />
                        <div>
                          <div className="font-medium">crm.contacts.with_deals.v1</div>
                          <div className="text-muted-foreground">Contacts with associated deals</div>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3 p-2 bg-muted rounded text-xs">
                      <p className="text-muted-foreground">
                        <strong>Note:</strong> View keys are versioned (e.g., <code>.v1</code>). 
                        Only active views for your tenant are returned, ordered by key.
                      </p>
                    </div>
                    <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900 rounded-lg">
                      <p className="text-xs text-amber-900 dark:text-amber-200">
                        <strong>Note:</strong> If you don't see any views, check that:
                      </p>
                      <ul className="text-xs text-amber-800 dark:text-amber-300 mt-2 ml-4 list-disc space-y-1">
                        <li>The Data Lab backend is properly configured</li>
                        <li>CRM views are registered in your backend</li>
                        <li>You have the necessary permissions</li>
                      </ul>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ) : filteredViews.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <p>No views match your search</p>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {filteredViews.map((view) => (
                  <Card key={view.id} className="hover:border-primary transition-colors">
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <CardTitle className="text-lg">{view.label}</CardTitle>
                          <CardDescription className="mt-1">
                            {view.key}
                          </CardDescription>
                        </div>
                        {view.is_active ? (
                          <Badge variant="default">Active</Badge>
                        ) : (
                          <Badge variant="secondary">Inactive</Badge>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      {view.description && (
                        <p className="text-sm text-muted-foreground mb-4">
                          {view.description}
                        </p>
                      )}
                      <div className="space-y-2 mb-4">
                        <div className="text-xs text-muted-foreground">
                          {view.schema_json.length} columns available
                        </div>
                        {view.allowed_filters_json.length > 0 && (
                          <div className="text-xs text-muted-foreground">
                            {view.allowed_filters_json.length} filterable fields
                          </div>
                        )}
                      </div>
                      <Link href={`/datalab/datasources/${encodeURIComponent(view.key)}/query`}>
                        <Button className="w-full">
                          Query View
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                      </Link>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </DataLabWorkspace>
  );
}
