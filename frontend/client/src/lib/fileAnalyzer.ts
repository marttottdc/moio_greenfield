import Papa from "papaparse";
import * as XLSX from "xlsx";

export type DetectedColumn = {
  name: string;
  type: "string" | "integer" | "decimal" | "boolean" | "date" | "datetime";
};

export type FileAnalysisResult = {
  detected_schema: DetectedColumn[];
  sample_rows: Record<string, any>[];
  row_count: number;
  warnings: string[];
  detected_delimiter?: string;
  detected_sheets?: Array<{ name: string; index: number }>;
  detected_header_row?: number;
  suggested_skip_rows?: number;
};

const COMMON_DELIMITERS = [",", ";", "\t", "|"] as const;

export function detectDelimiter(text: string): string {
  let best = ",";
  let bestCount = 0;
  for (const delimiter of COMMON_DELIMITERS) {
    const firstLine = text.split(/\r?\n/)[0] ?? "";
    const count = firstLine.split(delimiter).length;
    if (count > bestCount) {
      bestCount = count;
      best = delimiter;
    }
  }
  return best;
}

function detectDataType(value: any): DetectedColumn["type"] {
  if (value === null || value === undefined || value === "") return "string";
  if (typeof value === "boolean") return "boolean";
  const str = String(value).trim();
  if (str === "") return "string";
  if (str.toLowerCase() === "true" || str.toLowerCase() === "false") return "boolean";
  const intVal = parseInt(str, 10);
  const floatVal = parseFloat(str);
  if (!Number.isNaN(intVal) && String(intVal) === str) return "integer";
  if (!Number.isNaN(floatVal) && str.match(/^-?\d+(\.\d+)?$/)) return "decimal";
  const date = new Date(str);
  if (!Number.isNaN(date.getTime())) {
    return str.length > 10 ? "datetime" : "date";
  }
  return "string";
}

function detectSchema(rows: Record<string, any>[], header: string[]): DetectedColumn[] {
  return header.map((col) => {
    const samples = rows.slice(0, 20).map((r) => r[col]);
    const types = samples.map(detectDataType);
    // pick most frequent type
    const freq = types.reduce<Record<string, number>>((acc, t) => {
      acc[t] = (acc[t] ?? 0) + 1;
      return acc;
    }, {});
    const bestType = (Object.entries(freq).sort((a, b) => b[1] - a[1])[0]?.[0] ??
      "string") as DetectedColumn["type"];
    return { name: col, type: bestType };
  });
}

function findHeaderRow(lines: string[], delimiter: string): number {
  // Heuristic: choose the first line with the modal column count and majority non-numeric
  const counts = lines.slice(0, 30).map((line) => line.split(delimiter).length);
  const freq = counts.reduce<Record<number, number>>((acc, n) => {
    acc[n] = (acc[n] ?? 0) + 1;
    return acc;
  }, {});
  const modalCount = Number(Object.entries(freq).sort((a, b) => b[1] - a[1])[0]?.[0] ?? counts[0] ?? 0);

  const isMostlyText = (cells: string[]) => {
    const nonNumeric = cells.filter((c) => isNaN(Number(c.trim()))).length;
    return nonNumeric >= cells.length / 2;
  };

  for (let i = 0; i < Math.min(lines.length, 30); i++) {
    const cells = lines[i].split(delimiter);
    if (cells.length === modalCount && isMostlyText(cells)) return i;
  }
  return 0;
}

export async function analyzeCSVFile(file: File): Promise<FileAnalysisResult> {
  const text = await file.text();
  const delimiter = detectDelimiter(text);

  const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
  const headerRow = findHeaderRow(lines, delimiter);
  const textToParse = lines.slice(headerRow).join("\n");

  const parsed = Papa.parse<Record<string, any>>(textToParse, {
    header: true,
    dynamicTyping: false,
    skipEmptyLines: true,
    delimiter,
  });

  const rows = parsed.data || [];
  const header = parsed.meta.fields || [];

  const schema = detectSchema(rows, header);

  return {
    detected_schema: schema,
    sample_rows: rows.slice(0, 5),
    row_count: rows.length,
    warnings: [],
    detected_delimiter: delimiter,
    detected_header_row: headerRow,
    suggested_skip_rows: headerRow > 0 ? headerRow : 0,
  };
}

export async function analyzeExcelFile(file: File): Promise<FileAnalysisResult> {
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: "array" });
  const sheetNames = workbook.SheetNames || [];
  const sheetName = sheetNames[0];
  const sheet = sheetName ? workbook.Sheets[sheetName] : undefined;

  if (!sheet) {
    throw new Error("No sheets found in Excel file");
  }

  const rawRows = XLSX.utils.sheet_to_json<any[]>(sheet, { header: 1, defval: "" }) as any[][];
  const headerRowIdx = rawRows.findIndex((r) => (r || []).some((v) => String(v).trim() !== ""));
  const headerRowSafe = headerRowIdx >= 0 ? headerRowIdx : 0;
  const header = (rawRows[headerRowSafe] || []).map((c) => String(c));
  const dataRows = rawRows.slice(headerRowSafe + 1);
  const rows: Record<string, any>[] = dataRows.map((row) => {
    const obj: Record<string, any> = {};
    header.forEach((col, idx) => {
      obj[col] = row[idx];
    });
    return obj;
  });

  const schema = detectSchema(rows, header);

  return {
    detected_schema: schema,
    sample_rows: rows.slice(0, 5),
    row_count: rows.length,
    warnings: [],
    detected_sheets: sheetNames.map((name, idx) => ({ name, index: idx })),
    detected_header_row: headerRowSafe,
    suggested_skip_rows: headerRowSafe > 0 ? headerRowSafe : 0,
  };
}

export function generatePreliminaryMapping(columns: DetectedColumn[]) {
  return columns.map((col) => ({
    source: col.name,
    target: col.name.toLowerCase().replace(/\s+/g, "_"),
    type: col.type,
    clean: [] as string[],
  }));
}

export async function analyzeLocalFile(file: File): Promise<FileAnalysisResult> {
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".csv")) {
    return analyzeCSVFile(file);
  }
  if (lower.endsWith(".xls") || lower.endsWith(".xlsx")) {
    return analyzeExcelFile(file);
  }
  throw new Error("Unsupported file type. Please upload CSV or Excel.");
}
