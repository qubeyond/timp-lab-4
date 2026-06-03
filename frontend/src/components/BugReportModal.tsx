import { useState } from 'react'
import { Modal, ModalActions } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { apiFetch } from '@/lib/auth'

interface Props {
  roomId?: string
  onClose: () => void
  onToast: (msg: string, type?: 'info' | 'success' | 'error') => void
}

export function BugReportModal({ roomId, onClose, onToast }: Props) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)

  async function handleSend() {
    const message = text.trim()
    if (message.length < 3) {
      onToast('Опишите проблему чуть подробнее', 'error')
      return
    }
    setSending(true)
    try {
      const res = await apiFetch('/api/v1/feedback', {
        method: 'POST',
        body: JSON.stringify({ message, room_id: roomId }),
      })
      if (!res.ok) {
        onToast('Не удалось отправить. Попробуйте позже', 'error')
        return
      }
      onToast('Сообщение отправлено', 'success')
      onClose()
    } catch (e) {
      onToast((e as Error).message, 'error')
    } finally {
      setSending(false)
    }
  }

  return (
    <Modal onClose={onClose} size="md" title="Сообщить о проблеме" showClose>
      <p className="toggle-hint" style={{ marginBottom: 12 }}>
        Нашли ошибку или есть идея? Опишите — я прочитаю.
      </p>
      <textarea
        className="bug-textarea"
        placeholder="Что случилось или что хотелось бы улучшить…"
        maxLength={2000}
        rows={5}
        value={text}
        onChange={e => setText(e.target.value)}
        autoFocus
      />
      <ModalActions>
        <Button variant="secondary" onClick={onClose}>Отмена</Button>
        <Button variant="primary" loading={sending} onClick={handleSend}>Отправить</Button>
      </ModalActions>
    </Modal>
  )
}
