import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabWidgetRender } from "@/hooks/use-datalab";
import { Loader2 } from "lucide-react";
import type { RenderedWidget } from "@/lib/moio-types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface WidgetRendererProps {
  widget: RenderedWidget;
}

export function WidgetRenderer({ widget }: WidgetRendererProps) {
  const { data: widgetData, isLoading } = useDataLabWidgetRender(widget.id, 30000);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{widget.name}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  const data = widgetData?.data || widget.data;

  switch (widget.type) {
    case "kpi":
      return (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{widget.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center">
              <div className="text-4xl font-bold">
                {data.formatted_value || data.value?.toLocaleString() || "N/A"}
              </div>
              {data.label && (
                <div className="text-sm text-muted-foreground mt-2">{data.label}</div>
              )}
              {data.aggregation && (
                <div className="text-xs text-muted-foreground mt-1">
                  {data.aggregation}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      );

    case "table":
      return (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{widget.name}</CardTitle>
          </CardHeader>
          <CardContent>
            {data.rows && data.rows.length > 0 ? (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {data.columns?.map((col: string) => (
                        <TableHead key={col}>{col}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.rows.map((row: Record<string, any>, idx: number) => (
                      <TableRow key={idx}>
                        {data.columns?.map((col: string) => (
                          <TableCell key={col} className="max-w-[200px] truncate">
                            {String(row[col] ?? "")}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {data.pagination && (
                  <div className="text-xs text-muted-foreground mt-2 text-center">
                    Page {data.pagination.page} of {data.pagination.total_pages} (
                    {data.pagination.total_rows} total rows)
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                No data available
              </div>
            )}
          </CardContent>
        </Card>
      );

    case "linechart":
    case "barchart":
    case "piechart":
      return (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{widget.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-8 text-muted-foreground">
              Chart visualization coming soon
              <div className="text-xs mt-2">
                {data.x_column && data.y_column && (
                  <>
                    {data.x_column} × {data.y_column}
                  </>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      );

    default:
      return (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{widget.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-8 text-muted-foreground">
              Unknown widget type: {widget.type}
            </div>
          </CardContent>
        </Card>
      );
  }
}
