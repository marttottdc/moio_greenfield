import { clsx } from 'clsx'
import { GlassPanel } from './glass-panel'

export function RadiantToolbar({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<'div'>) {
  return (
    <GlassPanel
      className={clsx('p-4', className)}
      {...props}
    >
      {children}
    </GlassPanel>
  )
}
