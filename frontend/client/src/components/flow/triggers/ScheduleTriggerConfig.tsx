import { useState, useMemo } from "react";
import { Calendar, Clock, Repeat, CalendarDays, ChevronDown, Check, Timer, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { ScheduleConfig } from "./types";
import { CRON_PRESETS, INTERVAL_PRESETS, TIMEZONE_OPTIONS } from "./types";

interface ScheduleTriggerConfigPanelProps {
  config: ScheduleConfig;
  onChange: (config: ScheduleConfig) => void;
}

function parseCronToHuman(cron: string | null): string {
  if (!cron) return "No schedule set";
  
  const parts = cron.split(" ");
  if (parts.length !== 5) return cron;
  
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  
  const preset = CRON_PRESETS.find((p) => p.cron === cron);
  if (preset) return preset.label;
  
  const formatHour = (h: string) => {
    const hourNum = parseInt(h, 10);
    if (isNaN(hourNum)) return h;
    const ampm = hourNum >= 12 ? "PM" : "AM";
    const hour12 = hourNum === 0 ? 12 : hourNum > 12 ? hourNum - 12 : hourNum;
    return `${hour12}:${minute.padStart(2, "0")} ${ampm}`;
  };
  
  const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  
  if (dayOfMonth === "*" && month === "*") {
    if (dayOfWeek === "*") {
      if (hour === "*") {
        return minute === "0" ? "Every hour" : `Every hour at :${minute.padStart(2, "0")}`;
      }
      return `Daily at ${formatHour(hour)}`;
    }
    
    if (dayOfWeek === "1-5") {
      return `Weekdays at ${formatHour(hour)}`;
    }
    
    if (dayOfWeek === "0,6") {
      return `Weekends at ${formatHour(hour)}`;
    }
    
    const dayNum = parseInt(dayOfWeek, 10);
    if (!isNaN(dayNum) && dayNum >= 0 && dayNum <= 6) {
      return `Every ${dayNames[dayNum]} at ${formatHour(hour)}`;
    }
  }
  
  if (dayOfMonth !== "*" && month === "*" && dayOfWeek === "*") {
    return `Monthly on day ${dayOfMonth} at ${formatHour(hour)}`;
  }
  
  return cron;
}

function formatInterval(seconds: number | null): string {
  if (!seconds) return "No interval set";
  
  const preset = INTERVAL_PRESETS.find((p) => p.seconds === seconds);
  if (preset) return preset.label;
  
  // Precise breakdown for custom intervals
  if (seconds < 60) {
    return `Every ${seconds} second${seconds !== 1 ? "s" : ""}`;
  }
  
  if (seconds < 3600) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (secs === 0) return `Every ${mins}m`;
    return `Every ${mins}m ${secs}s`;
  }
  
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (mins === 0) return `Every ${hours}h`;
    return `Every ${hours}h ${mins}m`;
  }
  
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (hours === 0) return `Every ${days}d`;
  return `Every ${days}d ${hours}h`;
}

function formatIntervalDetailed(seconds: number | null): string {
  if (!seconds) return "";
  
  const preset = INTERVAL_PRESETS.find((p) => p.seconds === seconds);
  if (preset) return `(${seconds.toLocaleString()} seconds)`;
  
  // Show breakdown and total seconds
  const parts: string[] = [];
  let remaining = seconds;
  
  const days = Math.floor(remaining / 86400);
  if (days > 0) {
    parts.push(`${days}d`);
    remaining %= 86400;
  }
  
  const hours = Math.floor(remaining / 3600);
  if (hours > 0) {
    parts.push(`${hours}h`);
    remaining %= 3600;
  }
  
  const mins = Math.floor(remaining / 60);
  if (mins > 0) {
    parts.push(`${mins}m`);
    remaining %= 60;
  }
  
  if (remaining > 0) {
    parts.push(`${remaining}s`);
  }
  
  return `(${parts.join(" ")} = ${seconds.toLocaleString()} seconds)`;
}

function formatOneOffDate(dateStr: string | null): string {
  if (!dateStr) return "No date selected";
  
  try {
    const date = new Date(dateStr);
    return date.toLocaleString(undefined, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

export function ScheduleTriggerConfigPanel({ config, onChange }: ScheduleTriggerConfigPanelProps) {
  const [customCron, setCustomCron] = useState(config.cron_expression || "");
  const [customIntervalValue, setCustomIntervalValue] = useState("");
  const [customIntervalUnit, setCustomIntervalUnit] = useState<"minutes" | "hours" | "days">("hours");

  // Auto-populate custom fields when interval is set and not a preset
  const isCustomInterval = useMemo(() => {
    if (!config.interval_seconds) return false;
    return !INTERVAL_PRESETS.some((p) => p.seconds === config.interval_seconds);
  }, [config.interval_seconds]);

  useMemo(() => {
    if (isCustomInterval && config.interval_seconds && customIntervalValue === "") {
      let value = config.interval_seconds;
      let unit: "minutes" | "hours" | "days" = "hours";
      
      if (config.interval_seconds % 86400 === 0) {
        value = config.interval_seconds / 86400;
        unit = "days";
      } else if (config.interval_seconds % 3600 === 0) {
        value = config.interval_seconds / 3600;
        unit = "hours";
      } else if (config.interval_seconds % 60 === 0) {
        value = config.interval_seconds / 60;
        unit = "minutes";
      }
      
      setCustomIntervalValue(String(value));
      setCustomIntervalUnit(unit);
    }
  }, [isCustomInterval, config.interval_seconds]);

  const handleScheduleTypeChange = (type: "cron" | "interval" | "one_off") => {
    onChange({
      ...config,
      schedule_type: type,
      cron_expression: type === "cron" ? (config.cron_expression || "0 9 * * *") : null,
      interval_seconds: type === "interval" ? (config.interval_seconds || 3600) : null,
      run_at: type === "one_off" ? (config.run_at || new Date().toISOString()) : null,
    });
  };

  const handlePresetSelect = (cron: string) => {
    onChange({ ...config, cron_expression: cron });
    setCustomCron(cron);
  };

  const handleCustomCronChange = (value: string) => {
    setCustomCron(value);
    if (value.split(" ").length === 5) {
      onChange({ ...config, cron_expression: value });
    }
  };

  const handleIntervalPresetSelect = (seconds: number) => {
    onChange({ ...config, interval_seconds: seconds });
    setCustomIntervalValue("");
  };

  const applyCustomInterval = () => {
    const value = parseInt(customIntervalValue, 10);
    if (isNaN(value) || value <= 0) return;
    
    let seconds = value;
    if (customIntervalUnit === "minutes") seconds *= 60;
    if (customIntervalUnit === "hours") seconds *= 3600;
    if (customIntervalUnit === "days") seconds *= 86400;
    
    onChange({ ...config, interval_seconds: seconds });
  };

  const handleCustomIntervalApply = applyCustomInterval;

  const handleCustomIntervalKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      applyCustomInterval();
    }
  };

  const handleCustomIntervalBlur = () => {
    if (customIntervalValue) {
      applyCustomInterval();
    }
  };

  const handleDateTimeChange = (value: string) => {
    try {
      const date = new Date(value);
      onChange({ ...config, run_at: date.toISOString() });
    } catch {
      // Invalid date, ignore
    }
  };

  const localDateTime = useMemo(() => {
    if (!config.run_at) return "";
    try {
      const date = new Date(config.run_at);
      return date.toISOString().slice(0, 16);
    } catch {
      return "";
    }
  }, [config.run_at]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 pb-2">
        <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center">
          <Clock className="h-4 w-4 text-white" />
        </div>
        <div>
          <h3 className="font-semibold text-sm">Scheduled Trigger</h3>
          <p className="text-xs text-muted-foreground">Run at specific times</p>
        </div>
      </div>

      <Separator />

      <Tabs
        value={config.schedule_type}
        onValueChange={(v) => handleScheduleTypeChange(v as "cron" | "interval" | "one_off")}
        className="space-y-4"
      >
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="cron" className="gap-1.5">
            <CalendarDays className="h-3.5 w-3.5" />
            <span className="text-xs">Schedule</span>
          </TabsTrigger>
          <TabsTrigger value="interval" className="gap-1.5">
            <Repeat className="h-3.5 w-3.5" />
            <span className="text-xs">Interval</span>
          </TabsTrigger>
          <TabsTrigger value="one_off" className="gap-1.5">
            <Calendar className="h-3.5 w-3.5" />
            <span className="text-xs">One-time</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="cron" className="space-y-4">
          <div className="p-4 rounded-xl bg-gradient-to-br from-blue-500/10 to-cyan-500/10 border border-blue-500/20">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="h-4 w-4 text-blue-500" />
              <span className="font-medium text-sm">
                {parseCronToHuman(config.cron_expression)}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {config.cron_expression || "Select a schedule below"}
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-medium">Quick Presets</Label>
            <div className="grid grid-cols-2 gap-2">
              {CRON_PRESETS.slice(0, 6).map((preset) => {
                const isSelected = config.cron_expression === preset.cron;
                return (
                  <Button
                    key={preset.cron}
                    type="button"
                    variant={isSelected ? "default" : "outline"}
                    size="sm"
                    className={cn(
                      "justify-start h-auto py-2 px-3",
                      isSelected && "bg-gradient-to-r from-blue-500/90 to-cyan-600/90"
                    )}
                    onClick={() => handlePresetSelect(preset.cron)}
                    data-testid={`preset-${preset.cron.replace(/\s/g, "-")}`}
                  >
                    <div className="text-left">
                      <div className="text-xs font-medium">{preset.label}</div>
                      <div className="text-[10px] opacity-70">{preset.description}</div>
                    </div>
                  </Button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-medium">Custom Cron Expression</Label>
            <div className="flex gap-2">
              <Input
                placeholder="0 9 * * *"
                value={customCron}
                onChange={(e) => handleCustomCronChange(e.target.value)}
                className="font-mono text-sm"
                data-testid="input-custom-cron"
              />
            </div>
            <p className="text-[10px] text-muted-foreground">
              Format: minute hour day-of-month month day-of-week
            </p>
          </div>
        </TabsContent>

        <TabsContent value="interval" className="space-y-4">
          <div className="p-4 rounded-xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 border border-emerald-500/20">
            <div className="flex items-center gap-2 mb-1">
              <Timer className="h-4 w-4 text-emerald-500" />
              <span className="font-medium text-sm">
                {formatInterval(config.interval_seconds)}
              </span>
              {isCustomInterval && (
                <Badge variant="secondary" className="text-[10px] ml-auto">
                  Custom
                </Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Runs repeatedly at this interval {formatIntervalDetailed(config.interval_seconds)}
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-medium">Quick Presets</Label>
            <div className="grid grid-cols-2 gap-2">
              {INTERVAL_PRESETS.map((preset) => {
                const isSelected = config.interval_seconds === preset.seconds;
                return (
                  <Button
                    key={preset.seconds}
                    type="button"
                    variant={isSelected ? "default" : "outline"}
                    size="sm"
                    className={cn(
                      "justify-start",
                      isSelected && "bg-gradient-to-r from-emerald-500/90 to-teal-600/90"
                    )}
                    onClick={() => handleIntervalPresetSelect(preset.seconds)}
                    data-testid={`interval-${preset.seconds}`}
                  >
                    {preset.label}
                  </Button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-medium">Custom Interval</Label>
            <div className="flex gap-2">
              <Input
                type="number"
                placeholder="1"
                value={customIntervalValue}
                onChange={(e) => setCustomIntervalValue(e.target.value)}
                onKeyDown={handleCustomIntervalKeyDown}
                onBlur={handleCustomIntervalBlur}
                className="flex-1"
                min="1"
                data-testid="input-custom-interval"
              />
              <Select value={customIntervalUnit} onValueChange={(v) => setCustomIntervalUnit(v as any)}>
                <SelectTrigger className="w-[120px]" data-testid="select-interval-unit">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="minutes">Minutes</SelectItem>
                  <SelectItem value="hours">Hours</SelectItem>
                  <SelectItem value="days">Days</SelectItem>
                </SelectContent>
              </Select>
              <Button 
                type="button" 
                variant="outline" 
                onClick={handleCustomIntervalApply}
                data-testid="button-apply-interval"
              >
                Apply
              </Button>
            </div>
            <p className="text-[10px] text-muted-foreground">
              Press Enter or click Apply to save • Blur auto-applies when valid
            </p>
          </div>
        </TabsContent>

        <TabsContent value="one_off" className="space-y-4">
          <div className="p-4 rounded-xl bg-gradient-to-br from-amber-500/10 to-orange-500/10 border border-amber-500/20">
            <div className="flex items-center gap-2 mb-1">
              <Calendar className="h-4 w-4 text-amber-500" />
              <span className="font-medium text-sm">
                {formatOneOffDate(config.run_at)}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              Runs once at this specific time
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-medium">Date & Time</Label>
            <Input
              type="datetime-local"
              value={localDateTime}
              onChange={(e) => handleDateTimeChange(e.target.value)}
              className="w-full"
              data-testid="input-one-off-datetime"
            />
          </div>
        </TabsContent>
      </Tabs>

      <Separator />

      <div className="space-y-2">
        <Label className="text-xs font-medium flex items-center gap-1.5">
          <Globe className="h-3 w-3 text-indigo-500" />
          Timezone
        </Label>
        <Select
          value={config.timezone}
          onValueChange={(tz) => onChange({ ...config, timezone: tz })}
        >
          <SelectTrigger data-testid="select-timezone">
            <SelectValue placeholder="Select timezone" />
          </SelectTrigger>
          <SelectContent>
            {TIMEZONE_OPTIONS.map((tz) => (
              <SelectItem key={tz} value={tz}>
                {tz.replace(/_/g, " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

export function getScheduleSummary(config: ScheduleConfig): string {
  if (config.schedule_type === "cron") {
    return parseCronToHuman(config.cron_expression);
  }
  if (config.schedule_type === "interval") {
    return formatInterval(config.interval_seconds);
  }
  if (config.schedule_type === "one_off") {
    return formatOneOffDate(config.run_at);
  }
  return "No schedule configured";
}
