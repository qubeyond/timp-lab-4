import type { ButtonHTMLAttributes, ReactNode } from 'react'

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'> {
  children: ReactNode
  className?: string
}

export function IconButton({ children, className = '', ...rest }: Props) {
  return (
    <button type="button" className={`icon-btn ${className}`.trim()} {...rest}>
      {children}
    </button>
  )
}
