import type { ReactNode, CSSProperties } from 'react'

interface Props {
  title?: string
  children: ReactNode

  className?: string
  style?: CSSProperties
}

export function Card({ title, children, className = '', style }: Props) {
  return (
    <div className={`card ${className}`.trim()} style={style}>
      {title && <div className="card-title">{title}</div>}
      {children}
    </div>
  )
}

export function StatRow({
  label,
  accent,
  children,
}: {
  label: string

  accent?: 'blue' | 'green' | 'accent'
  children: ReactNode
}) {
  return (
    <div className="stat-row">
      <span className="stat-label">{label}</span>
      <span className={`stat-value${accent ? ' ' + accent : ''}`}>{children}</span>
    </div>
  )
}
