interface Props {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  hint?: string
  disabled?: boolean
}

export function Toggle({ checked, onChange, label, hint, disabled }: Props) {
  return (
    <label className={`toggle-row${disabled ? ' disabled' : ''}`}>
      <span className="toggle-text">
        <span className="toggle-label">{label}</span>
        {hint && <span className="toggle-hint">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        className={`toggle-switch${checked ? ' on' : ''}`}
        onClick={() => !disabled && onChange(!checked)}
      >
        <span className="toggle-knob" />
      </button>
    </label>
  )
}
