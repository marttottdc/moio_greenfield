import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageLayout } from "@/components/layout/page-layout";
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, 
  PieChart, Pie, Cell, Legend, AreaChart, Area 
} from "recharts";
import { 
  TrendingUp, TrendingDown, DollarSign, Target, Trophy, XCircle, 
  ArrowLeft, Clock, Users, Activity
} from "lucide-react";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";

interface PipelineStage {
  id: string;
  name: string;
  order: number;
  probability: number;
  is_won?: boolean;
  is_lost?: boolean;
  is_won_stage?: boolean;
  is_lost_stage?: boolean;
  color: string;
}

interface Pipeline {
  id: string;
  name: string;
  is_default?: boolean;
  stages: PipelineStage[];
}

interface Deal {
  id: string;
  title: string;
  value?: number | null;
  currency?: string;
  stage?: string;
  stage_id?: string;
  stage_name?: string;
  priority?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
}

interface DealsResponse {
  deals?: Deal[];
  results?: Deal[];
}

interface PipelinesResponse {
  pipelines?: Pipeline[];
}

const COLORS = ["#58a6ff", "#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#6366f1", "#14b8a6"];

export default function DealsAnalytics() {
  const pipelinesQuery = useQuery<PipelinesResponse>({
    queryKey: [apiV1("/crm/deals/pipelines/")],
    queryFn: () => fetchJson<PipelinesResponse>(apiV1("/crm/deals/pipelines/")),
  });

  const dealsQuery = useQuery<DealsResponse>({
    queryKey: [apiV1("/crm/deals/"), "all"],
    queryFn: () => fetchJson<DealsResponse>(apiV1("/crm/deals/")),
  });

  const pipelines = pipelinesQuery.data?.pipelines ?? [];
  const activePipeline = pipelines.find(p => p.is_default) || pipelines[0];
  const allStages = activePipeline?.stages?.sort((a, b) => a.order - b.order) ?? [];
  
  const deals = useMemo(() => {
    const data = dealsQuery.data;
    let rawDeals: Deal[] = [];
    if (Array.isArray(data)) {
      rawDeals = data;
    } else {
      rawDeals = data?.deals ?? data?.results ?? [];
    }
    return rawDeals.map(deal => ({
      ...deal,
      value: typeof deal.value === 'string' ? parseFloat(deal.value) : (deal.value || 0),
    }));
  }, [dealsQuery.data]);

  const activeStages = allStages.filter(s => !s.is_won && !s.is_lost && !s.is_won_stage && !s.is_lost_stage);
  const wonStage = allStages.find(s => s.is_won || s.is_won_stage);
  const lostStage = allStages.find(s => s.is_lost || s.is_lost_stage);

  const wonDeals = deals.filter(d => {
    const stageId = d.stage_id ?? d.stage;
    return stageId === wonStage?.id || stageId === wonStage?.name;
  });
  
  const lostDeals = deals.filter(d => {
    const stageId = d.stage_id ?? d.stage;
    return stageId === lostStage?.id || stageId === lostStage?.name;
  });
  
  const activeDeals = deals.filter(d => {
    const stageId = d.stage_id ?? d.stage;
    return activeStages.some(s => s.id === stageId || s.name === stageId);
  });

  const totalValue = deals.reduce((sum, d) => sum + (d.value || 0), 0);
  const wonValue = wonDeals.reduce((sum, d) => sum + (d.value || 0), 0);
  const activeValue = activeDeals.reduce((sum, d) => sum + (d.value || 0), 0);
  const avgDealValue = deals.length > 0 ? totalValue / deals.length : 0;
  const winRate = (wonDeals.length + lostDeals.length) > 0 
    ? (wonDeals.length / (wonDeals.length + lostDeals.length)) * 100 
    : 0;

  const dealsByStage = useMemo(() => {
    return activeStages.map(stage => {
      const stageDeals = deals.filter(d => {
        const dealStage = d.stage_id ?? d.stage;
        return dealStage === stage.id || dealStage === stage.name;
      });
      const value = stageDeals.reduce((sum, d) => sum + (d.value || 0), 0);
      return {
        name: stage.name.length > 12 ? stage.name.slice(0, 12) + "..." : stage.name,
        fullName: stage.name,
        deals: stageDeals.length,
        value,
        probability: stage.probability,
      };
    });
  }, [deals, activeStages]);

  const priorityData = useMemo(() => {
    const priorities = ["low", "medium", "high", "urgent"];
    return priorities.map(priority => ({
      name: priority.charAt(0).toUpperCase() + priority.slice(1),
      count: deals.filter(d => d.priority === priority).length,
      value: deals.filter(d => d.priority === priority).reduce((sum, d) => sum + (d.value || 0), 0),
    })).filter(p => p.count > 0);
  }, [deals]);

  const winLossData = [
    { name: "Won", value: wonDeals.length, color: "#10b981" },
    { name: "Lost", value: lostDeals.length, color: "#ef4444" },
    { name: "Active", value: activeDeals.length, color: "#58a6ff" },
  ].filter(d => d.value > 0);

  const isLoading = pipelinesQuery.isLoading || dealsQuery.isLoading;

  if (isLoading) {
    return (
      <PageLayout title="Deal Analytics" description="Analyze your sales performance">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-6">
          {[1, 2, 3, 4].map(i => (
            <Card key={i}>
              <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-32 mb-2" />
                <Skeleton className="h-3 w-20" />
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Card><CardContent className="pt-6"><Skeleton className="h-[300px]" /></CardContent></Card>
          <Card><CardContent className="pt-6"><Skeleton className="h-[300px]" /></CardContent></Card>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout 
      title="Deal Analytics" 
      description="Analyze your sales performance and pipeline health"
    >
      <div className="mb-4">
        <Link href="/deals">
          <Button variant="outline" size="sm" data-testid="button-back-to-deals">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Deals
          </Button>
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 mb-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Pipeline Value</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold" data-testid="text-total-pipeline-value">
              {totalValue.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })}
            </div>
            <p className="text-xs text-muted-foreground">
              {deals.length} total deals
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Won Revenue</CardTitle>
            <Trophy className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600" data-testid="text-won-revenue">
              {wonValue.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })}
            </div>
            <p className="text-xs text-muted-foreground">
              {wonDeals.length} won deals
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Win Rate</CardTitle>
            {winRate >= 50 ? <TrendingUp className="h-4 w-4 text-green-500" /> : <TrendingDown className="h-4 w-4 text-red-500" />}
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${winRate >= 50 ? "text-green-600" : "text-amber-600"}`} data-testid="text-win-rate">
              {winRate.toFixed(1)}%
            </div>
            <p className="text-xs text-muted-foreground">
              {wonDeals.length} won / {lostDeals.length} lost
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Deal Value</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold" data-testid="text-avg-deal-value">
              {avgDealValue.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })}
            </div>
            <p className="text-xs text-muted-foreground">
              Per deal average
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2 mb-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Deals by Stage</CardTitle>
            <CardDescription>Number of deals in each pipeline stage</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={dealsByStage} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis 
                  dataKey="name" 
                  className="text-xs" 
                  angle={-45} 
                  textAnchor="end" 
                  height={60}
                  tick={{ fontSize: 11 }}
                />
                <YAxis className="text-xs" />
                <Tooltip 
                  contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
                  formatter={(value: number, name: string) => [value, name === "deals" ? "Deals" : "Value"]}
                  labelFormatter={(label) => dealsByStage.find(s => s.name === label)?.fullName || label}
                />
                <Bar dataKey="deals" fill="#58a6ff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Value by Stage</CardTitle>
            <CardDescription>Total deal value in each stage</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={dealsByStage} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis 
                  dataKey="name" 
                  className="text-xs" 
                  angle={-45} 
                  textAnchor="end" 
                  height={60}
                  tick={{ fontSize: 11 }}
                />
                <YAxis 
                  className="text-xs" 
                  tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
                />
                <Tooltip 
                  contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
                  formatter={(value: number) => [
                    value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }),
                    "Value"
                  ]}
                />
                <Area type="monotone" dataKey="value" fill="#58a6ff" fillOpacity={0.3} stroke="#58a6ff" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2 mb-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Deal Status Distribution</CardTitle>
            <CardDescription>Won, Lost, and Active deals</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={winLossData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={false}
                >
                  {winLossData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
                />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Deals by Priority</CardTitle>
            <CardDescription>Distribution across priority levels</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={priorityData} layout="vertical" margin={{ top: 20, right: 30, left: 60, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis type="number" className="text-xs" />
                <YAxis dataKey="name" type="category" className="text-xs" width={60} />
                <Tooltip 
                  contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
                  formatter={(value: number, name: string) => [
                    name === "count" ? value : value.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 }),
                    name === "count" ? "Deals" : "Value"
                  ]}
                />
                <Bar dataKey="count" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Pipeline Summary</CardTitle>
          <CardDescription>Quick overview of your sales pipeline</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/50">
              <div className="p-3 rounded-full bg-blue-500/10">
                <Activity className="h-6 w-6 text-blue-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{activeDeals.length}</p>
                <p className="text-sm text-muted-foreground">Active Deals</p>
              </div>
            </div>
            <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/50">
              <div className="p-3 rounded-full bg-amber-500/10">
                <Clock className="h-6 w-6 text-amber-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {activeValue.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 })}
                </p>
                <p className="text-sm text-muted-foreground">Active Pipeline Value</p>
              </div>
            </div>
            <div className="flex items-center gap-4 p-4 rounded-lg bg-muted/50">
              <div className="p-3 rounded-full bg-green-500/10">
                <Users className="h-6 w-6 text-green-500" />
              </div>
              <div>
                <p className="text-2xl font-bold">{activeStages.length}</p>
                <p className="text-sm text-muted-foreground">Active Stages</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </PageLayout>
  );
}
