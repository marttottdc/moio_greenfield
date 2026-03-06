import { clsx } from 'clsx'

export function Gradient({
  className,
  ...props
}: React.ComponentPropsWithoutRef<'div'>) {
  return (
    <div
      {...props}
      className={clsx(
        className,
        'bg-gradient-to-br from-[#58a6ff]/10 via-[#74c365]/5 to-[#ffba08]/10',
      )}
    />
  )
}

export function GradientBackground() {
  return (
    <div className="relative mx-auto max-w-7xl">
      <div
        className={clsx(
          'absolute -top-44 -right-60 h-60 w-[500px] transform-gpu md:right-0',
          'bg-gradient-to-br from-[#58a6ff]/20 via-[#74c365]/10 to-[#ffba08]/20',
          'rotate-[-10deg] rounded-full blur-3xl',
        )}
      />
    </div>
  )
}
