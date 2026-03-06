import { Link, useLocation } from "wouter";
import { DataLabWorkspace } from "@/components/datalab/datalab-workspace";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useDataLabResultSets } from "@/hooks/use-datalab";
import { Database, Loader2, Eye } from "lucide-react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useState } from "react";

export default function DataLabResultSets() {
  const [origin, setOrigin] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);
  const { data, isLoading } = useDataLabResultSets(origin, page, 20);

  return (
    <DataLabWorkspace>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">ResultSets</h1>
            <p className="text-muted-foreground mt-2">
              Browse and manage your data results
            </p>
          </div>
        </div>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>All ResultSets</CardTitle>
                <CardDescription>
                  {data?.count ? `${data.count} total resultsets` : "No resultsets yet"}
                </CardDescription>
              </div>
              <Select value={origin || "all"} onValueChange={(value) => setOrigin(value === "all" ? undefined : value)}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Filter by origin" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Origins</SelectItem>
                  <SelectItem value="import">Imports</SelectItem>
                  <SelectItem value="crm_query">CRM Queries</SelectItem>
                  <SelectItem value="script">Scripts</SelectItem>
                  <SelectItem value="pipeline">Pipelines</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : !data?.results || data.results.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Database className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No resultsets found</p>
                <p className="text-sm mt-2">
                  {origin ? `No ${origin} resultsets available` : "Create an import or query to get started"}
                </p>
              </div>
            ) : (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Origin</TableHead>
                      <TableHead>Rows</TableHead>
                      <TableHead>Columns</TableHead>
                      <TableHead>Storage</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.results.map((resultset) => (
                      <TableRow key={resultset.id}>
                        <TableCell className="font-medium">
                          {resultset.name || "Unnamed ResultSet"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{resultset.origin}</Badge>
                        </TableCell>
                        <TableCell>
                          {(resultset.row_count ?? 0).toLocaleString()}
                        </TableCell>
                        <TableCell>
                          {resultset.schema_json?.length ?? 0}
                        </TableCell>
                        <TableCell>
                          <Badge variant={resultset.storage === "parquet" ? "default" : "secondary"}>
                            {resultset.storage}
                          </Badge>
                        </TableCell>
                        <TableCell>{formatDate(resultset.created_at)}</TableCell>
                        <TableCell>
                          <Link href={`/datalab/resultsets/${resultset.id}`}>
                            <Button variant="ghost" size="sm">
                              <Eye className="mr-2 h-4 w-4" />
                              View
                            </Button>
                          </Link>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {(data.next || data.previous) && (
                  <div className="flex items-center justify-between mt-4">
                    <Button
                      variant="outline"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={!data.previous}
                    >
                      Previous
                    </Button>
                    <span className="text-sm text-muted-foreground">
                      Page {page}
                    </span>
                    <Button
                      variant="outline"
                      onClick={() => setPage((p) => p + 1)}
                      disabled={!data.next}
                    >
                      Next
                    </Button>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </DataLabWorkspace>
  );
}
