import { useEffect, useState } from "react";
import { getClientBuildInfo, loadBuildInfoFromMeta, getApiBaseUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/contexts/AuthContext";

interface GlobalFooterProps extends React.ComponentProps<"footer"> {}

function extractHostname(url: string): string {
  if (url.startsWith("/")) {
    return window.location.host;
  }
  try {
    const parsed = new URL(url);
    return parsed.host;
  } catch {
    return url;
  }
}

export function GlobalFooter({ className, ...props }: GlobalFooterProps) {
  const [buildInfo, setBuildInfo] = useState(getClientBuildInfo());
  const currentYear = new Date().getFullYear();
  const apiHost = extractHostname(getApiBaseUrl());
  const { user } = useAuth();
  const tenantName = user?.organization?.name?.toString().trim() || "";

  useEffect(() => {
    loadBuildInfoFromMeta().then(setBuildInfo);
  }, []);

  const { buildNumber: buildId, commit, fallbackVersion } = buildInfo;

  const buildLabel = (() => {
    if (buildId && commit) {
      return `Build ${buildId} • ${commit}`;
    }

    if (buildId) {
      return `Build ${buildId}`;
    }

    if (commit) {
      return `Commit ${commit}`;
    }

    return `v${fallbackVersion}`;
  })();

  return (
    <footer
      data-testid="global-footer"
      className={cn(
        "w-full border-t border-border/60 bg-background/80 text-[0.75rem] text-muted-foreground",
        "px-4 py-2 flex flex-wrap items-center justify-between gap-2 backdrop-blur-sm",
        className,
      )}
      {...props}
    >
      <span className="font-medium" data-testid="text-copyright">© {currentYear} Moio CRM</span>
      <div className="flex items-center gap-2">
        {tenantName && (
          <Badge variant="outline" className="text-[0.65rem]" data-testid="badge-tenant-name">
            {tenantName}
          </Badge>
        )}
        <Badge variant="outline" className="font-mono text-[0.65rem]" data-testid="badge-api-host">
          {apiHost}
        </Badge>
        <span className="font-mono text-xs uppercase tracking-wide" data-testid="text-build-version">{buildLabel}</span>
      </div>
    </footer>
  );
}
