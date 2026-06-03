import { IconButton } from '@/components/ui/IconButton'

interface Props {
  roomId: string
  label: string
  onCopy: () => void
  action: React.ReactNode
  onQr?: () => void
  onSettings?: () => void
}

function GearIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
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

export function RoomHeader({ roomId, label, onCopy, action, onQr, onSettings }: Props) {
  return (
    <div className="page-header">
      <div className="page-header-left">
        {onQr && (
          <IconButton onClick={onQr} title="Показать QR-код" aria-label="Показать QR-код">
            <QrIcon />
          </IconButton>
        )}
        <div className="room-meta">
          <div className="room-label">{label}</div>
          <div className="room-id" onClick={onCopy} title="Скопировать ссылку на комнату">
            {roomId}
          </div>
        </div>
      </div>
      <div className="page-header-actions">
        {onSettings && (
          <IconButton onClick={onSettings} title="Настройки комнаты" aria-label="Настройки комнаты">
            <GearIcon />
          </IconButton>
        )}
        {action}
      </div>
    </div>
  )
}
