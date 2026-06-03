import { useEffect, useRef } from 'react'
import QRCode from 'qrcode'
import { Modal, ModalActions } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'

interface Props {
  url: string
  roomId?: string
  onClose: () => void
}

export function QrModal({ url, roomId, onClose }: Props) {
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

  const shortCode = roomId || url.split('/').pop() || 'room'

  async function handleDownload() {

    const { jsPDF } = await import('jspdf')

    if (document.fonts?.ready) await document.fonts.ready

    const scale = 3
    const W = 794
    const H = 1123
    const cv = document.createElement('canvas')
    cv.width = W * scale
    cv.height = H * scale
    const ctx = cv.getContext('2d')!
    ctx.scale(scale, scale)

    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, W, H)
    ctx.textAlign = 'center'
    ctx.fillStyle = '#1a1a18'

    const font = 'Inter, -apple-system, "Segoe UI", system-ui, sans-serif'
    ctx.font = `700 38px ${font}`
    ctx.fillText('Электронная очередь', W / 2, 130)
    ctx.font = `400 20px ${font}`
    ctx.fillStyle = '#6b6860'
    ctx.fillText('Отсканируйте QR-код, чтобы занять место', W / 2, 168)

    const qrPx = 420
    const qrX = (W - qrPx) / 2
    const qrY = 230
    const qrCanvas = document.createElement('canvas')
    await QRCode.toCanvas(qrCanvas, url, {
      width: qrPx * scale,
      margin: 1,
      color: { dark: '#000000', light: '#ffffff' },
    })
    ctx.drawImage(qrCanvas, qrX, qrY, qrPx, qrPx)

    ctx.fillStyle = '#1a1a18'
    ctx.font = `800 52px ${font}`
    ctx.fillText(shortCode, W / 2, qrY + qrPx + 80)
    ctx.fillStyle = '#9e9b95'
    ctx.font = `400 16px ${font}`
    ctx.fillText(url, W / 2, qrY + qrPx + 112)

    const pdf = new jsPDF({ unit: 'pt', format: 'a4' })
    const pw = pdf.internal.pageSize.getWidth()
    const ph = pdf.internal.pageSize.getHeight()
    pdf.addImage(cv.toDataURL('image/png'), 'PNG', 0, 0, pw, ph)
    pdf.save(`queue-${shortCode.toLowerCase()}-qr.pdf`)
  }

  return (
    <Modal onClose={onClose} size="qr" title="Отсканируйте для входа">
      <canvas ref={canvasRef} className="qr-canvas" />
      <div className="qr-code-chip">{shortCode}</div>
      <ModalActions>
        <Button variant="secondary" onClick={onClose}>Закрыть</Button>
        <Button variant="primary" onClick={handleDownload}>Скачать PDF</Button>
      </ModalActions>
    </Modal>
  )
}
