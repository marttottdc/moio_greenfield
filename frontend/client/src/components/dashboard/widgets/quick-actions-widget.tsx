import { Link } from "wouter";
import { GlassPanel } from "@/components/radiant/glass-panel";
import { Subheading } from "@/components/radiant/text";
import { Button } from "@/components/ui/button";
import { Plus, Megaphone, Users, MessageSquare, Zap } from "lucide-react";

const QUICK_ACTIONS = [
  { id: "new-campaign", label: "New Campaign", icon: Megaphone, path: "/campaigns" },
  { id: "new-contact", label: "Add Contact", icon: Users, path: "/crm?tab=contacts" },
  { id: "send-message", label: "Send Message", icon: MessageSquare, path: "/communications" },
  { id: "new-workflow", label: "New Workflow", icon: Zap, path: "/workflows" },
];

export function QuickActionsWidget() {
  return (
    <GlassPanel className="p-6" data-testid="widget-quick-actions">
      <Subheading className="mb-4 flex items-center gap-2">
        <Plus className="h-4 w-4" />
        Quick Actions
      </Subheading>

      <div className="grid grid-cols-2 gap-2">
        {QUICK_ACTIONS.map((action) => {
          const Icon = action.icon;
          return (
            <Link key={action.id} href={action.path}>
              <Button
                variant="outline"
                className="w-full justify-start gap-2"
                data-testid={`quick-action-${action.id}`}
              >
                <Icon className="h-4 w-4" />
                <span className="text-xs">{action.label}</span>
              </Button>
            </Link>
          );
        })}
      </div>
    </GlassPanel>
  );
}
