import { Link } from "wouter";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { EmptyState } from "@/components/empty-state";
import { Clock, LayoutDashboard, Users, Megaphone, MessageSquare, Settings } from "lucide-react";

const DEMO_FREQUENTLY_USED = [
  { id: "dashboard", name: "Dashboard", path: "/", icon: LayoutDashboard },
  { id: "contacts", name: "Contacts", path: "/crm?tab=contacts", icon: Users },
  { id: "campaigns", name: "Campaigns", path: "/campaigns", icon: Megaphone },
  { id: "communications", name: "Communications", path: "/communications", icon: MessageSquare },
  { id: "settings", name: "Settings", path: "/settings", icon: Settings },
];

export function FrequentlyUsedWidget() {
  return (
    <GlassPanel className="p-6 h-full" data-testid="widget-frequently-used">
      <div className="flex items-center justify-between mb-4">
        <Subheading className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-muted-foreground" />
          Frequently Used
        </Subheading>
      </div>

      <div className="space-y-2">
        {DEMO_FREQUENTLY_USED.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.id}
              href={item.path}
              className="flex items-center gap-3 p-2 rounded-lg hover-elevate"
              data-testid={`frequently-used-item-${item.id}`}
            >
              <div className="h-8 w-8 rounded-md bg-muted flex items-center justify-center">
                <Icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <span className="text-sm">{item.name}</span>
            </Link>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground text-center mt-4 border-t pt-4">
        <span className="opacity-60">[Demo Data]</span> Based on your usage patterns.
      </p>
    </GlassPanel>
  );
}
