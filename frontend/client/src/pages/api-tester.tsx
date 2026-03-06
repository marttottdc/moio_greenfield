import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { runAllTests, generateMarkdownReport, type TestCategory } from "@/lib/apiTester";
import { Download, PlayCircle, Loader2, RefreshCcw } from "lucide-react";
import { fetchJson } from "@/lib/queryClient";
import { apiV1 } from "@/lib/api";
import type { Campaign as CampaignRecord } from "@/lib/moio-types";
import { WSDebugVisualizer, EventLog } from "@/components/ws-debug-visualizer";

interface CampaignListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: CampaignRecord[];
}

interface CampaignUseCaseResult {
  ok: boolean;
  count: number;
  timestamp: string;
  sample?: CampaignRecord;
  error?: string;
}

const CAMPAIGNS_PATH = apiV1("/campaigns/");

export default function ApiTester() {
  const [isRunning, setIsRunning] = useState(false);
  const [testResults, setTestResults] = useState<TestCategory[] | null>(null);
  const [report, setReport] = useState<string>("");
  const [campaignUseCaseRunning, setCampaignUseCaseRunning] = useState(false);
  const [campaignUseCaseResult, setCampaignUseCaseResult] = useState<CampaignUseCaseResult | null>(null);
  const [wsEvents, setWsEvents] = useState<EventLog[]>([]);

  const handleRunTests = async () => {
    setIsRunning(true);
    setTestResults(null);
    setReport("");

    try {
      const results = await runAllTests();
      setTestResults(results);
      
      const markdown = generateMarkdownReport(results);
      setReport(markdown);
    } catch {
      // Failed to run tests
    } finally {
      setIsRunning(false);
    }
  };

  const handleCampaignUseCase = async () => {
    setCampaignUseCaseRunning(true);
    setCampaignUseCaseResult(null);

    try {
      const response = await fetchJson<CampaignListResponse>(CAMPAIGNS_PATH, {
        page_size: 25,
      });

      const ok = (response.results?.length ?? 0) > 0;
      setCampaignUseCaseResult({
        ok,
        count: response.count ?? response.results.length,
        sample: response.results?.[0],
        timestamp: new Date().toISOString(),
        error: ok ? undefined : "The authenticated tenant has no campaigns available.",
      });
    } catch (error) {
      setCampaignUseCaseResult({
        ok: false,
        count: 0,
        timestamp: new Date().toISOString(),
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setCampaignUseCaseRunning(false);
    }
  };

  const handleDownloadReport = () => {
    if (!report) return;

    const blob = new Blob([report], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "API_TEST_REPORT.md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getTotalStats = () => {
    if (!testResults) return { total: 0, success: 0, failed: 0 };

    let total = 0;
    let success = 0;
    let failed = 0;

    testResults.forEach((category) => {
      category.results.forEach((result) => {
        total++;
        if (result.success) {
          success++;
        } else {
          failed++;
        }
      });
    });

    return { total, success, failed };
  };

  const stats = getTotalStats();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">API Endpoint Tester</h1>
        <p className="text-muted-foreground mt-2">
          Systematically test all Moio Platform API endpoints and generate a comprehensive report
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Test Controls</CardTitle>
          <CardDescription>
            Run tests against all API endpoints and download a detailed markdown report
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-4">
            <Button
              onClick={handleRunTests}
              disabled={isRunning}
              size="lg"
              data-testid="button-run-tests"
            >
              {isRunning ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Running Tests...
                </>
              ) : (
                <>
                  <PlayCircle className="w-4 h-4 mr-2" />
                  Run All Tests
                </>
              )}
            </Button>

            {report && (
              <Button
                onClick={handleDownloadReport}
                variant="outline"
                size="lg"
                data-testid="button-download-report"
              >
                <Download className="w-4 h-4 mr-2" />
                Download Report
              </Button>
            )}
          </div>

          {testResults && (
            <div className="grid grid-cols-3 gap-4 pt-4">
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>Total Tests</CardDescription>
                  <CardTitle className="text-3xl">{stats.total}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>Successful</CardDescription>
                  <CardTitle className="text-3xl text-green-600">{stats.success}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-3">
                  <CardDescription>Failed</CardDescription>
                  <CardTitle className="text-3xl text-red-600">{stats.failed}</CardTitle>
                </CardHeader>
              </Card>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Campaigns Use Case</CardTitle>
          <CardDescription>
            Validate that the authenticated tenant (e.g. tenant 1) can list existing campaigns without relying on mocked data
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            onClick={handleCampaignUseCase}
            disabled={campaignUseCaseRunning}
            size="lg"
            data-testid="button-run-campaign-use-case"
          >
            {campaignUseCaseRunning ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Checking campaigns...
              </>
            ) : (
              <>
                <RefreshCcw className="w-4 h-4 mr-2" />
                Run Campaign Listing Use Case
              </>
            )}
          </Button>

          {campaignUseCaseResult && (
            <div className="border rounded-lg p-4 space-y-3" data-testid="campaign-use-case-result">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Last run</p>
                  <p className="text-base font-medium">{new Date(campaignUseCaseResult.timestamp).toLocaleString()}</p>
                </div>
                <Badge variant={campaignUseCaseResult.ok ? "default" : "destructive"}>
                  {campaignUseCaseResult.ok ? "Campaigns found" : "No campaigns"}
                </Badge>
              </div>

              <div className="grid gap-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Total campaigns</span>
                  <span className="font-medium">{campaignUseCaseResult.count}</span>
                </div>

                {campaignUseCaseResult.sample ? (
                  <div className="rounded-md bg-muted/50 p-3">
                    <p className="text-sm font-semibold">Sample campaign</p>
                    <p className="text-sm">{campaignUseCaseResult.sample.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Status: {campaignUseCaseResult.sample.status} · Channel: {campaignUseCaseResult.sample.channel}
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No campaign payload returned.</p>
                )}

                {campaignUseCaseResult.error && (
                  <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                    {campaignUseCaseResult.error}
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {testResults && testResults.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-2xl font-bold">Test Results</h2>
          
          {testResults.map((category, idx) => (
            <Card key={idx}>
              <CardHeader>
                <CardTitle>{category.category}</CardTitle>
                <CardDescription>
                  {category.results.filter((r) => r.success).length} of {category.results.length} endpoints working
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {category.results.map((result, resultIdx) => (
                    <div
                      key={resultIdx}
                      className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                      data-testid={`test-result-${result.method}-${result.path}`}
                    >
                      <div className="flex items-center gap-3 flex-1">
                        <Badge variant="outline" className="font-mono text-xs">
                          {result.method}
                        </Badge>
                        <code className="text-sm">{result.path}</code>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge
                          variant={result.success ? "default" : result.status === 404 ? "secondary" : "destructive"}
                        >
                          {result.status}
                        </Badge>
                        {result.success ? (
                          <span className="text-green-600">✅</span>
                        ) : result.status === 404 ? (
                          <span>⚠️</span>
                        ) : (
                          <span className="text-red-600">❌</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>WebSocket Debug</CardTitle>
          <CardDescription>
            Monitor WebSocket connections and events in real-time with customizable URL selection
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div style={{ height: "500px" }}>
            <WSDebugVisualizer
              persistedEvents={wsEvents}
              onEventsChange={setWsEvents}
              embeddedMode={true}
              isConnected={false}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
