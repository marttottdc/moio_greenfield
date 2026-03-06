import { SidebarTrigger } from '@/components/ui/sidebar'
import { Heading } from './text'
import { RadiantCTAButton } from './radiant-cta-button'
import { LucideIcon } from 'lucide-react'
import { clsx } from 'clsx'
import React from 'react'

type PageHeaderProps = {
  title: string
  description?: string | React.ReactNode
  metrics?: Array<{
    label: string
    value: string
    color?: string
    testId?: string
  }>
  ctaLabel?: string
  ctaIcon?: LucideIcon
  onCtaClick?: () => void
  ctaTestId?: string
  className?: string
  headerAction?: React.ReactNode
  showSidebarTrigger?: boolean
}

export function PageHeader({
  title,
  description,
  metrics = [],
  ctaLabel,
  ctaIcon,
  onCtaClick,
  ctaTestId,
  className,
  headerAction,
  showSidebarTrigger = true,
}: PageHeaderProps) {
  return (
    <div className={clsx('flex items-center justify-between gap-4 flex-wrap', className)}>
      {/* Left side - Title and description */}
      <div className="flex items-center gap-3">
        {showSidebarTrigger && <SidebarTrigger data-testid="button-sidebar-toggle" />}
        <div>
          <Heading as="h1" className="!text-3xl sm:!text-4xl" data-testid="text-page-title">
            {title}
          </Heading>
          {description && (
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          )}
        </div>
      </div>

      {/* Right side - Metrics and CTA */}
      <div className="flex items-center gap-4">
        {/* Metrics */}
        {metrics.map((metric, index) => (
          <div key={metric.testId || metric.label} className="flex items-center gap-4">
            {index > 0 && <div className="h-10 w-px bg-border" />}
            <div className="text-center">
              <div className="text-xs text-muted-foreground mb-0.5">{metric.label}</div>
              <div
                className="text-xl font-bold"
                style={metric.color ? { color: metric.color } : undefined}
                data-testid={metric.testId}
              >
                {metric.value}
              </div>
            </div>
          </div>
        ))}

        {/* CTA Button */}
        {ctaLabel && (
          <RadiantCTAButton
            icon={ctaIcon}
            onClick={onCtaClick}
            data-testid={ctaTestId}
          >
            {ctaLabel}
          </RadiantCTAButton>
        )}

        {/* Header Action */}
        {headerAction && (
          <div className="shrink-0">
            {headerAction}
          </div>
        )}
      </div>
    </div>
  )
}