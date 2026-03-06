import { useState, useRef, useEffect, useMemo } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/hooks/use-toast";
import {
  useDataLabImportProcess,
  useDataLabImportProcessUpdate,
  useDataLabImportProcessCreate,
  useDataLabImportProcessRun,
  useDataLabFiles,
  useDataLabFileUpload,
} from "@/hooks/use-datalab";
import {
  Loader2,
  Upload,
  Save,
  Play,
  FileSpreadsheet,
  FileText,
  Search,
  Check,
  ChevronRight,
  Table2,
  Columns3,
  Settings2,
  Eye,
  FolderOpen,
  Plus,
  X,
  AlertCircle,
  Wand2,
} from "lucide-react";
import {
  analyzeLocalFile,
  analyzeCSVFile,
  analyzeExcelFile,
  FileAnalysisResult,
  DetectedColumn,
  generatePreliminaryMapping,
} from "@/lib/fileAnalyzer";
import { dataLabApi } from "@/lib/api";
import { useDataLabImportInspectShape } from "@/hooks/use-datalab";

type Props = { id?: string; onCreated?: (id: string) => void };

type Step = "select-file" | "explore" | "configure" | "review";

// Represents a single extractable structure within a file
// Column with inferred type info from shape inspector
interface DetectedColumn {
  name: string;
  normalizedName?: string;
  type: string;
  inferredFormat?: string; // For date/datetime columns
  typeConfidence?: number; // 0-1 confidence score
}

interface DetectedStructure {
  id: string;
  name: string;
  type: "sheet" | "table" | "csv";
  columns: DetectedColumn[];
  rowCount: number;
  // Sample data rows for preview (from backend inspect-shape)
  sampleRows?: Record<string, any>[];
  // Excel-specific
  sheetIndex?: number;
  // PDF-specific
  page?: number;
  columnCount?: number;
  // Selection state
  selected: boolean;
}

// Clean rule options
type CleanRule = "trim" | "upper" | "lower" | "remove_accents" | "currency_to_decimal";

interface ColumnMapping {
  source: string;
  target: string;
  type: string;
  include: boolean;
  format?: string; // optional format override (e.g., "DD/MM/YYYY" for dates)
  clean?: CleanRule[]; // optional cleaning rules
}

interface StructureMapping {
  structureId: string;
  columns: ColumnMapping[];
  headerRow: number;
  skipRows: number;
}

/**
 * ImportProcess Editor - File Adapter Builder
 * 
 * Purpose: Help users configure how to extract data from files they may not fully understand.
 * UX Philosophy: Explore first, configure second - discover file structure before defining extraction.
 */
export function ImportProcessEditor({ id, onCreated }: Props) {
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // API hooks
  const { data: existingProcess, isLoading: processLoading } = useDataLabImportProcess(id);
  const { data: files, isLoading: filesLoading, refetch: refetchFiles } = useDataLabFiles(1, 100);
  const uploadMutation = useDataLabFileUpload();
  const updateMutation = useDataLabImportProcessUpdate();
  const createMutation = useDataLabImportProcessCreate();
  const runMutation = useDataLabImportProcessRun(id || "");
  const inspectShapeMutation = useDataLabImportInspectShape();

  // Wizard state
  const [step, setStep] = useState<Step>("select-file");
  const [filePickerOpen, setFilePickerOpen] = useState(false);
  const [fileSearch, setFileSearch] = useState("");
  
  // File state
  const [selectedFileId, setSelectedFileId] = useState<string | undefined>();
  const [selectedFileName, setSelectedFileName] = useState<string>("");
  const [localFile, setLocalFile] = useState<File | null>(null);
  const [fileType, setFileType] = useState<"csv" | "excel" | "pdf">("csv");
  
  // Status state
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [analysis, setAnalysis] = useState<FileAnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  
  // Structures state - multiple sheets/tables detected in file
  const [detectedStructures, setDetectedStructures] = useState<DetectedStructure[]>([]);
  const [activeStructureId, setActiveStructureId] = useState<string | null>(null);
  const [structureMappings, setStructureMappings] = useState<Record<string, StructureMapping>>({});
  
  // Configuration state
  const [processName, setProcessName] = useState("");
  const [importAsJson, setImportAsJson] = useState(false);
  
  // Parser-level settings
  const [dateFormat, setDateFormat] = useState("DD/MM/YYYY");
  const [datetimeFormat, setDatetimeFormat] = useState("YYYY-MM-DD HH:mm:ss");
  const [csvDelimiter, setCsvDelimiter] = useState(",");
  const [csvEncoding, setCsvEncoding] = useState("utf-8");
  const [pdfPageInfo, setPdfPageInfo] = useState<{
    pageCount: number;
    headerPages: number[];
    detailPages: number[];
    footerPages: number[];
  } | null>(null);
  const [selectedPdfPage, setSelectedPdfPage] = useState<number | "all">("all");

  // Track if we've already loaded the existing process
  const [processLoaded, setProcessLoaded] = useState(false);

  // Load existing process data when editing
  useEffect(() => {
    if (!existingProcess || processLoaded) return;
    
    console.log("Loading existing process:", existingProcess);
    setProcessLoaded(true);
    
    // Set basic info
    setProcessName(existingProcess.name || "");
    setFileType(existingProcess.file_type || "csv");
    
    // Set file reference if available
    if (existingProcess.file_id) {
      setSelectedFileId(existingProcess.file_id);
    }
    
    // Load contract_json settings
    const contract = existingProcess.contract_json;
    if (contract) {
      console.log("Loading contract_json:", contract);
      
      // Parser settings
      if (contract.parser) {
        if (contract.parser.delimiter) setCsvDelimiter(contract.parser.delimiter);
        if (contract.parser.encoding) setCsvEncoding(contract.parser.encoding);
        if (contract.parser.date_format) setDateFormat(contract.parser.date_format);
        if (contract.parser.datetime_format) setDatetimeFormat(contract.parser.datetime_format);
      }
      
      // Build column mappings from contract mapping
      if (contract.mapping && contract.mapping.length > 0) {
        // Create a single structure with the mappings
        const columns = contract.mapping.map((m) => ({
          name: m.source,
          type: m.type || "string",
        }));
        
        const structure: DetectedStructure = {
          id: "loaded-structure",
          name: existingProcess.name || "Imported Data",
          type: existingProcess.file_type === "pdf" ? "table" : existingProcess.file_type === "excel" ? "sheet" : "csv",
          columns,
          rowCount: 0,
          selected: true,
        };
        
        setDetectedStructures([structure]);
        setActiveStructureId("loaded-structure");
        
        // Set structure mapping with loaded values
        setStructureMappings({
          "loaded-structure": {
            structureId: "loaded-structure",
            headerRow: contract.parser?.header_row ?? 0,
            skipRows: contract.parser?.skip_rows ?? 0,
            columns: contract.mapping.map((m) => ({
              source: m.source,
              target: m.target,
              type: m.type || "string",
              include: true,
              format: m.format,
              clean: m.clean as CleanRule[] | undefined,
            })),
          },
        });
        
        // Move to explore step since we have data
        setStep("explore");
      }
    }
  }, [existingProcess, processLoaded]);

  // Load filename when files are available
  useEffect(() => {
    if (!selectedFileId || !files?.results) return;
    const file = files.results.find((f) => f.id === selectedFileId);
    if (file && !selectedFileName) {
      setSelectedFileName(file.filename);
    }
  }, [selectedFileId, files, selectedFileName]);

  // Filter files by search
  const filteredFiles = useMemo(() => {
    const list = files?.results || [];
    if (!fileSearch.trim()) return list;
    const q = fileSearch.toLowerCase();
    return list.filter((f) => f.filename.toLowerCase().includes(q));
  }, [files, fileSearch]);

  // Detect file type from name
  const detectFileType = (filename: string): "csv" | "excel" | "pdf" => {
    const lower = filename.toLowerCase();
    if (lower.endsWith(".csv") || lower.endsWith(".tsv") || lower.endsWith(".txt")) return "csv";
    if (lower.endsWith(".xls") || lower.endsWith(".xlsx") || lower.endsWith(".xlsm")) return "excel";
    if (lower.endsWith(".pdf")) return "pdf";
    return "csv"; // Default to CSV for unknown types
  };

  // Analyze file via backend inspect-shape endpoint
  // All file types (CSV, Excel, PDF) are sent to backend for analysis
  // Backend now returns sample_rows with actual data for preview
  const analyzeFile = async (file: File, fileId?: string): Promise<FileAnalysisResult | null> => {
    const type = detectFileType(file.name);
    const structures: DetectedStructure[] = [];
    
    if (!fileId) {
      throw new Error("File ID is required for analysis");
    }
    
    try {
      console.log("Calling backend inspect-shape with:", { file_id: fileId, file_type: type });
      const shapeResult = await inspectShapeMutation.mutateAsync({
        file_id: fileId,
        file_type: type,
      });
      console.log("Backend shape result:", shapeResult);
      
      const description = shapeResult.description || {};
      
      // Parse column with inferred type info
      const parseColumn = (col: any): DetectedColumn => {
        if (typeof col === "string") {
          return { name: col, type: "string" };
        }
        return {
          name: col.name || col.original || "unknown",
          normalizedName: col.normalized_name,
          type: col.inferred_type || col.type || "string",
          inferredFormat: col.inferred_format,
          typeConfidence: col.type_confidence,
        };
      };

      // Handle based on file type
      if (type === "csv") {
        // CSV: single structure with columns and sample data from backend
        const columns = (description.columns || []).map(parseColumn);
        const sampleRows = description.sample_rows || [];
        const rowCount = description.total_row_count || description.row_count || sampleRows.length;
        
        structures.push({
          id: "csv-main",
          name: file.name,
          type: "csv",
          columns,
          rowCount,
          selected: true,
          sampleRows, // Store sample rows in structure
        });
        
        setDetectedStructures(structures);
        setActiveStructureId("csv-main");
        initializeStructureMapping("csv-main", columns, 0, 0);
        
        return {
          detected_schema: columns.map((c: any) => ({ name: c.name, type: c.type as any })),
          sample_rows: sampleRows,
          row_count: rowCount,
          warnings: [],
          detected_delimiter: description.delimiter,
        };
      }
      
      if (type === "excel") {
        // Excel: multiple sheets with sample data per sheet
        const sheets = description.sheets || [];
        
        // If no detailed sheets, create one from top-level data
        if (sheets.length === 0 && description.columns) {
          sheets.push({
            name: "Sheet1",
            columns: description.columns,
            sample_rows: description.sample_rows || [],
            total_row_count: description.total_row_count || 0,
          });
        }
        
        sheets.forEach((sheet: any, idx: number) => {
          const sheetName = typeof sheet === "string" ? sheet : sheet.name || `Sheet${idx + 1}`;
          const sheetColumns = (sheet.columns || description.columns || []).map(parseColumn);
          const sheetSampleRows = sheet.sample_rows || [];
          const sheetRowCount = sheet.total_row_count || sheetSampleRows.length;
          
          structures.push({
            id: `sheet-${idx}`,
            name: sheetName,
            type: "sheet",
            sheetIndex: idx,
            columns: sheetColumns,
            rowCount: sheetRowCount,
            selected: idx === 0,
            sampleRows: sheetSampleRows,
          });
          
          if (sheetColumns.length > 0) {
            initializeStructureMapping(`sheet-${idx}`, sheetColumns, 0, 0);
          }
        });
        
        setDetectedStructures(structures);
        setActiveStructureId("sheet-0");
        
        const firstSheet = structures[0];
        return {
          detected_schema: firstSheet?.columns.map((c: any) => ({ name: c.name, type: c.type as any })) || [],
          sample_rows: firstSheet?.sampleRows || [],
          row_count: firstSheet?.rowCount || 0,
          warnings: [],
          detected_sheets: structures.map((s, i) => ({ name: s.name, index: i })),
        };
      }
      
      if (type === "pdf") {
        // PDF: multiple tables with sample data per table
        const tables = description.tables || [];
        const pagePatterns = description.page_patterns || {};
        const pageCount = description.page_count || 0;
        
        setPdfPageInfo({
          pageCount,
          headerPages: pagePatterns.header || [],
          detailPages: pagePatterns.detail || [],
          footerPages: pagePatterns.footer || [],
        });
        
        // Reset page selection when analyzing a new file
        setSelectedPdfPage("all");
        
        tables.forEach((table: any, idx: number) => {
          const columns = (table.columns || []).map(parseColumn);
          const tableSampleRows = table.sample_rows || [];
          const tableIndex = table.table_index !== undefined ? table.table_index : idx;
          
          structures.push({
            id: `table-${idx}`,
            name: `Table ${tableIndex + 1} (Page ${table.page + 1})`,
            type: "table" as const,
            page: table.page,
            columnCount: table.column_count || columns.length,
            columns,
            rowCount: table.row_count_estimate || tableSampleRows.length,
            selected: idx === 0,
            sampleRows: tableSampleRows,
          });
          
          if (columns.length > 0) {
            initializeStructureMapping(`table-${idx}`, columns, 0, 0);
          }
        });
        
        setDetectedStructures(structures);
        if (structures.length > 0) {
          setActiveStructureId(structures[0].id);
        }
        
        const totalRows = structures.reduce((sum, s) => sum + s.rowCount, 0);
        const firstTable = structures[0];
        
        return {
          detected_schema: firstTable?.columns.map((c) => ({ name: c.name, type: c.type as any })) || [],
          sample_rows: firstTable?.sampleRows || [],
          row_count: totalRows,
          warnings: [`PDF: ${pageCount} pages, ${tables.length} table(s) detected`],
        };
      }
      
      throw new Error(`Unsupported file type: ${type}`);
    } catch (err: any) {
      console.error("Backend inspect-shape failed:", err);
      throw new Error(`File inspection failed: ${err?.message || "Unknown error"}`);
    }
  };

  // Initialize column mapping for a structure using inferred types
  const initializeStructureMapping = (
    structureId: string,
    columns: DetectedColumn[],
    headerRow: number,
    skipRows: number
  ) => {
    setStructureMappings((prev) => ({
      ...prev,
      [structureId]: {
        structureId,
        headerRow,
        skipRows,
        columns: columns.map((col) => ({
          source: col.name,
          // Use normalized name if available, otherwise generate one
          target: col.normalizedName || col.name.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, ""),
          type: col.type,
          include: true,
          // Use inferred format for date/datetime columns
          format: col.inferredFormat,
        })),
      },
    }));
  };

  // Toggle structure selection
  const toggleStructureSelection = (structureId: string) => {
    setDetectedStructures((prev) =>
      prev.map((s) => (s.id === structureId ? { ...s, selected: !s.selected } : s))
    );
    // Initialize mapping if not exists and now selected
    const structure = detectedStructures.find((s) => s.id === structureId);
    if (structure && !structure.selected && !structureMappings[structureId]) {
      initializeStructureMapping(structureId, structure.columns, 0, 0);
    }
  };

  // Get active structure's mapping
  const activeMapping = activeStructureId ? structureMappings[activeStructureId] : null;
  const activeStructure = detectedStructures.find((s) => s.id === activeStructureId);
  const selectedStructures = detectedStructures.filter((s) => s.selected);
  
  // Filter structures by selected PDF page
  const filteredStructures = useMemo(() => {
    if (selectedPdfPage === "all" || !pdfPageInfo) {
      return detectedStructures;
    }
    return detectedStructures.filter((s) => s.page === selectedPdfPage);
  }, [detectedStructures, selectedPdfPage, pdfPageInfo]);

  // Handle clicking on a structure to view it - initialize mapping if needed
  const handleStructureClick = (structureId: string) => {
    setActiveStructureId(structureId);
    // Initialize mapping if it doesn't exist and structure has columns
    const structure = detectedStructures.find((s) => s.id === structureId);
    if (structure && !structureMappings[structureId] && structure.columns.length > 0) {
      initializeStructureMapping(structureId, structure.columns, 0, 0);
    }
  };

  // Handle file selection from picker
  const handleSelectExistingFile = async (fileId: string, filename: string) => {
    setSelectedFileId(fileId);
    setSelectedFileName(filename);
    setLocalFile(null);
    setFileType(detectFileType(filename));
    setFilePickerOpen(false);
    setProcessName(filename.replace(/\.[^.]+$/, ""));
    
    // Auto-analyze
    await analyzeSelectedFile(fileId, filename);
  };

  // Handle new file upload
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    // Reset state
    setLocalFile(file);
    setSelectedFileName(file.name);
    setSelectedFileId(undefined);
    setFileType(detectFileType(file.name));
    setProcessName(file.name.replace(/\.[^.]+$/, ""));
    setFilePickerOpen(false);
    setAnalysis(null);
    setAnalysisError(null);
    
    // Step 1: Upload file
    setUploading(true);
    setStatusMessage("Uploading file...");
    
    let uploadedFileId: string;
    try {
      const uploaded = await uploadMutation.mutateAsync({ file });
      uploadedFileId = uploaded.id;
      setSelectedFileId(uploadedFileId);
      await refetchFiles();
      setStatusMessage("File uploaded successfully");
      toast({ description: `File saved (ID: ${uploadedFileId.slice(0, 8)}...)` });
    } catch (err: any) {
      setUploading(false);
      setStatusMessage("");
      setAnalysisError(err?.message || "Failed to upload file");
      toast({ variant: "destructive", description: err?.message || "Upload failed" });
      return;
    }
    setUploading(false);
    
    // Step 2: Analyze file (now that it's saved)
    setAnalyzing(true);
    setStatusMessage("Analyzing file structure...");
    
    try {
      const result = await analyzeFile(file, uploadedFileId);
      if (result) {
        setAnalysis(result);
        // Set detected delimiter if available (for CSV)
        if (result.detected_delimiter) {
          setCsvDelimiter(result.detected_delimiter);
        }
        setStep("explore");
        toast({ description: "File analyzed - ready to configure" });
      }
    } catch (err: any) {
      setAnalysisError(err?.message || "Failed to analyze file");
      toast({ variant: "destructive", description: err?.message || "Analysis failed" });
    } finally {
      setAnalyzing(false);
      setStatusMessage("");
    }
  };

  // Analyze an existing file (download + analyze)
  const analyzeSelectedFile = async (fileId: string, filename: string) => {
    setAnalyzing(true);
    setAnalysisError(null);
    setAnalysis(null);
    setDetectedStructures([]);
    setStructureMappings({});
    setStatusMessage("Analyzing file structure...");
    
    try {
      const type = detectFileType(filename);
      let file: File;
      
      // For PDF, we don't need to download - backend handles it
      if (type === "pdf") {
        file = new File([], filename); // Dummy file for type detection
      } else {
        // Download the file content for local analysis
        setStatusMessage("Downloading file for analysis...");
        const blob = await dataLabApi.getFileContent(fileId);
        file = new File([blob], filename, { type: blob.type });
      }
      
      setStatusMessage("Analyzing file structure...");
      const result = await analyzeFile(file, fileId);
      
      if (result) {
        setAnalysis(result);
        // Set detected delimiter if available (for CSV)
        if (result.detected_delimiter) {
          setCsvDelimiter(result.detected_delimiter);
        }
        setStep("explore");
        toast({ description: "File analyzed successfully" });
      }
    } catch (err: any) {
      setAnalysisError(err?.message || "Failed to analyze file");
      toast({ variant: "destructive", description: err?.message || "Analysis failed" });
    } finally {
      setAnalyzing(false);
      setStatusMessage("");
    }
  };

  // Toggle column inclusion for active structure
  const toggleColumn = (source: string) => {
    if (!activeStructureId) return;
    setStructureMappings((prev) => ({
      ...prev,
      [activeStructureId]: {
        ...prev[activeStructureId],
        columns: prev[activeStructureId].columns.map((m) =>
          m.source === source ? { ...m, include: !m.include } : m
        ),
      },
    }));
  };

  // Update column mapping for active structure
  const updateMapping = (source: string, field: keyof ColumnMapping, value: any) => {
    if (!activeStructureId) return;
    setStructureMappings((prev) => ({
      ...prev,
      [activeStructureId]: {
        ...prev[activeStructureId],
        columns: prev[activeStructureId].columns.map((m) =>
          m.source === source ? { ...m, [field]: value } : m
        ),
      },
    }));
  };

  // Toggle clean rule for a column
  const toggleCleanRule = (source: string, rule: CleanRule) => {
    if (!activeStructureId) return;
    setStructureMappings((prev) => {
      const currentMapping = prev[activeStructureId]?.columns.find((m) => m.source === source);
      const currentClean = currentMapping?.clean || [];
      const newClean = currentClean.includes(rule)
        ? currentClean.filter((r) => r !== rule)
        : [...currentClean, rule];
      
      return {
        ...prev,
        [activeStructureId]: {
          ...prev[activeStructureId],
          columns: prev[activeStructureId].columns.map((m) =>
            m.source === source ? { ...m, clean: newClean } : m
          ),
        },
      };
    });
  };

  // Update structure settings (headerRow, skipRows)
  const updateStructureSetting = (field: "headerRow" | "skipRows", value: number) => {
    if (!activeStructureId) return;
    setStructureMappings((prev) => ({
      ...prev,
      [activeStructureId]: {
        ...prev[activeStructureId],
        [field]: value,
      },
    }));
  };

  // Build contract_json from selected structures and mappings
  const buildContractJson = () => {
    // Use first selected structure for parser config (most common case)
    const firstStructure = selectedStructures[0];
    const firstMapping = firstStructure ? structureMappings[firstStructure.id] : null;
    
    // Build parser section based on file type
    const parser: any = {
      type: fileType,
      header_row: firstMapping?.headerRow ?? 0,
      skip_rows: firstMapping?.skipRows ?? 0,
      date_format: dateFormat,
      datetime_format: datetimeFormat,
    };
    
    // CSV-specific
    if (fileType === "csv") {
      parser.delimiter = csvDelimiter;
      parser.encoding = csvEncoding;
    }
    
    // Excel-specific
    if (fileType === "excel" && firstStructure?.type === "sheet") {
      parser.sheet = firstStructure.sheetIndex ?? firstStructure.name;
    }
    
    // PDF-specific
    if (fileType === "pdf" && firstStructure?.type === "table") {
      parser.structural_unit = {
        kind: "pdf_table",
        selector: {
          page_selector: { type: "first" }, // TODO: make configurable
        },
      };
      if (firstStructure.page !== undefined) {
        parser.structural_unit.selector.page_selector = {
          type: "specific",
          value: firstStructure.page,
        };
      }
    }
    
    // Build mapping array from all selected structures
    const mapping: any[] = [];
    selectedStructures.forEach((structure) => {
      const structMapping = structureMappings[structure.id];
      if (!structMapping) return;
      
      structMapping.columns
        .filter((col) => col.include)
        .forEach((col) => {
          const mapEntry: any = {
            source: col.source,
            target: col.target,
            type: col.type,
          };
          if (col.format) {
            mapEntry.format = col.format;
          }
          if (col.clean && col.clean.length > 0) {
            mapEntry.clean = col.clean;
          }
          mapping.push(mapEntry);
        });
    });
    
    return {
      version: "1",
      parser,
      mapping,
    };
  };

  // Save handler
  const handleSave = async () => {
    if (!processName.trim()) {
      toast({ variant: "destructive", description: "Please enter a name for this import process" });
      return;
    }
    if (!selectedFileId) {
      toast({ variant: "destructive", description: "Please select a file first" });
      return;
    }

    const contractJson = buildContractJson();

    try {
      if (id) {
        // Update existing: PATCH with contract_json
        await updateMutation.mutateAsync({
          id,
          data: {
            name: processName.trim(),
            file_type: fileType,
            contract_json: contractJson,
          },
        });
        toast({ description: "Import process saved" });
      } else {
        // Create new: POST with file_id (auto-detects config)
        const created = await createMutation.mutateAsync({
          name: processName.trim(),
          file_type: fileType,
          file_id: selectedFileId,
          import_data_as_json: importAsJson || undefined,
        });
        
        // Then PATCH with customized contract_json
        if (contractJson.mapping.length > 0) {
          await updateMutation.mutateAsync({
            id: created.id,
            data: {
              contract_json: contractJson,
            },
          });
        }
        
        toast({ description: "Import process created" });
        onCreated?.(created.id);
      }
    } catch (err: any) {
      toast({ variant: "destructive", description: err?.message || "Save failed" });
    }
  };

  // Run result state
  const [runResult, setRunResult] = useState<{
    status: "success" | "failed" | "pending" | null;
    errorMessage?: string;
    shapeMatch?: { status: string; reasons?: string[] };
    resultsetIds?: string[];
  } | null>(null);

  // Run handler
  const handleRun = async () => {
    if (!id) {
      toast({ variant: "destructive", description: "Save the import process first" });
      return;
    }
    if (!selectedFileId) {
      toast({ variant: "destructive", description: "Select a file to process" });
      return;
    }

    setRunResult({ status: "pending" });

    try {
      const result = await runMutation.mutateAsync({ raw_dataset_id: selectedFileId });
      console.log("Run result:", result);
      
      // Check if the run succeeded or failed
      if (result.status === "failed") {
        setRunResult({
          status: "failed",
          errorMessage: result.error_message,
          shapeMatch: result.shape_match,
          resultsetIds: result.resultset_ids || [],
        });
        toast({
          variant: "destructive",
          title: "Import failed",
          description: result.error_message || "Unknown error occurred",
        });
      } else if (result.status === "success" || result.status === "completed") {
        setRunResult({
          status: "success",
          resultsetIds: result.resultset_ids || [],
        });
        toast({
          title: "Import completed",
          description: `Created ${result.resultset_ids?.length || 0} dataset(s)`,
        });
      } else {
        // Pending or other status
        setRunResult({
          status: result.status as any,
          resultsetIds: result.resultset_ids || [],
        });
        toast({ description: `Import status: ${result.status}` });
      }
    } catch (err: any) {
      setRunResult({
        status: "failed",
        errorMessage: err?.message || "Run failed",
      });
      toast({ variant: "destructive", description: err?.message || "Run failed" });
    }
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 p-4 border-b bg-background">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold">
              {id ? "Edit Import Process" : "New Import Process"}
            </h2>
            <p className="text-sm text-muted-foreground">
              Configure how to extract data from your file
            </p>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleSave}
              disabled={isSaving || !selectedFileId}
            >
              {isSaving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Save
            </Button>
            <Button
              size="sm"
              onClick={handleRun}
              disabled={runMutation.isPending || !id || !selectedFileId}
            >
              {runMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Play className="h-4 w-4 mr-2" />}
              Run
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4">
        <div className="max-w-5xl mx-auto space-y-4">
          {/* Step 1: File Selection */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-medium">
                    1
                  </div>
                  <div>
                    <CardTitle className="text-base">Select Source File</CardTitle>
                    <CardDescription>Choose an existing file or upload a new one</CardDescription>
                  </div>
                </div>
                {selectedFileName && (
                  <Badge variant="secondary" className="gap-1">
                    {fileType === "csv" && <FileText className="h-3 w-3" />}
                    {fileType === "excel" && <FileSpreadsheet className="h-3 w-3" />}
                    {selectedFileName}
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex gap-3">
                {/* File Picker Dialog */}
                <Dialog open={filePickerOpen} onOpenChange={setFilePickerOpen}>
                  <DialogTrigger asChild>
                    <Button variant="outline" className="flex-1 h-20 flex-col gap-1">
                      <FolderOpen className="h-5 w-5" />
                      <span className="text-sm">Browse Files</span>
                      <span className="text-xs text-muted-foreground">
                        {(files?.results?.length || 0)} files available
                      </span>
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-lg">
                    <DialogHeader>
                      <DialogTitle>Select a File</DialogTitle>
                      <DialogDescription>
                        Choose an existing file to configure for import
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                      <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          placeholder="Search files..."
                          value={fileSearch}
                          onChange={(e) => setFileSearch(e.target.value)}
                          className="pl-9"
                        />
                      </div>
                      <ScrollArea className="h-64 border rounded-md">
                        {filesLoading ? (
                          <div className="flex items-center justify-center h-full">
                            <Loader2 className="h-5 w-5 animate-spin" />
                          </div>
                        ) : filteredFiles.length === 0 ? (
                          <div className="flex flex-col items-center justify-center h-full text-muted-foreground p-4">
                            <FileText className="h-8 w-8 mb-2 opacity-50" />
                            <p className="text-sm">No files found</p>
                          </div>
                        ) : (
                          <div className="p-1">
                            {filteredFiles.map((f) => (
                              <button
                                key={f.id}
                                onClick={() => handleSelectExistingFile(f.id, f.filename)}
                                className="w-full flex items-center gap-3 p-2 rounded hover:bg-muted text-left"
                              >
                                {detectFileType(f.filename) === "csv" ? (
                                  <FileText className="h-4 w-4 text-green-600" />
                                ) : detectFileType(f.filename) === "excel" ? (
                                  <FileSpreadsheet className="h-4 w-4 text-emerald-600" />
                                ) : (
                                  <FileText className="h-4 w-4 text-red-600" />
                                )}
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium truncate">{f.filename}</p>
                                  <p className="text-xs text-muted-foreground">
                                    {f.size ? `${(f.size / 1024).toFixed(1)} KB` : "Unknown size"}
                                  </p>
                                </div>
                                {selectedFileId === f.id && (
                                  <Check className="h-4 w-4 text-primary" />
                                )}
                              </button>
                            ))}
                          </div>
                        )}
                      </ScrollArea>
                    </div>
                  </DialogContent>
                </Dialog>

                {/* Upload Button */}
                <Button
                  variant="outline"
                  className="flex-1 h-20 flex-col gap-1"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading || analyzing}
                >
                  {uploading ? (
                    <Loader2 className="h-5 w-5 animate-spin" />
                  ) : (
                    <Upload className="h-5 w-5" />
                  )}
                  <span className="text-sm">Upload New File</span>
                  <span className="text-xs text-muted-foreground">CSV, Excel, or PDF</span>
                </Button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.xls,.xlsx,.pdf"
                  className="hidden"
                  onChange={handleFileUpload}
                />
              </div>

              {(uploading || analyzing) && statusMessage && (
                <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {statusMessage}
                </div>
              )}

              {selectedFileId && !uploading && !analyzing && !analysis && (
                <div className="mt-4 flex items-center gap-2 text-sm text-green-600">
                  <Check className="h-4 w-4" />
                  File saved: {selectedFileId.slice(0, 8)}...
                </div>
              )}

              {analysisError && (
                <div className="mt-4 p-3 bg-destructive/10 text-destructive rounded-md text-sm flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  {analysisError}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Step 2: Detected Structures - Only show after analysis */}
          {detectedStructures.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-medium">
                      2
                    </div>
                    <div>
                      <CardTitle className="text-base">Detected Structures</CardTitle>
                      <CardDescription>
                        Found {detectedStructures.length} {detectedStructures.length === 1 ? "structure" : "structures"} • 
                        {selectedStructures.length} selected for import
                      </CardDescription>
                    </div>
                  </div>
                  {pdfPageInfo && (
                    <Badge variant="outline" className="text-xs">
                      {pdfPageInfo.pageCount} pages
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {/* PDF Page Navigator */}
                {pdfPageInfo && pdfPageInfo.pageCount > 1 && (
                  <div className="mb-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xs font-medium text-muted-foreground">Navigate pages:</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      <Button
                        variant={selectedPdfPage === "all" ? "default" : "outline"}
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => setSelectedPdfPage("all")}
                      >
                        All ({detectedStructures.length})
                      </Button>
                      {Array.from({ length: pdfPageInfo.pageCount }, (_, i) => {
                        const tablesOnPage = detectedStructures.filter((s) => s.page === i).length;
                        const pageType = pdfPageInfo.headerPages.includes(i)
                          ? "H"
                          : pdfPageInfo.footerPages.includes(i)
                          ? "F"
                          : "";
                        return (
                          <Button
                            key={i}
                            variant={selectedPdfPage === i ? "default" : "outline"}
                            size="sm"
                            className={`h-7 px-2 text-xs ${
                              tablesOnPage === 0 ? "opacity-50" : ""
                            }`}
                            onClick={() => setSelectedPdfPage(i)}
                          >
                            Page {i + 1}
                            {tablesOnPage > 0 && (
                              <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
                                {tablesOnPage}
                              </Badge>
                            )}
                            {pageType && (
                              <span className="ml-1 text-[10px] text-muted-foreground">({pageType})</span>
                            )}
                          </Button>
                        );
                      })}
                    </div>
                    {/* Page type legend */}
                    <div className="flex gap-3 mt-2 text-[10px] text-muted-foreground">
                      <span>(H) = Header page</span>
                      <span>(F) = Footer page</span>
                    </div>
                  </div>
                )}

                {/* Structures Grid */}
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {filteredStructures.map((structure) => (
                    <div
                      key={structure.id}
                      className={`relative p-3 border rounded-lg cursor-pointer transition-colors ${
                        structure.selected
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-muted-foreground/50"
                      } ${activeStructureId === structure.id ? "ring-2 ring-primary/50" : ""}`}
                      onClick={() => handleStructureClick(structure.id)}
                    >
                      <div className="flex items-start gap-2">
                        <Checkbox
                          checked={structure.selected}
                          onCheckedChange={() => toggleStructureSelection(structure.id)}
                          onClick={(e) => e.stopPropagation()}
                          className="mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            {structure.type === "sheet" && <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-600" />}
                            {structure.type === "table" && <Table2 className="h-3.5 w-3.5 text-blue-600" />}
                            {structure.type === "csv" && <FileText className="h-3.5 w-3.5 text-green-600" />}
                            <span className="font-medium text-sm truncate">{structure.name}</span>
                          </div>
                          <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                            <span>{structure.columns.length} columns</span>
                            <span>•</span>
                            <span>~{structure.rowCount.toLocaleString()} rows</span>
                            {structure.sampleRows && structure.sampleRows.length > 0 && (
                              <>
                                <span>•</span>
                                <span className="text-green-600">{structure.sampleRows.length} preview</span>
                              </>
                            )}
                          </div>
                          {structure.type === "table" && structure.page !== undefined && (
                            <div className="text-xs text-muted-foreground mt-0.5">
                              Page {structure.page + 1}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Empty state when filtering */}
                {filteredStructures.length === 0 && selectedPdfPage !== "all" && (
                  <div className="text-center py-8 text-muted-foreground text-sm">
                    <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    <p>No tables detected on page {(selectedPdfPage as number) + 1}</p>
                    <p className="text-xs mt-1">Try selecting a different page or "All"</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Step 3: Structure Details - Show when a structure is active */}
          {activeStructure && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-medium">
                    3
                  </div>
                  <div className="flex-1">
                    <CardTitle className="text-base flex items-center gap-2">
                      Configure: {activeStructure.name}
                      {!activeStructure.selected && (
                        <Badge variant="secondary" className="text-xs">Not selected</Badge>
                      )}
                    </CardTitle>
                    <CardDescription>
                      {activeStructure.columns.length} columns detected
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <Tabs defaultValue="preview" className="w-full">
                  <TabsList className="mb-3">
                    <TabsTrigger value="preview" className="gap-1">
                      <Eye className="h-3.5 w-3.5" />
                      Preview
                    </TabsTrigger>
                    <TabsTrigger value="columns" className="gap-1">
                      <Columns3 className="h-3.5 w-3.5" />
                      Columns
                    </TabsTrigger>
                    <TabsTrigger value="settings" className="gap-1">
                      <Settings2 className="h-3.5 w-3.5" />
                      Settings
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="preview" className="mt-0">
                    {activeStructure.sampleRows && activeStructure.sampleRows.length > 0 ? (
                      <>
                        <div className="border rounded-md overflow-auto max-h-64">
                          <table className="w-full text-xs font-mono">
                            <thead className="bg-muted sticky top-0 z-10">
                              <tr>
                                <th className="px-2 py-1.5 text-center font-medium border-r bg-muted/80 w-8">#</th>
                                {activeStructure.columns.map((col) => (
                                  <th key={col.name} className="px-3 py-1.5 text-left font-medium border-r last:border-r-0 whitespace-nowrap">
                                    {col.name}
                                    <span className="ml-1 text-[10px] text-muted-foreground font-normal">({col.type})</span>
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {activeStructure.sampleRows.slice(0, 10).map((row, i) => (
                                <tr key={i} className={`border-t ${i % 2 === 0 ? "bg-background" : "bg-muted/30"} hover:bg-accent/50`}>
                                  <td className="px-2 py-1 text-center text-muted-foreground border-r text-[10px]">{i + 1}</td>
                                  {activeStructure.columns.map((col) => (
                                    <td 
                                      key={col.name} 
                                      className="px-3 py-1 border-r last:border-r-0 truncate max-w-[180px]"
                                      title={String(row[col.name] ?? "")}
                                    >
                                      {String(row[col.name] ?? "")}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                          Showing {Math.min(10, activeStructure.sampleRows.length)} of {activeStructure.rowCount.toLocaleString()} rows
                        </p>
                      </>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground text-sm">
                        <Eye className="h-8 w-8 mx-auto mb-2 opacity-50" />
                        <p>No sample data available</p>
                        <p className="text-xs mt-1">Sample data could not be extracted from this structure</p>
                      </div>
                    )}
                  </TabsContent>

                  <TabsContent value="columns" className="mt-0">
                    {activeMapping ? (
                      <div className="space-y-1">
                        {activeStructure.columns.map((col) => {
                          const mapping = activeMapping.columns.find((m) => m.source === col.name);
                          if (!mapping) return null;
                          const cleanCount = mapping.clean?.length || 0;
                          // Show confidence indicator if available
                          const confidence = col.typeConfidence;
                          const confidenceColor = confidence !== undefined
                            ? confidence >= 0.9 ? "text-green-600" 
                            : confidence >= 0.7 ? "text-yellow-600" 
                            : "text-orange-600"
                            : "";
                          
                          return (
                            <div
                              key={col.name}
                              className={`flex items-center gap-2 p-2 border rounded text-sm ${
                                !mapping.include ? "opacity-50" : ""
                              }`}
                            >
                              <Checkbox
                                checked={mapping.include}
                                onCheckedChange={() => toggleColumn(col.name)}
                              />
                              <div className="flex-1 min-w-0">
                                <span className="font-medium truncate">{col.name}</span>
                                {confidence !== undefined && (
                                  <span className={`ml-1 text-[10px] ${confidenceColor}`} title={`Type confidence: ${Math.round(confidence * 100)}%`}>
                                    ({Math.round(confidence * 100)}%)
                                  </span>
                                )}
                              </div>
                              <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
                              <Input
                                value={mapping.target}
                                onChange={(e) => updateMapping(col.name, "target", e.target.value)}
                                className="w-28 h-7 text-xs"
                                disabled={!mapping.include}
                                placeholder={col.normalizedName}
                              />
                              <Select
                                value={mapping.type}
                                onValueChange={(v) => updateMapping(col.name, "type", v)}
                                disabled={!mapping.include}
                              >
                                <SelectTrigger className={`w-24 h-7 text-xs ${confidence !== undefined && confidence >= 0.8 ? "border-green-300" : ""}`}>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="string">string</SelectItem>
                                  <SelectItem value="integer">integer</SelectItem>
                                  <SelectItem value="decimal">decimal</SelectItem>
                                  <SelectItem value="boolean">boolean</SelectItem>
                                  <SelectItem value="date">date</SelectItem>
                                  <SelectItem value="datetime">datetime</SelectItem>
                                </SelectContent>
                              </Select>
                              {/* Clean rules dropdown */}
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild disabled={!mapping.include}>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className={`h-7 px-2 text-xs ${cleanCount > 0 ? "border-primary text-primary" : ""}`}
                                  >
                                    <Wand2 className="h-3 w-3" />
                                    {cleanCount > 0 && (
                                      <span className="ml-1">{cleanCount}</span>
                                    )}
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-48">
                                  <DropdownMenuLabel className="text-xs">Clean Rules</DropdownMenuLabel>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuCheckboxItem
                                    checked={mapping.clean?.includes("trim")}
                                    onCheckedChange={() => toggleCleanRule(col.name, "trim")}
                                  >
                                    Trim whitespace
                                  </DropdownMenuCheckboxItem>
                                  <DropdownMenuCheckboxItem
                                    checked={mapping.clean?.includes("upper")}
                                    onCheckedChange={() => toggleCleanRule(col.name, "upper")}
                                  >
                                    Uppercase
                                  </DropdownMenuCheckboxItem>
                                  <DropdownMenuCheckboxItem
                                    checked={mapping.clean?.includes("lower")}
                                    onCheckedChange={() => toggleCleanRule(col.name, "lower")}
                                  >
                                    Lowercase
                                  </DropdownMenuCheckboxItem>
                                  <DropdownMenuCheckboxItem
                                    checked={mapping.clean?.includes("remove_accents")}
                                    onCheckedChange={() => toggleCleanRule(col.name, "remove_accents")}
                                  >
                                    Remove accents
                                  </DropdownMenuCheckboxItem>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuCheckboxItem
                                    checked={mapping.clean?.includes("currency_to_decimal")}
                                    onCheckedChange={() => toggleCleanRule(col.name, "currency_to_decimal")}
                                  >
                                    Currency → Decimal
                                  </DropdownMenuCheckboxItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </div>
                          );
                        })}
                      </div>
                    ) : activeStructure.columns.length > 0 ? (
                      <div className="space-y-1">
                        {activeStructure.columns.map((col) => (
                          <div key={col.name} className="flex items-center gap-3 p-2 border rounded text-sm">
                            <div className="flex-1 min-w-0">
                              <span className="font-medium">{col.name}</span>
                            </div>
                            <Badge variant="outline" className="text-xs">{col.type}</Badge>
                          </div>
                        ))}
                        <p className="text-xs text-muted-foreground mt-2">
                          Select this structure for import to configure column mapping
                        </p>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground text-sm">
                        <Columns3 className="h-8 w-8 mx-auto mb-2 opacity-50" />
                        <p>No column data available</p>
                        <p className="text-xs mt-1">Backend could not detect columns for this structure</p>
                      </div>
                    )}
                  </TabsContent>

                  <TabsContent value="settings" className="mt-0">
                    {activeMapping ? (
                      <div className="space-y-4">
                        {/* Structure-specific settings */}
                        <div className="grid gap-4 sm:grid-cols-2">
                          <div>
                            <Label className="text-xs">Header Row</Label>
                            <Input
                              type="number"
                              min={0}
                              value={activeMapping.headerRow}
                              onChange={(e) => updateStructureSetting("headerRow", Number(e.target.value))}
                              className="mt-1 h-8"
                            />
                            <p className="text-xs text-muted-foreground mt-1">Row containing column headers (0-indexed)</p>
                          </div>
                          <div>
                            <Label className="text-xs">Skip Rows</Label>
                            <Input
                              type="number"
                              min={0}
                              value={activeMapping.skipRows}
                              onChange={(e) => updateStructureSetting("skipRows", Number(e.target.value))}
                              className="mt-1 h-8"
                            />
                            <p className="text-xs text-muted-foreground mt-1">Rows to skip before header</p>
                          </div>
                        </div>
                        
                        {/* CSV-specific settings */}
                        {fileType === "csv" && (
                          <div className="grid gap-4 sm:grid-cols-2 pt-2 border-t">
                            <div>
                              <Label className="text-xs">Delimiter</Label>
                              <Select value={csvDelimiter} onValueChange={setCsvDelimiter}>
                                <SelectTrigger className="mt-1 h-8">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value=",">Comma (,)</SelectItem>
                                  <SelectItem value=";">Semicolon (;)</SelectItem>
                                  <SelectItem value="\t">Tab</SelectItem>
                                  <SelectItem value="|">Pipe (|)</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                            <div>
                              <Label className="text-xs">Encoding</Label>
                              <Select value={csvEncoding} onValueChange={setCsvEncoding}>
                                <SelectTrigger className="mt-1 h-8">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="utf-8">UTF-8</SelectItem>
                                  <SelectItem value="latin-1">Latin-1 (ISO-8859-1)</SelectItem>
                                  <SelectItem value="cp1252">Windows-1252</SelectItem>
                                </SelectContent>
                              </Select>
                            </div>
                          </div>
                        )}
                        
                        {/* Date format settings */}
                        <div className="grid gap-4 sm:grid-cols-2 pt-2 border-t">
                          <div>
                            <Label className="text-xs">Date Format</Label>
                            <Select value={dateFormat} onValueChange={setDateFormat}>
                              <SelectTrigger className="mt-1 h-8">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="DD/MM/YYYY">DD/MM/YYYY (31/12/2024)</SelectItem>
                                <SelectItem value="MM/DD/YYYY">MM/DD/YYYY (12/31/2024)</SelectItem>
                                <SelectItem value="YYYY-MM-DD">YYYY-MM-DD (2024-12-31)</SelectItem>
                                <SelectItem value="DD-MM-YYYY">DD-MM-YYYY (31-12-2024)</SelectItem>
                                <SelectItem value="DD.MM.YYYY">DD.MM.YYYY (31.12.2024)</SelectItem>
                              </SelectContent>
                            </Select>
                            <p className="text-xs text-muted-foreground mt-1">Format for date columns</p>
                          </div>
                          <div>
                            <Label className="text-xs">Datetime Format</Label>
                            <Select value={datetimeFormat} onValueChange={setDatetimeFormat}>
                              <SelectTrigger className="mt-1 h-8">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="YYYY-MM-DD HH:mm:ss">YYYY-MM-DD HH:mm:ss</SelectItem>
                                <SelectItem value="DD/MM/YYYY HH:mm:ss">DD/MM/YYYY HH:mm:ss</SelectItem>
                                <SelectItem value="MM/DD/YYYY HH:mm:ss">MM/DD/YYYY HH:mm:ss</SelectItem>
                                <SelectItem value="DD/MM/YYYY HH:mm">DD/MM/YYYY HH:mm</SelectItem>
                              </SelectContent>
                            </Select>
                            <p className="text-xs text-muted-foreground mt-1">Format for datetime columns</p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-8 text-muted-foreground text-sm">
                        <Settings2 className="h-8 w-8 mx-auto mb-2 opacity-50" />
                        <p>Settings not available</p>
                        <p className="text-xs mt-1">Select this structure for import to configure settings</p>
                      </div>
                    )}
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          )}

          {/* Step 4: Name & Save */}
          {selectedStructures.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-medium">
                    4
                  </div>
                  <div>
                    <CardTitle className="text-base">Save Import Process</CardTitle>
                    <CardDescription>
                      Name this configuration to reuse it for similar files
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-3 items-end">
                  <div className="flex-1">
                    <Label className="text-xs">Process Name</Label>
                    <Input
                      value={processName}
                      onChange={(e) => setProcessName(e.target.value)}
                      placeholder="e.g. Monthly Sales Import"
                      className="mt-1"
                    />
                  </div>
                </div>
                
                {/* Import as JSON option */}
                <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/30">
                  <div className="space-y-0.5">
                    <Label className="text-sm font-medium">Import as JSON</Label>
                    <p className="text-xs text-muted-foreground">
                      Skip DataFrame creation and output raw JSON data instead
                    </p>
                  </div>
                  <Switch
                    checked={importAsJson}
                    onCheckedChange={setImportAsJson}
                  />
                </div>
                
                <div className="flex justify-end gap-2">
                  <Button onClick={handleSave} disabled={isSaving || !processName.trim()} variant="outline">
                    {isSaving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                    {id ? "Update" : "Create"} Import Process
                  </Button>
                  {id && (
                    <Button onClick={handleRun} disabled={runMutation.isPending || !selectedFileId}>
                      {runMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Play className="h-4 w-4 mr-2" />}
                      Run Import
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Run Result */}
          {runResult && (
            <Card className={runResult.status === "failed" ? "border-destructive" : runResult.status === "success" ? "border-green-500" : ""}>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-3">
                  <div className={`h-8 w-8 rounded-full flex items-center justify-center ${
                    runResult.status === "failed" ? "bg-destructive/10 text-destructive" :
                    runResult.status === "success" ? "bg-green-500/10 text-green-600" :
                    "bg-muted text-muted-foreground"
                  }`}>
                    {runResult.status === "pending" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : runResult.status === "success" ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <AlertCircle className="h-4 w-4" />
                    )}
                  </div>
                  <div>
                    <CardTitle className="text-base">
                      {runResult.status === "pending" ? "Running..." :
                       runResult.status === "success" ? "Import Successful" :
                       "Import Failed"}
                    </CardTitle>
                    {runResult.status === "success" && runResult.resultsetIds && runResult.resultsetIds.length > 0 && (
                      <CardDescription>
                        Created {runResult.resultsetIds.length} dataset(s)
                      </CardDescription>
                    )}
                  </div>
                </div>
              </CardHeader>
              {runResult.status === "failed" && (
                <CardContent className="space-y-3">
                  {runResult.errorMessage && (
                    <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-md">
                      <p className="text-sm font-medium text-destructive">Error Message:</p>
                      <p className="text-sm text-destructive/80 mt-1 font-mono break-all">
                        {runResult.errorMessage}
                      </p>
                    </div>
                  )}
                  {runResult.shapeMatch?.reasons && runResult.shapeMatch.reasons.length > 0 && (
                    <div className="p-3 bg-muted rounded-md">
                      <p className="text-sm font-medium">Shape Match Issues:</p>
                      <ul className="text-xs text-muted-foreground mt-1 space-y-1">
                        {runResult.shapeMatch.reasons.map((reason, i) => (
                          <li key={i} className="font-mono">• {reason}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Check the parser settings (delimiter, encoding, header row) and try again.
                  </p>
                </CardContent>
              )}
              {runResult.status === "success" && runResult.resultsetIds && runResult.resultsetIds.length > 0 && (
                <CardContent>
                  <p className="text-sm font-medium mb-2">Created Datasets:</p>
                  <div className="space-y-1">
                    {runResult.resultsetIds.map((rsId) => (
                      <div key={rsId} className="flex items-center gap-2 p-2 bg-muted rounded text-xs font-mono">
                        <Check className="h-3 w-3 text-green-600" />
                        {rsId}
                      </div>
                    ))}
                  </div>
                </CardContent>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
