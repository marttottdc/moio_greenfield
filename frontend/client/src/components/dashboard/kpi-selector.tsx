import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type { KPIType } from "@shared/schema";
import { 
  Megaphone, 
  Users, 
  Send, 
  MailOpen, 
  MousePointerClick, 
  Contact, 
  Briefcase, 
  TrendingUp, 
  MessageCircle,
  Eye
} from "lucide-react";

interface KPISelectorProps {
  open: boolean;
  onClose: () => void;
  selectedKPIs: KPIType[];
  onSave: (kpis: KPIType[]) => Promise<void> | void;
}

const KPI_OPTIONS: { type: KPIType; label: string; icon: typeof Megaphone }[] = [
  { type: "total_campaigns", label: "Total Campaigns", icon: Megaphone },
  { type: "total_audiences", label: "Total Audiences", icon: Users },
  { type: "total_sent", label: "Messages Sent", icon: Send },
  { type: "total_opened", label: "Messages Opened", icon: MailOpen },
  { type: "open_rate", label: "Open Rate", icon: Eye },
  { type: "click_rate", label: "Click Rate", icon: MousePointerClick },
  { type: "total_contacts", label: "Total Contacts", icon: Contact },
  { type: "active_deals", label: "Active Deals", icon: Briefcase },
  { type: "conversion_rate", label: "Conversion Rate", icon: TrendingUp },
  { type: "response_rate", label: "Response Rate", icon: MessageCircle },
];

export function KPISelector({ open, onClose, selectedKPIs, onSave }: KPISelectorProps) {
  const [localSelected, setLocalSelected] = useState<KPIType[]>(selectedKPIs);

  useEffect(() => {
    setLocalSelected([...selectedKPIs]);
  }, [open, selectedKPIs]);

  const toggleKPI = (type: KPIType) => {
    setLocalSelected((prev) => {
      if (prev.includes(type)) {
        return prev.filter((k) => k !== type);
      }
      return [...prev, type];
    });
  };

  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave(localSelected);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Select KPIs</DialogTitle>
          <DialogDescription>
            Choose which metrics to display in the KPI ribbon.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3 py-4">
          {KPI_OPTIONS.map((kpi) => {
            const Icon = kpi.icon;
            const isSelected = localSelected.includes(kpi.type);
            return (
              <label
                key={kpi.type}
                className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  isSelected ? "bg-primary/5 border-primary/30" : "hover-elevate"
                }`}
                data-testid={`kpi-option-${kpi.type}`}
              >
                <Checkbox
                  checked={isSelected}
                  onCheckedChange={() => toggleKPI(kpi.type)}
                  data-testid={`checkbox-kpi-${kpi.type}`}
                />
                <Icon className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">{kpi.label}</span>
              </label>
            );
          })}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={isSaving} data-testid="button-save-kpis">
            {isSaving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
