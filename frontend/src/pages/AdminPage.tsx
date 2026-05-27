import { useEffect, useRef, useState } from 'react'
import { RoomHeader } from '@/components/RoomHeader'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { QrModal } from '@/components/QrModal'
import { apiFetch, getAccessToken, ensureToken } from '@/lib/auth'
import { useTimer, fmtTime, fmtDuration } from '@/hooks/useTimer'
import { useConfirm } from '@/hooks/useConfirm'
import type { RoomStateResponse, QueueInfo, RoomStatsResponse, WsMessage } from '@/types/api'

interface Props {
  roomId: string
  onClose: () => void
  onRoomClosed: () => void
  onToast: (msg: string, type?: 'info' | 'success' | 'error') => void
}

export function AdminPage({ roomId, onClose, onRoomClosed, onToast }: Props) {
  const [queues, setQueues] = useState<QueueInfo[]>([])
  const [stats, setStats] = useState<{ completed: number; avg: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [showQr, setShowQr] = useState(false)
  const { confirm, dialogProps } = useConfirm()

  const closedRef = useRef(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const onRoomClosedRef = useRef(onRoomClosed)
  const onToastRef = useRef(onToast)
  onRoomClosedRef.current = onRoomClosed
  onToastRef.current = onToast

  const roomIdRef = useRef(roomId)
  roomIdRef.current = roomId

  function fetchStats() {
    apiFetch(`/api/v1/admin/stats/${roomIdRef.current}`)
      .then(r => r.ok ? r.json() : null)
      .then((d: RoomStatsResponse | null) => {
        if (d) setStats({ completed: d.completed, avg: d.avg_serve_seconds })
      })
      .catch(() => {})
  }

  function handleState(data: RoomStateResponse) {
    if (data.room_closed) {
      if (!closedRef.current) { closedRef.current = true; onRoomClosedRef.current() }
      return
    }
    setLoading(false)
    const ctx = data.admin_context
    if (ctx) setQueues(ctx.queues)
    fetchStats()
  }

  function fetchState() {
    apiFetch(`/api/v1/rooms/${roomIdRef.current}/state`)
      .then(r => r.ok ? r.json() : null)
      .then((d: RoomStateResponse | null) => { if (d) handleState(d) })
      .catch(() => {})
  }

  useEffect(() => {
    let destroyed = false

    function initWs() {
      if (destroyed) return
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null }

      const token = getAccessToken()
      if (!token) { ensureToken().then(() => { if (!destroyed) initWs() }); return }

      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${proto}//${location.host}/ws/room/${roomIdRef.current}?token=${encodeURIComponent(token)}`)
      wsRef.current = ws

      ws.onopen = () => {
        if (destroyed) { ws.close(); return }
        fetchState()
        pingTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
        }, 25000)
      }

      ws.onclose = () => {
        if (pingTimer.current) { clearInterval(pingTimer.current); pingTimer.current = null }
        if (destroyed || closedRef.current) return
        reconnectTimer.current = setTimeout(() => {
          if (!destroyed && document.visibilityState !== 'hidden') initWs()
        }, 3000)
      }

      ws.onmessage = (event: MessageEvent<string>) => {
        if (destroyed || event.data === 'pong') return
        let msg: WsMessage
        try { msg = JSON.parse(event.data) as WsMessage } catch { return }
        if (msg.type === 'welcome' && msg.data) { handleState(msg.data); return }
        if (msg.type === 'update') {
          if (msg.data?.room_closed) {
            if (!closedRef.current) { closedRef.current = true; onRoomClosedRef.current() }
            return
          }
          fetchState()
        }
      }
    }

    initWs()

    return () => {
      destroyed = true
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null }
      if (pingTimer.current) { clearInterval(pingTimer.current); pingTimer.current = null }
      if (reconnectTimer.current) { clearTimeout(reconnectTimer.current); reconnectTimer.current = null }
    }
  }, [])

  async function handleCloseRoom() {
    if (!await confirm('Закрыть комнату и завершить приём?')) return
    closedRef.current = true
    try { await apiFetch(`/api/v1/rooms/${roomId}`, { method: 'DELETE' }) } catch (_) {}
    onClose()
  }

  async function handleNext(queueLabel: string) {
    try {
      const res = await apiFetch('/api/v1/admin/next', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomId, queue_label: queueLabel }),
      })
      if (!res.ok) onToast(((await res.json()) as { detail?: string }).detail || 'Ошибка', 'error')
    } catch (e) { onToast((e as Error).message, 'error') }
  }

  async function handleComplete(queueLabel: string) {
    try {
      const res = await apiFetch('/api/v1/admin/complete', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomId, queue_label: queueLabel }),
      })
      if (!res.ok) onToast(((await res.json()) as { detail?: string }).detail || 'Ошибка', 'error')
    } catch (e) { onToast((e as Error).message, 'error') }
  }

  async function handleAddQueue() {
    try {
      const res = await apiFetch('/api/v1/admin/queue/add', { method: 'POST', body: JSON.stringify({ room_id: roomId }) })
      const d = await res.json() as { detail?: string; queue_label?: string }
      if (!res.ok) { onToast(d.detail || 'Ошибка', 'error'); return }
      onToast(`Очередь ${d.queue_label} добавлена`, 'success')
      fetchState()
    } catch (e) { onToast((e as Error).message, 'error') }
  }

  async function handleRemoveQueue(queueLabel: string) {
    if (!await confirm(`Удалить очередь ${queueLabel}?`)) return
    try {
      const res = await apiFetch('/api/v1/admin/queue/remove', {
        method: 'DELETE',
        body: JSON.stringify({ room_id: roomId, queue_label: queueLabel }),
      })
      const d = await res.json() as { detail?: string; queue_label?: string }
      if (!res.ok) { onToast(d.detail || 'Ошибка', 'error'); return }
      onToast(`Очередь ${d.queue_label} удалена`, 'success')
      fetchState()
    } catch (e) { onToast((e as Error).message, 'error') }
  }

  function handleCopy() {
    navigator.clipboard.writeText(roomId).then(() => onToast('ID скопирован', 'info'))
  }

  const qrUrl = `${location.origin}/?room=${roomId}`

  return (
    <div className="page-wrap">
      {dialogProps && <ConfirmDialog {...dialogProps} />}
      {showQr && <QrModal url={qrUrl} onClose={() => setShowQr(false)} />}
      <RoomHeader
        roomId={roomId}
        label="Комната"
        onCopy={handleCopy}
        onQr={() => setShowQr(true)}
        action={
          <button className="btn btn-danger btn-sm" onClick={handleCloseRoom}>Закрыть</button>
        }
      />

      <div style={{ width: '100%', maxWidth: 440 }}>
        {loading ? (
          <div className="card">
            <button className="btn btn-secondary" disabled>
              <span className="spinner" /> Загрузка...
            </button>
          </div>
        ) : (
          queues.map(q => (
            <QueueCard
              key={q.label}
              queue={q}
              onNext={handleNext}
              onComplete={handleComplete}
              onRemove={handleRemoveQueue}
            />
          ))
        )}

        <div style={{ marginBottom: 16 }}>
          <button className="btn btn-secondary" onClick={handleAddQueue}>
            + Добавить очередь
          </button>
        </div>

        <div className="card">
          <div className="card-title">Статистика сессии</div>
          <div className="stat-row">
            <span className="stat-label">Всего обслужено</span>
            <span className="stat-value">{stats?.completed ?? '—'}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Среднее время</span>
            <span className="stat-value">{stats?.avg ? fmtDuration(stats.avg) : '—'}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

interface QueueCardProps {
  queue: QueueInfo
  onNext: (label: string) => Promise<void>
  onComplete: (label: string) => Promise<void>
  onRemove: (label: string) => Promise<void>
}

function QueueCard({ queue: q, onNext, onComplete, onRemove }: QueueCardProps) {
  const [actionLoading, setActionLoading] = useState(false)
  const elapsed = useTimer(q.elapsed_time ?? 0, q.status === 'serving')

  async function handleAction(fn: () => Promise<void>) {
    setActionLoading(true)
    try { await fn() } finally { setActionLoading(false) }
  }

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '1rem', fontWeight: 700 }}>Очередь {q.label}</span>
          <span className={`chip ${q.status}`}>
            {q.status === 'serving' ? 'Идёт приём' : 'Ожидание'}
          </span>
        </div>
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => handleAction(() => onRemove(q.label))}
          style={{ opacity: 0.6 }}
        >
          ✕
        </button>
      </div>

      <div className="adm-ticket-big">{q.current_ticket}</div>

      {q.status === 'serving' && (
        <div className={`timer-display${elapsed > 0 ? ' active' : ''}`}>
          {fmtTime(elapsed)}
        </div>
      )}

      <div style={{ margin: '12px 0 8px' }}>
        {q.status === 'serving' ? (
          <button
            className="btn btn-danger-solid"
            disabled={actionLoading}
            onClick={() => handleAction(() => onComplete(q.label))}
          >
            {actionLoading ? <span className="spinner" /> : `Завершить · ${q.label}`}
          </button>
        ) : (
          <button
            className="btn btn-success-solid"
            disabled={actionLoading}
            onClick={() => handleAction(() => onNext(q.label))}
          >
            {actionLoading ? <span className="spinner" /> : `Вызвать следующего · ${q.label}`}
          </button>
        )}
      </div>

      <div className="queue-line">
        {q.length === 0 ? (
          <span className="queue-empty">Очередь пуста</span>
        ) : (
          <span className="q-chip">{q.length} чел. ожидают</span>
        )}
      </div>
    </div>
  )
}
