interface Props {
  roomId: string
  label: string
  onCopy: () => void
  action: React.ReactNode
  onQr?: () => void
}

function QrIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <rect x="1" y="1" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="3" y="3" width="4" height="4" rx=".5"/>
      <rect x="13" y="1" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="15" y="3" width="4" height="4" rx=".5"/>
      <rect x="1" y="13" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5"/>
      <rect x="3" y="15" width="4" height="4" rx=".5"/>
      <rect x="13" y="13" width="2" height="2" rx=".3"/>
      <rect x="16" y="13" width="2" height="2" rx=".3"/>
      <rect x="13" y="16" width="2" height="2" rx=".3"/>
      <rect x="16" y="16" width="2" height="2" rx=".3"/>
      <rect x="19" y="16" width="2" height="2" rx=".3"/>
      <rect x="19" y="13" width="2" height="2" rx=".3"/>
      <rect x="13" y="19" width="2" height="2" rx=".3"/>
      <rect x="16" y="19" width="2" height="2" rx=".3"/>
    </svg>
  )
}

export function RoomHeader({ roomId, label, onCopy, action, onQr }: Props) {
  const HEIGHT = 38

  return (
    <div className="page-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        {onQr && (
          <button
            onClick={onQr}
            title="Показать QR-код"
            style={{
              width: HEIGHT,
              height: HEIGHT,
              flexShrink: 0,
              background: 'var(--surface2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background .15s, border-color .15s',
              padding: 0,
              color: 'var(--text-2)',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--border)'
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border2)'
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLButtonElement).style.background = 'var(--surface2)'
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--border)'
            }}
          >
            <QrIcon />
          </button>
        )}
        <div
          style={{
            height: HEIGHT,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            gap: 2,
          }}
        >
          <div className="room-label">{label}</div>
          <div className="room-id" onClick={onCopy} title="Скопировать ID">
            {roomId}
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {action}
      </div>
    </div>
  )
}
