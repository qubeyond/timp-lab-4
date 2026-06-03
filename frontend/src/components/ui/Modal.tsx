import { useEffect, type ReactNode } from 'react'

interface Props {
  onClose: () => void
  /** Ширина бокса. sm — диалоги, qr — компактный по центру с gap. */
  size?: 'sm' | 'md' | 'qr'
  /** Заголовок (uppercase card-title). */
  title?: string
  /** Показать крестик закрытия в правом верхнем углу. */
  showClose?: boolean
  /** Закрывать по клику на оверлей (по умолчанию да). */
  closeOnOverlay?: boolean
  children: ReactNode
}

export function Modal({
  onClose,
  size = 'sm',
  title,
  showClose = false,
  closeOnOverlay = true,
  children,
}: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="modal-overlay"
      onClick={closeOnOverlay ? onClose : undefined}
      role="dialog"
      aria-modal="true"
    >
      <div className={`modal-box modal-box-${size}`} onClick={e => e.stopPropagation()}>
        {(title || showClose) && (
          <div className="modal-header">
            {title && <div className="card-title modal-title">{title}</div>}
            {showClose && (
              <button type="button" className="modal-close" aria-label="Закрыть" onClick={onClose}>
                ✕
              </button>
            )}
          </div>
        )}
        {children}
      </div>
    </div>
  )
}

/** Ряд кнопок действия снизу модалки — равной ширины. */
export function ModalActions({ children }: { children: ReactNode }) {
  return <div className="modal-actions">{children}</div>
}
