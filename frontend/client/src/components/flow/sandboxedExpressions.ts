import type { AvailableDataField } from "./types";

// ============================================================================
// Spec: ctx.* contract + sandboxed expressions
// ============================================================================

/**
 * Roots under `ctx.<root>` that are reserved and must not be user-defined.
 * Also: any root starting with "$" is reserved.
 */
export const RESERVED_CTX_ROOTS = new Set<string>([
  "config",
  "nodes",
  "$input",
  "$trigger",
  "$outputs",
  "$loops",
  "$sandbox",
  "tenant_id",
  "execution_id",
  "flow_execution_id",
]);

export const CTX_SEGMENT_RE = /^[A-Za-z0-9_-]+$/;

export function isReservedCtxRoot(root: string): boolean {
  if (!root) return false;
  if (root.startsWith("$")) return true;
  return RESERVED_CTX_ROOTS.has(root);
}

export function validateCtxPath(ctxPath: string): { ok: boolean; reason?: string; root?: string } {
  const raw = (ctxPath || "").trim();
  if (!raw) return { ok: false, reason: "ctx_path is required" };
  if (!raw.startsWith("ctx.")) return { ok: false, reason: 'ctx_path must start with "ctx."' };

  const parts = raw.split(".");
  if (parts.length < 2) return { ok: false, reason: 'ctx_path must be like "ctx.<seg>.<seg>..."' };
  if (parts[0] !== "ctx") return { ok: false, reason: 'ctx_path must start with "ctx."' };

  const root = parts[1] ?? "";
  if (!root) return { ok: false, reason: 'ctx_path must include a root segment after "ctx."' };
  if (!CTX_SEGMENT_RE.test(root)) return { ok: false, reason: `Invalid ctx root segment "${root}"` };
  if (isReservedCtxRoot(root)) {
    return { ok: false, reason: `ctx root "${root}" is reserved`, root };
  }

  for (let i = 1; i < parts.length; i++) {
    const seg = parts[i];
    if (!seg) return { ok: false, reason: "ctx_path contains an empty segment (..)" };
    if (!CTX_SEGMENT_RE.test(seg)) {
      return { ok: false, reason: `Invalid segment "${seg}". Allowed: [A-Za-z0-9_-]` };
    }
  }

  return { ok: true, root };
}

/**
 * Spec: Normalize source_path must be one of:
 * - input.body.*
 * - nodes.<nodeId>.output.*
 * - config.*
 *
 * No indexing, no calls, no expressions.
 */
export function validateNormalizeSourcePath(sourcePath: string): { ok: boolean; reason?: string } {
  const raw = (sourcePath || "").trim();
  if (!raw) return { ok: false, reason: "source_path is required" };

  // Hard-bans: indexing / calls / braces / template syntax.
  // (We keep this strict; if backend later supports more, we can relax.)
  if (/[()[\]{}]/.test(raw)) return { ok: false, reason: "source_path cannot contain calls, indexing or literals" };
  if (raw.includes("${") || raw.includes("{{") || raw.includes("}}")) return { ok: false, reason: "source_path must be a plain path (no templates)" };

  const seg = "[A-Za-z0-9_-]+";
  const tail = `(?:\\.${seg})*`;

  const inputRe = new RegExp(`^input\\.body(?:\\.${seg}${tail})?$`);
  const configRe = new RegExp(`^config(?:\\.${seg}${tail})?$`);
  const nodesRe = new RegExp(`^nodes\\.${seg}\\.output(?:\\.${seg}${tail})?$`);

  if (!inputRe.test(raw) && !configRe.test(raw) && !nodesRe.test(raw)) {
    return {
      ok: false,
      reason: 'source_path must start with "input.body.", "nodes.<nodeId>.output." or "config."',
    };
  }

  return { ok: true };
}

// ============================================================================
// Sandboxed expression validation (ctx-only)
// ============================================================================

export type SandboxedExprIssue = {
  message: string;
  index?: number;
};

export type SandboxedExprValidation = {
  ok: boolean;
  errors: SandboxedExprIssue[];
  referencedCtxPaths: string[];
};

type Token =
  | { type: "lparen"; value: "("; index: number }
  | { type: "rparen"; value: ")"; index: number }
  | { type: "op"; value: "==" | "!=" | "<" | "<=" | ">" | ">="; index: number }
  | { type: "kw"; value: "and" | "or" | "not" | "is" | "in"; index: number }
  | { type: "null"; value: "None" | "null"; index: number }
  | { type: "bool"; value: "True" | "False" | "true" | "false"; index: number }
  | { type: "number"; value: string; index: number }
  | { type: "string"; value: string; index: number }
  | { type: "ctx_path"; value: string; index: number }
  | { type: "identifier"; value: string; index: number };

function tokenizeSandboxedExpr(input: string): { tokens: Token[]; errors: SandboxedExprIssue[] } {
  const s = input ?? "";
  const tokens: Token[] = [];
  const errors: SandboxedExprIssue[] = [];

  const isWs = (c: string) => c === " " || c === "\n" || c === "\t" || c === "\r";
  const isDigit = (c: string) => c >= "0" && c <= "9";
  const isIdentStart = (c: string) => /[A-Za-z_]/.test(c);
  const isIdent = (c: string) => /[A-Za-z0-9_]/.test(c);

  let i = 0;
  while (i < s.length) {
    const c = s[i];

    if (isWs(c)) {
      i++;
      continue;
    }

    // Strings
    if (c === "'" || c === '"') {
      const quote = c;
      const start = i;
      i++;
      let out = "";
      let closed = false;
      while (i < s.length) {
        const ch = s[i];
        if (ch === "\\") {
          // Consume escape
          if (i + 1 < s.length) {
            out += s[i + 1];
            i += 2;
            continue;
          }
          i++;
          continue;
        }
        if (ch === quote) {
          closed = true;
          i++;
          break;
        }
        out += ch;
        i++;
      }
      if (!closed) {
        errors.push({ message: "Unterminated string literal", index: start });
      }
      tokens.push({ type: "string", value: out, index: start });
      continue;
    }

    // Hard forbidden punctuation (outside strings)
    if (c === "[" || c === "]") {
      errors.push({ message: "Indexing is not allowed (no [] in sandboxed expressions)", index: i });
      i++;
      continue;
    }
    if (c === "{" || c === "}") {
      errors.push({ message: "List/dict/set literals are not allowed (no {} in sandboxed expressions)", index: i });
      i++;
      continue;
    }

    // Parentheses (grouping only; calls are rejected later)
    if (c === "(") {
      tokens.push({ type: "lparen", value: "(", index: i });
      i++;
      continue;
    }
    if (c === ")") {
      tokens.push({ type: "rparen", value: ")", index: i });
      i++;
      continue;
    }

    // Operators
    const two = s.slice(i, i + 2);
    if (two === "==" || two === "!=" || two === "<=" || two === ">=") {
      tokens.push({ type: "op", value: two as any, index: i });
      i += 2;
      continue;
    }
    if (c === "<" || c === ">") {
      tokens.push({ type: "op", value: c as any, index: i });
      i++;
      continue;
    }

    // Explicitly forbid arithmetic / ternary / bitwise
    if ("+-*/%?:|&^~".includes(c)) {
      errors.push({ message: `Operator "${c}" is not allowed in sandboxed expressions`, index: i });
      i++;
      continue;
    }

    // ctx path (supports segments with dash/underscore)
    if (s.startsWith("ctx.", i)) {
      const start = i;
      i += 4; // "ctx."
      let path = "ctx.";
      // Need at least one segment
      const segRe = /[A-Za-z0-9_-]/;
      let seg = "";
      while (i < s.length) {
        const ch = s[i];
        if (ch === ".") {
          if (!seg) break; // stop on empty seg (parser will error later)
          path += seg + ".";
          seg = "";
          i++;
          continue;
        }
        if (!segRe.test(ch)) break;
        seg += ch;
        i++;
      }
      if (seg) {
        path += seg;
      } else if (path.endsWith(".")) {
        // Keep as-is; will be validated by parser
      }
      tokens.push({ type: "ctx_path", value: path, index: start });
      continue;
    }

    // Numbers (simple)
    if (isDigit(c)) {
      const start = i;
      let num = "";
      while (i < s.length && (isDigit(s[i]) || s[i] === ".")) {
        num += s[i];
        i++;
      }
      tokens.push({ type: "number", value: num, index: start });
      continue;
    }

    // Identifiers/keywords
    if (isIdentStart(c)) {
      const start = i;
      let word = "";
      while (i < s.length && isIdent(s[i])) {
        word += s[i];
        i++;
      }
      if (word === "and" || word === "or" || word === "not" || word === "is" || word === "in") {
        tokens.push({ type: "kw", value: word, index: start });
      } else if (word === "None" || word === "null") {
        tokens.push({ type: "null", value: word as any, index: start });
      } else if (word === "True" || word === "False" || word === "true" || word === "false") {
        tokens.push({ type: "bool", value: word as any, index: start });
      } else {
        // Explicit UX errors for common forbidden namespaces/names.
        if (word === "input" || word === "payload" || word === "nodes" || word === "config" || word === "system") {
          errors.push({
            message: `Forbidden name "${word}". Sandboxed expressions can only read ctx.*`,
            index: start,
          });
        }
        tokens.push({ type: "identifier", value: word, index: start });
      }
      continue;
    }

    // Dots outside ctx paths are not allowed (avoids input.body.* etc)
    if (c === ".") {
      errors.push({ message: 'Only "ctx.<...>" is allowed (unexpected ".")', index: i });
      i++;
      continue;
    }

    // Anything else is invalid
    errors.push({ message: `Unexpected character "${c}"`, index: i });
    i++;
  }

  // Disallow calls: identifier '(' or ctx_path '('
  for (let t = 0; t < tokens.length - 1; t++) {
    const a = tokens[t];
    const b = tokens[t + 1];
    if ((a.type === "identifier" || a.type === "ctx_path") && b.type === "lparen") {
      errors.push({ message: "Calls are not allowed in sandboxed expressions", index: a.index });
    }
  }

  // Disallow any identifier other than ctx (ctx is tokenized as ctx_path)
  for (const tok of tokens) {
    if (tok.type === "identifier") {
      errors.push({
        message: `Only ctx.* reads are allowed (found "${tok.value}")`,
        index: tok.index,
      });
    }
  }

  // Disallow ctx reserved roots
  for (const tok of tokens) {
    if (tok.type === "ctx_path") {
      const parts = tok.value.split(".");
      const root = parts[1] ?? "";
      if (isReservedCtxRoot(root)) {
        errors.push({
          message: `ctx.${root} is reserved and cannot be accessed`,
          index: tok.index,
        });
      }
    }
  }

  return { tokens, errors };
}

// Recursive descent parser for a small, safe boolean expression language.
// Grammar:
//   expr    := orExpr
//   orExpr  := andExpr ("or" andExpr)*
//   andExpr := notExpr ("and" notExpr)*
//   notExpr := "not" notExpr | comp
//   comp    := term (compOp term)?
//   compOp  := ("=="|"!="|"<"|"<="|">"|">=")
//           | "is" ["not"]
//           | ["not"] "in"         // only supports "in" and "not in"
//   term    := literal | ctxPath | "(" expr ")"
function parseSandboxedTokens(tokens: Token[]): SandboxedExprIssue[] {
  const errors: SandboxedExprIssue[] = [];
  let i = 0;

  const peek = () => tokens[i];
  const consume = () => tokens[i++];

  const matchKw = (value: Token["value"]) => {
    const t = peek();
    if (t && t.type === "kw" && t.value === value) {
      consume();
      return true;
    }
    return false;
  };

  const parseExpr = (): boolean => parseOr();

  const parseOr = (): boolean => {
    if (!parseAnd()) return false;
    while (matchKw("or")) {
      if (!parseAnd()) return false;
    }
    return true;
  };

  const parseAnd = (): boolean => {
    if (!parseNot()) return false;
    while (matchKw("and")) {
      if (!parseNot()) return false;
    }
    return true;
  };

  const parseNot = (): boolean => {
    if (matchKw("not")) {
      return parseNot();
    }
    return parseComp();
  };

  const parseComp = (): boolean => {
    if (!parseTerm()) return false;

    // Optional comparator
    const t = peek();
    if (!t) return true;

    // Symbol comparators
    if (t.type === "op") {
      consume();
      if (!parseTerm()) return false;
      return true;
    }

    // "is" ["not"]
    if (t.type === "kw" && t.value === "is") {
      consume();
      matchKw("not");
      if (!parseTerm()) return false;
      return true;
    }

    // ["not"] "in"
    if (t.type === "kw" && t.value === "not") {
      // Lookahead for "not in"
      const t2 = tokens[i + 1];
      if (t2 && t2.type === "kw" && t2.value === "in") {
        consume(); // not
        consume(); // in
        if (!parseTerm()) return false;
        return true;
      }
    }

    if (t.type === "kw" && t.value === "in") {
      consume();
      if (!parseTerm()) return false;
      return true;
    }

    return true;
  };

  const parseTerm = (): boolean => {
    const t = peek();
    if (!t) {
      errors.push({ message: "Unexpected end of expression" });
      return false;
    }

    if (t.type === "lparen") {
      consume();
      if (!parseExpr()) return false;
      const close = peek();
      if (!close || close.type !== "rparen") {
        errors.push({ message: 'Expected ")"', index: t.index });
        return false;
      }
      consume();
      return true;
    }

    if (t.type === "ctx_path") {
      // must be ctx.<seg>.<seg>... (at least one segment)
      const parts = t.value.split(".");
      if (parts.length < 2 || !parts[1]) {
        errors.push({ message: 'ctx path must be like "ctx.foo.bar"', index: t.index });
        consume();
        return true;
      }
      consume();
      return true;
    }

    if (t.type === "string" || t.type === "number" || t.type === "bool" || t.type === "null") {
      consume();
      return true;
    }

    errors.push({ message: `Unexpected token`, index: t.index });
    consume();
    return true;
  };

  if (tokens.length === 0) return errors;
  const ok = parseExpr();
  if (!ok) return errors;
  if (i < tokens.length) {
    errors.push({ message: `Unexpected token after end of expression`, index: tokens[i].index });
  }
  return errors;
}

export function validateSandboxedExpression(expr: string): SandboxedExprValidation {
  const raw = (expr ?? "").trim();
  if (!raw) return { ok: true, errors: [], referencedCtxPaths: [] };

  const { tokens, errors: lexErrors } = tokenizeSandboxedExpr(raw);
  const parseErrors = parseSandboxedTokens(tokens);

  const errors = [...lexErrors, ...parseErrors];

  // Extract referenced ctx paths (dedup)
  const referenced = Array.from(
    new Set(tokens.filter((t) => t.type === "ctx_path").map((t) => (t as any).value as string))
  );

  return {
    ok: errors.length === 0,
    errors,
    referencedCtxPaths: referenced,
  };
}

// ============================================================================
// ctx_schema helpers (flatten for autocomplete)
// ============================================================================

type CtxSchemaNode =
  | { kind: "object"; properties: Record<string, CtxSchemaNode> }
  | { kind: "array"; items?: CtxSchemaNode }
  | { kind: "primitive"; type?: string }
  | { kind: "unknown" }
  | Record<string, any>;

function isSchemaNodeLike(x: any): x is { kind: string } {
  return Boolean(x && typeof x === "object" && typeof x.kind === "string");
}

function toKind(node: any): string {
  const k = node?.kind;
  if (k === "object" || k === "array" || k === "primitive" || k === "unknown") return k;
  return "unknown";
}

export function flattenCtxSchemaToAvailableData(ctxSchema: unknown): AvailableDataField[] {
  // Backend may return either:
  // - SchemaNode-like object for ctx root (object)
  // - { ctx: <SchemaNode> } (rare)
  // We normalize to a SchemaNode-like root describing ctx contents.
  const raw = ctxSchema as any;
  const rootNode: any =
    (raw && isSchemaNodeLike(raw) ? raw : raw?.ctx && isSchemaNodeLike(raw.ctx) ? raw.ctx : undefined) ?? undefined;

  if (!rootNode) return [];

  const out: AvailableDataField[] = [];

  const walk = (node: any, path: string) => {
    const k = toKind(node);
    if (k === "object") {
      const props = (node as any).properties;
      if (!props || typeof props !== "object") return;
      for (const [key, child] of Object.entries(props)) {
        if (!key) continue;
        const nextPath = `${path}.${key}`;
        const childKind = toKind(child);
        if (childKind === "object") {
          // Also include object root as a selectable token
          out.push({ key: nextPath, type: "object", source: "ctx_schema" });
          walk(child, nextPath);
        } else if (childKind === "array") {
          out.push({ key: nextPath, type: "array", source: "ctx_schema" });
          // No deep expansion: indexing is forbidden in sandboxed expressions.
        } else if (childKind === "primitive") {
          out.push({ key: nextPath, type: (child as any).type || "primitive", source: "ctx_schema" });
        } else {
          out.push({ key: nextPath, type: "unknown", source: "ctx_schema" });
        }
      }
      return;
    }

    // Non-object at root: still expose it as ctx (rare)
    out.push({ key: path, type: k, source: "ctx_schema" });
  };

  walk(rootNode, "ctx");

  // Dedup + stable-ish order
  const seen = new Set<string>();
  return out.filter((f) => {
    if (seen.has(f.key)) return false;
    seen.add(f.key);
    return true;
  });
}

export function ctxPathExistsInFlattenedSchema(ctxSchemaFields: AvailableDataField[], ctxPath: string): boolean {
  const p = (ctxPath || "").trim();
  if (!p.startsWith("ctx.")) return false;
  // Existence check is prefix-friendly: if schema defines ctx.a.b, we also accept ctx.a (object root)
  // but we only warn on fully-qualified paths not present.
  return ctxSchemaFields.some((f) => f.key === p);
}

