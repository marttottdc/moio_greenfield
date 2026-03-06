import { cn } from "@/lib/utils";
import { Inbox, Loader2, type LucideIcon } from "lucide-react";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  className?: string;
  isLoading?: boolean;
}

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  className,
  isLoading = false,
}: EmptyStateProps) {
  const DisplayIcon = isLoading ? Loader2 : Icon;

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center border border-dashed border-muted-foreground/40 rounded-lg p-8 bg-white/60 dark:bg-slate-900/60",
        className,
      )}
      data-testid="empty-state"
    >
      <DisplayIcon
        className={cn(
          "h-10 w-10 text-muted-foreground mb-4",
          isLoading && "animate-spin",
        )}
      />
      <h3 className="text-lg font-semibold text-foreground">{title}</h3>
      {description && (
        <p className="mt-2 text-sm text-muted-foreground max-w-sm">{description}</p>
      )}
    </div>
  );
}
