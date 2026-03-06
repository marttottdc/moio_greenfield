import { Link } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabPanels } from "@/hooks/use-datalab";
import { LayoutDashboard, Plus, Loader2, Eye, Edit } from "lucide-react";
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

export default function DataLabPanels() {
  const { data: panels, isLoading, error } = useDataLabPanels();

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Panels</h1>
            <p className="text-muted-foreground mt-2">
              Create custom dashboards and visualizations
            </p>
          </div>
          <Link href="/datalab/panels/new">
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              New Panel
            </Button>
          </Link>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>All Panels</CardTitle>
            <CardDescription>
              {panels?.length ? `${panels.length} total panels` : "No panels yet"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="text-center py-8">
                <div className="text-destructive mb-2">Failed to load panels</div>
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
            ) : !panels || panels.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <LayoutDashboard className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No panels created yet</p>
                <p className="text-sm mt-2">Create your first dashboard panel to get started</p>
                <Link href="/datalab/panels/new">
                  <Button className="mt-4">
                    <Plus className="mr-2 h-4 w-4" />
                    New Panel
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {panels.map((panel) => (
                  <Card key={panel.id} className="hover:border-primary transition-colors">
                    <CardHeader>
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <CardTitle className="text-lg">{panel.name}</CardTitle>
                          {panel.description && (
                            <CardDescription className="mt-1">
                              {panel.description}
                            </CardDescription>
                          )}
                        </div>
                        {panel.is_public ? (
                          <Badge variant="default">Public</Badge>
                        ) : (
                          <Badge variant="secondary">Private</Badge>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 mb-4">
                        <div className="text-sm text-muted-foreground">
                          {panel.widget_count} widgets
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Created {formatDate(panel.created_at)}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Link href={`/datalab/panels/${panel.id}`} className="flex-1">
                          <Button variant="outline" className="w-full" size="sm">
                            <Eye className="mr-2 h-4 w-4" />
                            View
                          </Button>
                        </Link>
                        <Link href={`/datalab/panels/${panel.id}/edit`} className="flex-1">
                          <Button variant="outline" className="w-full" size="sm">
                            <Edit className="mr-2 h-4 w-4" />
                            Edit
                          </Button>
                        </Link>
                      </div>
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
