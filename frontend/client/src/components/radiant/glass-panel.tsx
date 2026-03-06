import { clsx } from 'clsx'

export function GlassPanel({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<'div'>) {
  return (
    <div
      className={clsx(
        'bg-card/70 backdrop-blur-md',
        'border border-border/60 rounded-lg shadow-sm',
        'transition-all duration-200 hover:shadow-md',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
