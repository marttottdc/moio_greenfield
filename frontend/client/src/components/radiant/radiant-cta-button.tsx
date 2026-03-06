import { clsx } from 'clsx'
import { LucideIcon } from 'lucide-react'

type RadiantCTAButtonProps = {
  children: React.ReactNode
  icon?: LucideIcon
  onClick?: () => void
  className?: string
  fullWidth?: boolean
  'data-testid'?: string
} & React.ComponentPropsWithoutRef<'button'>

export function RadiantCTAButton({
  children,
  icon: Icon,
  onClick,
  className,
  fullWidth = false,
  ...props
}: RadiantCTAButtonProps) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'px-4 py-2 bg-[#ffba08] hover:bg-[#e5a807] dark:bg-[#ffba08] dark:hover:bg-[#e5a807]',
        'text-gray-900 dark:text-gray-900 font-medium rounded-lg',
        'transition-colors shadow-sm active:shadow-inner',
        'flex items-center gap-2 justify-center',
        fullWidth && 'w-full',
        className
      )}
      {...props}
    >
      {Icon && <Icon className="h-4 w-4" />}
      {children}
    </button>
  )
}
