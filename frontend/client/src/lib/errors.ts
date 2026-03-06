/**
 * Error handling utilities that are verbose in dev and polite in prod
 */

const isDevelopment = import.meta.env.DEV;

export interface ErrorDisplayInfo {
  // Main summary
  summary: string;
  statusCode?: number;
  endpoint?: string;
  
  // Expandable details (only in dev)
  errorMessage?: string;
  stackTrace?: string;
  requestDetails?: string;
  responseBody?: string;
}

/**
 * Extract error information from ApiError or generic Error
 */
function extractErrorInfo(error: unknown): {
  statusCode?: number;
  body?: string;
  detail?: string;
  message: string;
  stack?: string;
} {
  if (!error) {
    return { message: 'Unknown error occurred' };
  }
  
  if (error && typeof error === 'object') {
    const apiError = error as any;
    
    // Extract detail information if available
    let detail = apiError.detail;
    if (!detail && apiError.body) {
      try {
        const parsed = typeof apiError.body === 'string' ? JSON.parse(apiError.body) : apiError.body;
        const nestedError = parsed?.error;
        const nestedMessage = typeof nestedError === "object" ? nestedError?.message : undefined;
        detail = nestedMessage || parsed.detail || parsed.message;
      } catch {
        // Ignore parse errors
      }
    }
    
    return {
      statusCode: apiError.status,
      body: apiError.body,
      detail,
      message: apiError.message || detail || String(error),
      stack: apiError.stack,
    };
  }
  return {
    message: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error ? error.stack : undefined,
  };
}

/**
 * Format an error for display based on environment
 * - Development: Show clear summary with expandable technical details
 * - Production: Show user-friendly messages only
 */
export function formatErrorForDisplay(error: unknown, endpoint?: string): ErrorDisplayInfo {
  const info = extractErrorInfo(error);
  
  if (isDevelopment) {
    // Development: Clear summary with expandable details
    let summary = '';
    
    if (info.statusCode) {
      summary = `HTTP ${info.statusCode} Error`;
      if (endpoint) {
        summary += ` on ${endpoint}`;
      }
    } else {
      summary = info.message || 'Request Failed';
    }
    
    return {
      summary,
      statusCode: info.statusCode,
      endpoint,
      errorMessage: info.detail || info.message,
      stackTrace: info.stack,
      responseBody: info.body,
      requestDetails: endpoint ? `GET ${endpoint}` : undefined,
    };
  } else {
    // Production: Polite messages
    const politeMessages: Record<number, string> = {
      404: 'The requested resource was not found.',
      401: 'You are not authorized to access this resource.',
      403: 'Access to this resource is forbidden.',
      500: 'An internal server error occurred.',
      503: 'The service is temporarily unavailable.',
    };
    
    // Use server-provided message if available, otherwise use polite fallback
    let summary: string;
    if (info.detail) {
      summary = info.detail;
    } else if (info.statusCode && politeMessages[info.statusCode]) {
      summary = politeMessages[info.statusCode];
    } else if (info.message && info.message !== 'Unknown error occurred') {
      summary = info.message;
    } else {
      summary = 'Something went wrong. Please try again later.';
    }
    
    return { summary };
  }
}

/**
 * Throw an error that will be verbose in dev and polite in prod
 */
export function throwError(message: string, technicalDetails?: unknown): never {
  if (isDevelopment) {
    // Verbose error in development
    const errorMessage = technicalDetails 
      ? `${message}\n\nTechnical Details:\n${JSON.stringify(technicalDetails, null, 2)}`
      : message;
    throw new Error(errorMessage);
  } else {
    // Polite error in production
    throw new Error(message);
  }
}

/**
 * Assert a condition, throwing verbose errors in dev
 */
export function assertDefined<T>(
  value: T | null | undefined,
  message: string
): asserts value is T {
  if (value === null || value === undefined) {
    throwError(message, { value, type: typeof value });
  }
}
