import { useState, type ReactNode } from "react"
import { useToast } from "@/hooks/use-toast"
import {
  Toast,
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastTitle,
  ToastViewport,
} from "@/components/ui/toast"
import { Copy, Check } from "lucide-react"
import { Button } from "@/components/ui/button"

export function Toaster() {
  const { toasts } = useToast()
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const handleCopy = async (id: string, title: ReactNode, description: ReactNode) => {
    const textContent = [
      typeof title === 'string' ? title : '',
      typeof description === 'string' ? description : ''
    ].filter(Boolean).join(': ')
    
    const timestamp = new Date().toISOString()
    const url = typeof window !== 'undefined' ? window.location.href : ''
    
    const hiddenContext = `\n\n---\nContext:\nTimestamp: ${timestamp}\nURL: ${url}\nError ID: ${id}`
    
    const fullContent = textContent + hiddenContext
    
    try {
      await navigator.clipboard.writeText(fullContent)
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 2000)
    } catch (err) {
      console.error('Failed to copy to clipboard:', err)
    }
  }

  return (
    <ToastProvider>
      {toasts.map(function ({ id, title, description, action, ...props }) {
        const isDestructive = props.variant === "destructive"
        const isCopied = copiedId === id
        
        return (
          <Toast key={id} {...props}>
            <div className="grid gap-1">
              {title && <ToastTitle>{title}</ToastTitle>}
              {description && (
                <ToastDescription>{description}</ToastDescription>
              )}
            </div>
            {isDestructive && (
              <Button
                size="icon"
                variant="ghost"
                className="h-6 w-6 shrink-0 text-destructive-foreground/70 hover:text-destructive-foreground hover:bg-destructive-foreground/10"
                onClick={() => handleCopy(id, title, description)}
                data-testid={`button-copy-error-${id}`}
              >
                {isCopied ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </Button>
            )}
            {action}
            <ToastClose />
          </Toast>
        )
      })}
      <ToastViewport />
    </ToastProvider>
  )
}
