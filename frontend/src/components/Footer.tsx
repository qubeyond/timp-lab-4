import { useState } from 'react'
import { BugReportModal } from '@/components/BugReportModal'

const GITHUB_URL = 'https://github.com/qubeyond'

interface Props {
  roomId?: string
  version?: string
  onToast: (msg: string, type?: 'info' | 'success' | 'error') => void
}

export function Footer({ roomId, version, onToast }: Props) {
  const [showBug, setShowBug] = useState(false)

  return (
    <>
      {showBug && (
        <BugReportModal roomId={roomId} onClose={() => setShowBug(false)} onToast={onToast} />
      )}
      <footer className="app-footer">
        <a
          className="footer-nick"
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          by gbeyond
        </a>
        <button type="button" className="bug-trigger" onClick={() => setShowBug(true)}>
          <span className="bug-icon" aria-hidden>⚠</span>
          Сообщить о проблеме
        </button>
        <span className="footer-version">{version || 'v.test'}</span>
      </footer>
    </>
  )
}
