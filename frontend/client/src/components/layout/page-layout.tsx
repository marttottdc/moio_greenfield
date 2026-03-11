import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/radiant/page-header";
import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface KPIStat {
  label: string;
  value: string;
  change?: string;
  trend?: "up" | "down";
}

interface PageLayoutProps {
  title: string;
  description?: string | React.ReactNode;
  metrics?: Array<{
    label: string;
    value: string;
    color?: string;
    testId?: string;
  }>;
  ctaLabel?: string;
  ctaIcon?: LucideIcon;
  onCtaClick?: () => void;
  ctaTestId?: string;
  kpiRibbon?: React.ReactNode;
  toolbar?: React.ReactNode;
  toolbarClassName?: string;
  headerAction?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  showSidebarTrigger?: boolean;
}

export function PageLayout({
  title,
  description,
  metrics,
  ctaLabel,
  ctaIcon,
  onCtaClick,
  ctaTestId,
  kpiRibbon,
  toolbar,
  toolbarClassName,
  headerAction,
  children,
  className,
  showSidebarTrigger = true,
}: PageLayoutProps) {
  const headerRef = useRef<HTMLDivElement>(null);
  const kpiRef = useRef<HTMLDivElement>(null);
  const [headerHeight, setHeaderHeight] = useState(89);
  const [kpiHeight, setKpiHeight] = useState(0);

  useEffect(() => {
    const updateHeights = () => {
      if (headerRef.current) {
        setHeaderHeight(headerRef.current.offsetHeight);
      }
      if (kpiRef.current) {
        setKpiHeight(kpiRef.current.offsetHeight);
      }
    };

    updateHeights();

    const resizeObserver = new ResizeObserver(updateHeights);
    if (headerRef.current) {
      resizeObserver.observe(headerRef.current);
    }
    if (kpiRef.current) {
      resizeObserver.observe(kpiRef.current);
    }

    return () => {
      resizeObserver.disconnect();
    };
  }, [kpiRibbon]);

  const toolbarTop = kpiRibbon ? headerHeight + kpiHeight : headerHeight;

  return (
    <div className="flex flex-col h-full">
      {/* Sticky Header */}
      <div
        ref={headerRef}
        className="sticky top-0 z-30 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75 border-b"
      >
        <div className="p-4 md:p-6">
          <PageHeader
            title={title}
            description={description}
            metrics={metrics}
            ctaLabel={ctaLabel}
            ctaIcon={ctaIcon}
            onCtaClick={onCtaClick}
            ctaTestId={ctaTestId}
            headerAction={headerAction}
            showSidebarTrigger={showSidebarTrigger}
          />
        </div>
      </div>

      {/* Sticky KPI Ribbon (if provided) */}
      {kpiRibbon && (
        <div
          ref={kpiRef}
          className="sticky z-20 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75 border-b"
          style={{ top: `${headerHeight}px` }}
        >
          <div className="p-4 md:p-6">{kpiRibbon}</div>
        </div>
      )}

      {/* Sticky Toolbar (if provided) */}
      {toolbar && (
        <div
          className="sticky z-10 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75 border-b"
          style={{ top: `${toolbarTop}px` }}
        >
          <div className={cn("px-4 py-4 md:px-6", toolbarClassName)}>{toolbar}</div>
        </div>
      )}

      {/* Scrollable Content - extra pb on mobile for app bar clearance */}
      <div className={cn("flex-1 overflow-y-auto p-4 md:p-6 pb-24 md:pb-6", className)}>
        {children}
      </div>
    </div>
  );
}

export function KPIRibbon({ stats }: { stats: KPIStat[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map((stat, index) => (
        <div
          key={index}
          className="bg-card border rounded-lg p-4"
          data-testid={`kpi-${stat.label.toLowerCase().replace(/\s+/g, "-")}`}
        >
          <div className="text-sm text-muted-foreground mb-1">
            {stat.label}
          </div>
          <div className="flex items-baseline justify-between">
            <div className="text-2xl font-semibold" data-testid={`kpi-value-${stat.label.toLowerCase().replace(/\s+/g, "-")}`}>
              {stat.value}
            </div>
            {stat.change && (
              <div
                className={cn(
                  "text-sm font-medium",
                  stat.trend === "up"
                    ? "text-green-600 dark:text-green-400"
                    : stat.trend === "down"
                    ? "text-red-600 dark:text-red-400"
                    : "text-muted-foreground"
                )}
              >
                {stat.change}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
