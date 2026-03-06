import { PortDefinition } from "./types";

/**
 * BranchRule - Represents a branch condition rule
 * v2 spec: includes id field
 */
export interface BranchRule {
  id: string;
  name: string;
  expr?: string;
}

/**
 * BranchConfig - Configuration for a branch node
 * v2 spec: mode field, else is string (output name) not boolean
 */
export interface BranchConfig extends Record<string, any> {
  rules: BranchRule[];
  mode?: "first" | "all";
  // Optional else output (when config.else === "else")
}

// No default rules - let users start with empty branch and add rules they need.
// Default output is implicit and always present (no rule needed).
export const DEFAULT_BRANCH_RULES: BranchRule[] = [];

/**
 * Generate a unique ID for a branch rule
 */
function generateRuleId(index: number): string {
  return `rule_${index + 1}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

export const isBranchNodeType = (nodeType?: string) => {
  if (!nodeType) return false;
  const key = nodeType.toLowerCase();
  // Branch (multi-rule) nodes only.
  // IMPORTANT: `logic_condition` is a control node but NOT a multi-output branch with rules.
  // Keeping this narrow avoids accidentally treating condition nodes as dynamic branches.
  return key.includes("branch") && !key.includes("condition");
};

const cloneSchema = (schema?: Record<string, any>) => {
  if (!schema) return undefined;
  return JSON.parse(JSON.stringify(schema));
};

const clonePortDefinition = (port?: PortDefinition): PortDefinition | undefined => {
  if (!port) return undefined;
  return {
    ...port,
    schema: port.schema ? cloneSchema(port.schema) : undefined,
  };
};

const sanitizeOutputName = (raw: string, index: number): string => {
  const trimmed = String(raw ?? "").trim();
  const underscored = trimmed.replace(/\s+/g, "_");
  const cleaned = underscored.replace(/[^A-Za-z0-9_-]/g, "");
  return cleaned || `rule_${index + 1}`;
};

export const normalizeBranchConfig = (config?: Record<string, any>): BranchConfig => {
  const base: Record<string, any> = typeof config === "object" && config !== null ? { ...config } : {};
  const rawRules = Array.isArray(base.rules) ? base.rules : [];
  
  // Normalize rules: sanitize & unique names; keep id for compat (not used as handle)
  const seen = new Set<string>();
  const normalizedRules = (rawRules.length ? rawRules : DEFAULT_BRANCH_RULES).map((rule, index) => {
    let name = sanitizeOutputName(rule?.name ?? `rule_${index + 1}`, index);
    // ensure uniqueness
    while (seen.has(name)) {
      name = `${name}_${Math.floor(Math.random() * 1000)}`;
    }
    seen.add(name);
    return {
      id: rule?.id || generateRuleId(index),
      name,
      expr: typeof rule?.expr === "string" ? rule.expr : "",
    };
  });

  base.rules = normalizedRules;
  
  // v2 spec: mode field (default "first")
  if (!base.mode || (base.mode !== "first" && base.mode !== "all")) {
    base.mode = "first";
  }

  // Optional else: normalize to string "else" when truthy, otherwise undefined
  if (typeof base.else === "boolean") {
    base.else = base.else ? "else" : undefined;
  } else if (typeof base.else === "string") {
    base.else = base.else.trim().toLowerCase() === "else" ? "else" : undefined;
  } else {
    base.else = undefined;
  }

  return base as BranchConfig;
};

/**
 * Derive branch output names from config
 * v2 spec: outputs are rule names + else output name (if provided)
 */
export const deriveBranchOutputs = (config: BranchConfig): string[] => {
  const outputs = config.rules.map((rule, index) => rule?.name?.trim() || `rule_${index + 1}`);
  // Include else only when enabled
  if (config.else === "else") {
    outputs.push("else");
  }

  return outputs;
};

/**
 * Derive stable handle IDs for branch outputs
 * Uses rule.id for rules and "else" for else output
 * This ensures handles remain stable when rule names change
 */
// Handles are simply output names; stable IDs are not used.
export const buildBranchOutPortMap = (
  config: BranchConfig,
  template?: PortDefinition
): Record<string, PortDefinition> => {
  const outputs = deriveBranchOutputs(config);
  const map: Record<string, PortDefinition> = {};

  outputs.forEach((name) => {
    const cloned = clonePortDefinition(template);
    map[name] = cloned
      ? {
          ...cloned,
          name,
        }
      : { name };
  });

  return map;
};
