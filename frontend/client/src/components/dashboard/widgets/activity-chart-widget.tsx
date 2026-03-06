import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  Legend
} from "recharts";

const DEMO_ACTIVITY_DATA = [
  { date: "Mon", sent: 120, opened: 89, clicked: 45 },
  { date: "Tue", sent: 145, opened: 102, clicked: 58 },
  { date: "Wed", sent: 98, opened: 78, clicked: 32 },
  { date: "Thu", sent: 187, opened: 145, clicked: 89 },
  { date: "Fri", sent: 210, opened: 168, clicked: 95 },
  { date: "Sat", sent: 65, opened: 48, clicked: 22 },
  { date: "Sun", sent: 42, opened: 31, clicked: 15 },
];

export function ActivityChartWidget() {
  return (
    <GlassPanel className="p-6" data-testid="widget-activity-chart">
      <div className="flex items-center justify-between mb-4">
        <Subheading>Activity & Engagement</Subheading>
        <span className="text-xs text-muted-foreground opacity-60">[Demo Data]</span>
      </div>

      <div className="h-[250px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={DEMO_ACTIVITY_DATA} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="colorSent" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#58a6ff" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#58a6ff" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorOpened" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ffba08" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#ffba08" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorClicked" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis dataKey="date" className="text-xs" />
            <YAxis className="text-xs" />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'hsl(var(--background))', 
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
              }} 
            />
            <Legend />
            <Area
              type="monotone"
              dataKey="sent"
              stroke="#58a6ff"
              fillOpacity={1}
              fill="url(#colorSent)"
              name="Sent"
            />
            <Area
              type="monotone"
              dataKey="opened"
              stroke="#ffba08"
              fillOpacity={1}
              fill="url(#colorOpened)"
              name="Opened"
            />
            <Area
              type="monotone"
              dataKey="clicked"
              stroke="#22c55e"
              fillOpacity={1}
              fill="url(#colorClicked)"
              name="Clicked"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </GlassPanel>
  );
}
