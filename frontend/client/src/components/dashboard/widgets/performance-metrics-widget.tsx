import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Cell
} from "recharts";
import { TrendingUp, TrendingDown } from "lucide-react";

const DEMO_METRICS_DATA = [
  { name: "Sent", value: 867, target: 900, color: "#58a6ff" },
  { name: "Delivered", value: 823, target: 850, color: "#22c55e" },
  { name: "Opened", value: 412, target: 500, color: "#ffba08" },
  { name: "Clicked", value: 156, target: 200, color: "#a855f7" },
  { name: "Responded", value: 89, target: 100, color: "#ef4444" },
];

const DEMO_COMPARISON = [
  { label: "Open Rate", current: 50.1, previous: 45.2, unit: "%" },
  { label: "Click Rate", current: 19.0, previous: 21.5, unit: "%" },
  { label: "Response Rate", current: 10.8, previous: 8.9, unit: "%" },
];

export function PerformanceMetricsWidget() {
  return (
    <GlassPanel className="p-6" data-testid="widget-performance-metrics">
      <div className="flex items-center justify-between mb-4">
        <Subheading>Performance Metrics</Subheading>
        <span className="text-xs text-muted-foreground opacity-60">[Demo Data]</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <p className="text-sm font-medium mb-3">Campaign Funnel</p>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={DEMO_METRICS_DATA} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" horizontal={false} />
                <XAxis type="number" className="text-xs" />
                <YAxis type="category" dataKey="name" className="text-xs" width={80} />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: 'hsl(var(--background))', 
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                  }} 
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {DEMO_METRICS_DATA.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <p className="text-sm font-medium mb-3">Week over Week</p>
          <div className="space-y-3">
            {DEMO_COMPARISON.map((metric) => {
              const change = metric.current - metric.previous;
              const isPositive = change > 0;
              return (
                <div 
                  key={metric.label} 
                  className="flex items-center justify-between p-3 rounded-lg border"
                >
                  <div>
                    <p className="text-sm font-medium">{metric.label}</p>
                    <p className="text-2xl font-bold">
                      {metric.current}{metric.unit}
                    </p>
                  </div>
                  <div className={`flex items-center gap-1 text-sm ${
                    isPositive ? "text-green-600" : "text-red-600"
                  }`}>
                    {isPositive ? (
                      <TrendingUp className="h-4 w-4" />
                    ) : (
                      <TrendingDown className="h-4 w-4" />
                    )}
                    <span>
                      {isPositive ? "+" : ""}{change.toFixed(1)}{metric.unit}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </GlassPanel>
  );
}
