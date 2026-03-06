import { useState } from "react";
import { useLocation } from "wouter";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  useDataLabResultSet,
  useDataLabResultSetUpdate,
  useDataLabResultSetDelete,
  useDataLabResultSetPromote,
} from "@/hooks/use-datalab";
import { useToast } from "@/hooks/use-toast";
import {
  Loader2,
  Trash2,
  ArrowUpCircle,
  Table2,
  Calendar,
  Hash,
  FileText,
  Copy,
  Pencil,
} from "lucide-react";

export function ResultSetViewer({
  id,
  onSelect,
}: {
  id: string;
  onSelect: (type: string, id?: string) => void;
}) {
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const { data: resultSet, isLoading, error } = useDataLabResultSet(id);
  const updateMutation = useDataLabResultSetUpdate();
  const deleteMutation = useDataLabResultSetDelete();
  const promoteMutation = useDataLabResultSetPromote();
  
  const [promoteName, setPromoteName] = useState("");
  const [promoteDialogOpen, setPromoteDialogOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");

  const startEditing = () => {
    setEditName(resultSet?.name || "");
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setEditName("");
  };

  const handleRename = async () => {
    const trimmed = editName.trim();
    if (!trimmed) {
      cancelEditing();
      return;
    }
    if (trimmed === resultSet?.name) {
      cancelEditing();
      return;
    }
    try {
      await updateMutation.mutateAsync({ id, data: { name: trimmed } });
      toast({ description: "Renamed" });
      setIsEditing(false);
    } catch (err: any) {
      toast({ variant: "destructive", description: err?.message || "Failed to rename" });
    }
  };

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync(id);
      toast({ description: "Result set deleted" });
      setLocation("/datalab");
    } catch (err: any) {
      toast({ variant: "destructive", description: err?.message || "Failed to delete" });
    }
  };

  const handlePromote = async () => {
    try {
      const result = await promoteMutation.mutateAsync({ 
        id, 
        name: promoteName.trim() || resultSet?.name || "Promoted Dataset" 
      });
      toast({ description: "Result set promoted to Dataset!" });
      setPromoteDialogOpen(false);
      // Navigate to the new dataset
      if (result?.id) {
        onSelect("dataset", result.id);
      }
    } catch (err: any) {
      toast({ variant: "destructive", description: err?.message || "Failed to promote" });
    }
  };

  const copyId = () => {
    navigator.clipboard.writeText(id);
    toast({ description: "ID copied to clipboard" });
  };

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !resultSet) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground">Failed to load result set</p>
          <Button variant="outline" size="sm" className="mt-2" onClick={() => setLocation("/datalab")}>
            Go back
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="p-4 flex-1 overflow-auto">
        <div className="max-w-4xl mx-auto space-y-4">
          {/* Header */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <CardTitle className="flex items-center gap-2">
                    <Table2 className="h-5 w-5" />
                    {isEditing ? (
                      <Input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        onBlur={handleRename}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRename();
                          if (e.key === "Escape") cancelEditing();
                        }}
                        className="h-7 text-lg font-semibold max-w-[300px]"
                        autoFocus
                      />
                    ) : (
                      <button
                        onClick={startEditing}
                        className="hover:text-primary transition-colors flex items-center gap-1 group"
                        title="Click to rename"
                      >
                        {resultSet.name || "Untitled Result Set"}
                        <Pencil className="h-3 w-3 opacity-0 group-hover:opacity-50 transition-opacity" />
                      </button>
                    )}
                  </CardTitle>
                  <CardDescription className="flex items-center gap-2">
                    <button
                      onClick={copyId}
                      className="font-mono text-xs hover:text-foreground transition-colors flex items-center gap-1"
                    >
                      {id.slice(0, 8)}...
                      <Copy className="h-3 w-3" />
                    </button>
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="capitalize">
                    {resultSet.origin || "unknown"}
                  </Badge>
                  <Badge variant="outline">
                    {resultSet.storage || "memory"}
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <Hash className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="text-muted-foreground text-xs">Rows</div>
                    <div className="font-medium">{(resultSet.row_count ?? 0).toLocaleString()}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="text-muted-foreground text-xs">Columns</div>
                    <div className="font-medium">{resultSet.schema_json?.length || 0}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="text-muted-foreground text-xs">Created</div>
                    <div className="font-medium">
                      {resultSet.created_at
                        ? new Date(resultSet.created_at).toLocaleDateString()
                        : "—"}
                    </div>
                  </div>
                </div>
                {resultSet.expires_at && (
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <div className="text-muted-foreground text-xs">Expires</div>
                      <div className="font-medium">
                        {new Date(resultSet.expires_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Schema */}
          {resultSet.schema_json && resultSet.schema_json.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Schema</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {resultSet.schema_json.map((col: any, i: number) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-2 rounded border text-sm"
                    >
                      <span className="font-medium truncate">{col.name}</span>
                      <Badge variant="outline" className="text-xs ml-2">
                        {col.type}
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Preview Data */}
          {resultSet.preview_json && resultSet.preview_json.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Preview (first {resultSet.preview_json.length} rows)</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="w-full">
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="bg-muted/50">
                          {resultSet.schema_json?.map((col: any, i: number) => (
                            <th
                              key={i}
                              className="px-3 py-2 text-left font-medium border-b whitespace-nowrap"
                            >
                              {col.name}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {resultSet.preview_json.map((row: any, rowIdx: number) => (
                          <tr key={rowIdx} className={rowIdx % 2 === 0 ? "" : "bg-muted/20"}>
                            {resultSet.schema_json?.map((col: any, colIdx: number) => (
                              <td
                                key={colIdx}
                                className="px-3 py-1.5 border-b truncate max-w-[200px]"
                                title={String(row[col.name] ?? "")}
                              >
                                {row[col.name] === null ? (
                                  <span className="text-muted-foreground italic">null</span>
                                ) : (
                                  String(row[col.name])
                                )}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          )}

          {/* Actions */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Actions</CardTitle>
              <CardDescription>
                Result sets are intermediate data. Promote to a Dataset for durable storage.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {/* Promote to Dataset */}
              <Dialog open={promoteDialogOpen} onOpenChange={setPromoteDialogOpen}>
                <DialogTrigger asChild>
                  <Button variant="default" size="sm">
                    <ArrowUpCircle className="h-4 w-4 mr-2" />
                    Promote to Dataset
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Promote to Dataset</DialogTitle>
                    <DialogDescription>
                      Create a durable Dataset from this result set. The data will be persisted and versioned.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="py-4">
                    <Label htmlFor="dataset-name">Dataset Name</Label>
                    <Input
                      id="dataset-name"
                      value={promoteName}
                      onChange={(e) => setPromoteName(e.target.value)}
                      placeholder={resultSet.name || "My Dataset"}
                      className="mt-1"
                    />
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setPromoteDialogOpen(false)}>
                      Cancel
                    </Button>
                    <Button onClick={handlePromote} disabled={promoteMutation.isPending}>
                      {promoteMutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                      Promote
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              {/* Delete */}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="destructive" size="sm">
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete Result Set?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will permanently delete this result set. This action cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={handleDelete}
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    >
                      {deleteMutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
