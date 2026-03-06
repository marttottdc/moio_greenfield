import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send, Loader2, Sparkles } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
};

type ChatPayload = {
  message: string;
  history: Array<Omit<Message, "timestamp"> & { timestamp: string }>;
};

export function CommandCenter() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const chatMutation = useMutation({
    mutationFn: async (payload: ChatPayload) => {
      const response = await apiRequest("POST", "/agent/chat", {
        data: payload,
      });

      return response.json() as Promise<{ message: string }>;
    },
    onSuccess: (data) => {
      const assistantMessage: Message = {
        id: `${Date.now()}-assistant`,
        role: "assistant",
        content: data.message,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    },
    onError: () => {
      const errorMessage: Message = {
        id: `${Date.now()}-error`,
        role: "assistant",
        content: "We couldn't reach the assistant. Please connect the backend service and try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || chatMutation.isPending) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);

    chatMutation.mutate({
      message: input,
      history: [...messages, userMessage]
        .slice(-10)
        .map(({ timestamp, ...rest }) => ({ ...rest, timestamp: timestamp.toISOString() })),
    });

    setInput("");
  };

  return (
    <div className="flex flex-col h-[400px] max-w-4xl mx-auto bg-white/70 backdrop-blur-md border border-white/60 rounded-lg shadow-sm" data-testid="command-center-panel">

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3" data-testid="messages-container">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-center" data-testid="empty-state">
            <div className="flex items-center gap-3 text-muted-foreground">
              <Sparkles className="h-5 w-5" style={{ color: '#ffba08' }} />
              <p className="text-sm" data-testid="text-welcome-message">
                Ask about contacts, deals, campaigns, or get insights...
              </p>
            </div>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                data-testid={`message-${message.role}-${message.id}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-4 py-3 ${
                    message.role === "user"
                      ? "bg-[#58a6ff] text-white"
                      : "bg-white/80 border border-white/60"
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                  <span className="text-xs opacity-70 mt-1 block">
                    {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </div>
            ))}
            {chatMutation.isPending && (
              <div className="flex justify-start">
                <div className="bg-white/80 border border-white/60 rounded-lg px-4 py-3">
                  <Loader2 className="h-4 w-4 animate-spin" style={{ color: '#58a6ff' }} />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-white/40">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about your CRM..."
            className="bg-white/80 flex-1"
            disabled={chatMutation.isPending}
            data-testid="input-command"
          />
          <Button
            type="submit"
            size="icon"
            disabled={!input.trim() || chatMutation.isPending}
            style={{ backgroundColor: '#ffba08' }}
            className="hover:opacity-90"
            data-testid="button-send-command"
          >
            {chatMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}
