import { useParams, Link } from "wouter";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabPanelRender } from "@/hooks/use-datalab";
import { ArrowLeft, Loader2, LayoutDashboard, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { WidgetRenderer } from "@/components/datalab/widget-renderer";

export default function PanelViewer() {
  const { id } = useParams<{ id: string }>();
  const { data: panelData, isLoading, refetch } = useDataLabPanelRender(id);

  if (isLoading) {
    return (
      <PageLayout>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageLayout>
    );
  }

  if (!panelData || !panelData.panel) {
    return (
      <PageLayout>
        <div className="text-center py-12">
          <LayoutDashboard className="h-12 w-12 mx-auto mb-4 opacity-50 text-muted-foreground" />
          <h2 className="text-2xl font-bold mb-2">Panel Not Found</h2>
          <p className="text-muted-foreground mb-4">
            The panel you're looking for doesn't exist or has been deleted.
          </p>
          <Link href="/datalab/panels">
            <Button>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Panels
            </Button>
          </Link>
        </div>
      </PageLayout>
    );
  }

  const { panel, widgets } = panelData;

  return (
    <PageLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <Link href="/datalab/panels">
              <Button variant="ghost" size="sm" className="mb-2">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Button>
            </Link>
            <h1 className="text-3xl font-bold">{panel.name}</h1>
            {panel.description && (
              <p className="text-muted-foreground mt-2">{panel.description}</p>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => refetch()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
            {panel.is_public && <Badge variant="default">Public</Badge>}
          </div>
        </div>

        {widgets.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <LayoutDashboard className="h-12 w-12 mx-auto mb-4 opacity-50 text-muted-foreground" />
              <p className="text-muted-foreground">No widgets in this panel</p>
              <Link href={`/datalab/panels/${panel.id}/edit`}>
                <Button className="mt-4">Add Widgets</Button>
              </Link>
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4" style={{
            gridTemplateColumns: `repeat(${panel.layout_json?.grid?.columns || 12}, minmax(0, 1fr))`,
          }}>
            {widgets.map((widget) => (
              <div
                key={widget.id}
                className="col-span-full"
                style={{
                  gridColumn: `span ${widget.position.width}`,
                  gridRow: `span ${widget.position.height}`,
                }}
              >
                <WidgetRenderer widget={widget} />
              </div>
            ))}
          </div>
        )}
      </div>
    </PageLayout>
  );
}
