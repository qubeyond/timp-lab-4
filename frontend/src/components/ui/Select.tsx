import { useEffect, useRef, useState } from 'react'

export interface SelectOption<T extends string> {
  value: T
  label: string
  hint?: string
}

interface Props<T extends string> {
  value: T
  options: SelectOption<T>[]
  onChange: (value: T) => void
  ariaLabel?: string
}

export function Select<T extends string>({ value, options, onChange, ariaLabel }: Props<T>) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const current = options.find(o => o.value === value) ?? options[0]

  return (
    <div className={`select${open ? ' open' : ''}`} ref={ref}>
      <button
        type="button"
        className="select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen(v => !v)}
      >
        <span className="select-value">{current?.label}</span>
        <span className="select-arrow" aria-hidden>▾</span>
      </button>

      {open && (
        <ul className="select-menu" role="listbox">
          {options.map(o => (
            <li
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              className={`select-option${o.value === value ? ' selected' : ''}`}
              onClick={() => {
                onChange(o.value)
                setOpen(false)
              }}
            >
              <span className="select-option-label">{o.label}</span>
              {o.hint && <span className="select-option-hint">{o.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
