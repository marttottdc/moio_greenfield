import { clsx } from 'clsx'
import { Subheading } from './text'

export function BentoCard({
  dark = false,
  className = '',
  eyebrow,
  title,
  description,
  graphic,
  fade = [],
}: {
  dark?: boolean
  className?: string
  eyebrow: React.ReactNode
  title: React.ReactNode
  description: React.ReactNode
  graphic: React.ReactNode
  fade?: ('top' | 'bottom')[]
}) {
  return (
    <div
      data-dark={dark ? 'true' : undefined}
      className={clsx(
        className,
        'group relative flex flex-col overflow-hidden rounded-lg',
        'bg-white/60 backdrop-blur-md shadow-sm ring-1 ring-white/40',
        'hover:bg-white/70 transition-all duration-300',
        'data-dark:bg-gray-800/70 data-dark:ring-white/15 data-dark:hover:bg-gray-800/80',
      )}
    >
      <div className="relative h-80 shrink-0">
        {graphic}
        {fade.includes('top') && (
          <div className="absolute inset-0 bg-gradient-to-b from-white to-50% group-data-dark:from-gray-800 group-data-dark:from-[-25%]" />
        )}
        {fade.includes('bottom') && (
          <div className="absolute inset-0 bg-gradient-to-t from-white to-50% group-data-dark:from-gray-800 group-data-dark:from-[-25%]" />
        )}
      </div>
      <div className="relative p-10">
        <Subheading as="h3" dark={dark}>
          {eyebrow}
        </Subheading>
        <p className="mt-1 text-2xl/8 font-medium tracking-tight text-gray-950 group-data-dark:text-white">
          {title}
        </p>
        <p className="mt-2 max-w-[600px] text-sm/6 text-gray-600 group-data-dark:text-gray-400">
          {description}
        </p>
      </div>
    </div>
  )
}
