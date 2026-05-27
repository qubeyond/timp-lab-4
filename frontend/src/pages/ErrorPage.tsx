interface Props {
  code?: number
  title: string
  message: string
  onRetry?: () => void
}

export function ErrorPage({ code, title, message, onRetry }: Props) {
  return (
    <div className="page-wrap centered">
      <div className="center-wrap">
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div className="logo-icon" style={{ width: 48, height: 48, borderRadius: 14, margin: '0 auto 20px' }}>
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 6h16M4 10h10M4 14h12M4 18h8" />
            </svg>
          </div>
          {code && (
            <div style={{
              fontSize: '4rem',
              fontWeight: 800,
              letterSpacing: '-3px',
              lineHeight: 1,
              color: 'var(--border2)',
              marginBottom: 12,
            }}>
              {code}
            </div>
          )}
          <div style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 8, color: 'var(--text)' }}>
            {title}
          </div>
          <div style={{ fontSize: '.9rem', color: 'var(--text-2)', lineHeight: 1.5 }}>
            {message}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {onRetry && (
            <button className="btn btn-primary" onClick={onRetry}>
              Попробовать снова
            </button>
          )}
          <a className="btn btn-secondary" href="/">
            На главную
          </a>
        </div>
      </div>
    </div>
  )
}
