import { Link, useLocation } from "wouter";
import { Home, Users, CheckSquare, Menu, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { useAppBarAction } from "@/contexts/AppBarActionContext";

export function MobileAppBar() {
  const [location] = useLocation();
  const { toggleSidebar, isMobile } = useSidebar();
  const { action } = useAppBarAction();

  if (!isMobile) return null;

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-border/60 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80"
      style={{ paddingBottom: "max(env(safe-area-inset-bottom, 0px), 8px)" }}
    >
      <div className="flex items-center justify-around h-14 relative">
        <Button
          variant="ghost"
          size="icon"
          className="flex flex-col items-center justify-center gap-0.5 flex-1 min-w-0 py-2 h-full rounded-none text-muted-foreground hover:text-foreground"
          onClick={toggleSidebar}
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
          <span className="text-xs font-medium">Menu</span>
        </Button>
        <Link
          href="/dashboard"
          className={cn(
            "flex flex-col items-center justify-center gap-0.5 flex-1 min-w-0 py-2 text-xs font-medium transition-colors",
            location === "/dashboard" || location === "/"
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Home className="h-5 w-5" strokeWidth={location === "/dashboard" || location === "/" ? 2.5 : 2} />
          <span>Dashboard</span>
        </Link>

        <div className="flex-1 min-w-0 flex justify-center items-center">
          {action ? (
            <Button
              variant="default"
              size="icon"
              className="h-12 w-12 rounded-full shadow-lg -translate-y-2 hover:scale-105 transition-transform"
              onClick={action.onClick}
              aria-label={action.label ?? "Add"}
            >
              <Plus className="h-6 w-6" />
            </Button>
          ) : (
            <div className="h-12 w-12" />
          )}
        </div>

        <Link
          href="/crm?tab=contacts"
          className={cn(
            "flex flex-col items-center justify-center gap-0.5 flex-1 min-w-0 py-2 text-xs font-medium transition-colors",
            location.startsWith("/crm")
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Users className="h-5 w-5" strokeWidth={location.startsWith("/crm") ? 2.5 : 2} />
          <span>Contacts</span>
        </Link>
        <Link
          href="/activities"
          className={cn(
            "flex flex-col items-center justify-center gap-0.5 flex-1 min-w-0 py-2 text-xs font-medium transition-colors",
            location.startsWith("/activities")
              ? "text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <CheckSquare className="h-5 w-5" strokeWidth={location.startsWith("/activities") ? 2.5 : 2} />
          <span>Activities</span>
        </Link>
      </div>
    </nav>
  );
}
