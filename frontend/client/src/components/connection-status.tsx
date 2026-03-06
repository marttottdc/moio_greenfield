import { useWhatsAppMessages, useTicketUpdates } from "@/hooks/useWebSocket";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface ConnectionStatusProps {
  service: "whatsapp" | "tickets";
}

export function ConnectionStatus({ service }: ConnectionStatusProps) {
  const whatsapp = useWhatsAppMessages({ enabled: service === "whatsapp" });
  const tickets = useTicketUpdates({ enabled: service === "tickets" });

  const connection = service === "whatsapp" ? whatsapp : tickets;
  const isConnected = connection.isConnected;
  const isConnecting = connection.status === "connecting" || connection.status === "reconnecting";

  const getStatusColor = () => {
    if (isConnected) return "bg-green-500";
    if (isConnecting) return "bg-amber-500 animate-pulse";
    return "bg-gray-400";
  };

  const getStatusText = () => {
    if (isConnected) return "Live monitoring active";
    if (isConnecting) return "Connecting...";
    if (connection.status === "error") return "Connection error";
    return "Disconnected";
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex items-center gap-2 px-3 py-2 rounded-md hover-elevate cursor-help">
          <div className={`w-2 h-2 rounded-full ${getStatusColor()}`} />
          <span className="text-xs font-medium text-muted-foreground">
            {isConnected ? "Live" : isConnecting ? "Connecting" : "Offline"}
          </span>
        </div>
      </TooltipTrigger>
      <TooltipContent className="text-xs">
        {getStatusText()} - {service === "whatsapp" ? "WhatsApp" : "Tickets"} monitoring
      </TooltipContent>
    </Tooltip>
  );
}
