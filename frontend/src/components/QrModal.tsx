import { useEffect, useRef } from 'react'
import QRCode from 'qrcode'

interface Props {
  url: string
  onClose: () => void
}

export function QrModal({ url, onClose }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (canvasRef.current) {
      QRCode.toCanvas(canvasRef.current, url, {
        width: 240,
        margin: 2,
        color: { dark: '#1a1a18', light: '#ffffff' },
      })
    }
  }, [url])

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,.35)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 10000,
        animation: 'fadeIn .15s ease-out',
        padding: '0 16px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '28px 24px 20px',
          width: '100%',
          maxWidth: 320,
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 16,
        }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ fontSize: '.68rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.09em', color: 'var(--text-3)' }}>
          Отсканируйте для входа
        </div>

        <canvas ref={canvasRef} style={{ borderRadius: 8, display: 'block' }} />

        <div style={{
          fontSize: '.8rem',
          fontFamily: 'monospace',
          color: 'var(--text-2)',
          background: 'var(--surface2)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          padding: '4px 10px',
          letterSpacing: '.05em',
          fontWeight: 600,
        }}>
          {url.split('/').pop()}
        </div>

        <button className="btn btn-secondary btn-sm" style={{ width: '100%' }} onClick={onClose}>
          Закрыть
        </button>
      </div>
    </div>
  )
}
