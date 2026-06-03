import { useEffect, useRef, useState } from 'react'
import { RoomHeader } from '@/components/RoomHeader'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { QrModal } from '@/components/QrModal'
import { SettingsModal } from '@/components/SettingsModal'
import { Button } from '@/components/ui/Button'
import { Card, StatRow } from '@/components/ui/Card'
import { apiFetch, getAccessToken, ensureToken } from '@/lib/auth'
import { useTimer, fmtTime, fmtDuration } from '@/hooks/useTimer'
import { useConfirm } from '@/hooks/useConfirm'
import { QueueState, WsMessageType, TicketStatus } from '@/constants'
import type {
  RoomStateResponse,
  QueueInfo,
  RoomStatsResponse,
  WsMessage,
  AdminRole,
  CoAdminItem,
  CoAdminsResponse,
} from '@/types/api'

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
  const [isOpen, setIsOpen] = useState(true)
  const [balancerEnabled, setBalancerEnabled] = useState(true)
  const [isOwner, setIsOwner] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [coAdmins, setCoAdmins] = useState<CoAdminItem[]>([])
  const { confirm, dialogProps } = useConfirm()

  const closedRef = useRef(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const onRoomClosedRef = useRef(onRoomClosed)
  const onToastRef = useRef(onToast)
  const onCloseRef = useRef(onClose)
  onRoomClosedRef.current = onRoomClosed
  onToastRef.current = onToast
  onCloseRef.current = onClose

  const roomIdRef = useRef(roomId)
  roomIdRef.current = roomId

  const verifyAccessRef = useRef<() => void>(() => {})
  verifyAccessRef.current = async () => {
    try {
      const res = await apiFetch('/api/v1/admin/resume', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomIdRef.current }),
      })
      if (res.status === 403) {
        closedRef.current = true
        onToastRef.current('Ваши права администратора отозваны', 'info')
        onCloseRef.current()
      }
    } catch { /* сеть — игнор, не выкидываем */ }
  }

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
    setIsOpen(data.is_open)
    setBalancerEnabled(data.balancer_enabled)
    setIsOwner(data.is_owner)
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
        if (msg.type === WsMessageType.WELCOME && msg.data) { handleState(msg.data); return }
        if (msg.type === WsMessageType.UPDATE) {
          if (msg.data?.room_closed) {
            if (!closedRef.current) { closedRef.current = true; onRoomClosedRef.current() }
            return
          }
          if (msg.data?.admin_revoked) {
            verifyAccessRef.current()
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
    if (!await confirm({
      message: 'Закрыть комнату и завершить приём? Все ожидающие будут отключены.',
      confirmLabel: 'Закрыть',
      danger: true,
    })) return
    closedRef.current = true
    try { await apiFetch(`/api/v1/rooms/${roomId}`, { method: 'DELETE' }) } catch (_) {}
    onClose()
  }

  async function handleLeaveRoom() {
    if (!await confirm({
      message: 'Выйти из комнаты? Вы потеряете права администратора. Комната продолжит работать.',
      confirmLabel: 'Выйти',
      danger: true,
    })) return
    closedRef.current = true
    try { await apiFetch('/api/v1/admin/leave', { method: 'POST', body: JSON.stringify({ room_id: roomId }) }) } catch (_) {}
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

  async function handleSkip(queueLabel: string) {
    try {
      const res = await apiFetch('/api/v1/admin/skip', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomId, queue_label: queueLabel }),
      })
      if (!res.ok) onToast(((await res.json()) as { detail?: string }).detail || 'Ошибка', 'error')
    } catch (e) { onToast((e as Error).message, 'error') }
  }

  async function handleToggleEntry(next: boolean) {
    setIsOpen(next)
    try {
      const res = await apiFetch('/api/v1/admin/entry', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomId, is_open: next }),
      })
      if (!res.ok) { setIsOpen(!next); onToast('Не удалось изменить приём', 'error'); return }
      onToast(next ? 'Приём открыт' : 'Приём закрыт', 'success')
    } catch (e) { setIsOpen(!next); onToast((e as Error).message, 'error') }
  }

  async function handleToggleBalancer(next: boolean) {
    setBalancerEnabled(next)
    try {
      const res = await apiFetch('/api/v1/admin/balancer', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomId, enabled: next }),
      })
      if (!res.ok) { setBalancerEnabled(!next); onToast('Не удалось изменить балансировщик', 'error') }
    } catch (e) { setBalancerEnabled(!next); onToast((e as Error).message, 'error') }
  }

  async function handleMoveTicket(ticket: string, toQueue: string, toIndex: number) {
    try {
      const res = await apiFetch('/api/v1/admin/move', {
        method: 'POST',
        body: JSON.stringify({
          room_id: roomId, ticket, to_queue: toQueue, to_index: toIndex,
        }),
      })
      if (!res.ok) onToast(((await res.json()) as { detail?: string }).detail || 'Ошибка', 'error')
    } catch (e) { onToast((e as Error).message, 'error') }
  }

  function copyQueueLink(code: string) {
    const link = `${location.origin}/?room=${roomId}&code=${code}`
    navigator.clipboard.writeText(link).then(
      () => onToast('Ссылка на очередь скопирована', 'success'),
      () => onToast('Не удалось скопировать', 'error'),
    )
  }

  async function handleInviteAdmin(role: AdminRole) {
    try {
      const res = await apiFetch('/api/v1/admin/invite', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomId, role }),
      })
      const d = await res.json() as { detail?: string; token?: string }
      if (!res.ok || !d.token) { onToast(d.detail || 'Не удалось создать приглашение', 'error'); return }
      const link = `${location.origin}/?room=${roomId}&invite=${encodeURIComponent(d.token)}`
      await navigator.clipboard.writeText(link)
      onToast('Ссылка скопирована', 'success')
    } catch (e) { onToast((e as Error).message, 'error') }
  }

  async function fetchCoAdmins() {
    try {
      const res = await apiFetch(`/api/v1/admin/admins/${roomId}`)
      if (!res.ok) return
      const d = await res.json() as CoAdminsResponse
      setCoAdmins(d.admins)
    } catch {  }
  }

  async function handleRevokeAdmin(targetUser: string) {
    try {
      const res = await apiFetch('/api/v1/admin/revoke-admin', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomId, user_id: targetUser }),
      })
      if (!res.ok) { onToast('Не удалось отозвать права', 'error'); return }
      onToast('Права отозваны', 'success')
      fetchCoAdmins()
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
    if (!await confirm({
      message: `Удалить очередь ${queueLabel}? Ожидающие перейдут в другие очереди.`,
      confirmLabel: 'Удалить',
      danger: true,
    })) return
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

  const qrUrl = `${location.origin}/?room=${roomId}`

  function handleCopy() {
    navigator.clipboard.writeText(qrUrl).then(
      () => onToast('Ссылка на комнату скопирована', 'success'),
      () => onToast('Не удалось скопировать', 'error'),
    )
  }

  return (
    <div className="page-wrap">
      {dialogProps && <ConfirmDialog {...dialogProps} />}
      {showQr && <QrModal url={qrUrl} roomId={roomId} onClose={() => setShowQr(false)} />}
      {showSettings && (
        <SettingsModal
          isOpen={isOpen}
          balancerEnabled={balancerEnabled}
          isOwner={isOwner}
          coAdmins={coAdmins}
          onToggleEntry={handleToggleEntry}
          onToggleBalancer={handleToggleBalancer}
          onInvite={handleInviteAdmin}
          onRevoke={handleRevokeAdmin}
          onRefreshAdmins={fetchCoAdmins}
          onClose={() => setShowSettings(false)}
        />
      )}
      <RoomHeader
        roomId={roomId}
        label="Комната"
        onCopy={handleCopy}
        onQr={() => setShowQr(true)}
        onSettings={() => setShowSettings(true)}
        action={
          isOwner ? (
            <Button variant="danger" size="sm" fullWidth={false} onClick={handleCloseRoom}>
              Закрыть
            </Button>
          ) : (
            <Button variant="danger" size="sm" fullWidth={false} onClick={handleLeaveRoom}>
              Выйти
            </Button>
          )
        }
      />

      <div className="page-content">
        {loading ? (
          <Card>
            <Button variant="secondary" loading disabled>Загрузка...</Button>
          </Card>
        ) : (
          queues.map(q => (
            <QueueCard
              key={q.label}
              queue={q}
              showCode={!balancerEnabled}
              onNext={handleNext}
              onComplete={handleComplete}
              onSkip={handleSkip}
              onRemove={handleRemoveQueue}
              onCopyCode={copyQueueLink}
              onMove={handleMoveTicket}
            />
          ))
        )}

        <div className="add-queue-row">
          <Button variant="secondary" onClick={handleAddQueue}>+ Добавить очередь</Button>
        </div>

        <Card title="Статистика сессии">
          <StatRow label="Всего обслужено">{stats?.completed ?? '—'}</StatRow>
          <StatRow label="Среднее время">{stats?.avg ? fmtDuration(stats.avg) : '—'}</StatRow>
        </Card>
      </div>
    </div>
  )
}

const STATUS_BADGE: Record<string, { text: string; cls: string }> = {
  on_way: { text: 'в пути', cls: 'on_way' },
  no_show: { text: 'не придёт', cls: 'no_show' },
}

interface QueueCardProps {
  queue: QueueInfo
  showCode: boolean
  onNext: (label: string) => Promise<void>
  onComplete: (label: string) => Promise<void>
  onSkip: (label: string) => Promise<void>
  onRemove: (label: string) => Promise<void>
  onCopyCode: (code: string) => void
  onMove: (ticket: string, toQueue: string, toIndex: number) => Promise<void>
}

function QueueCard({
  queue: q, showCode, onNext, onComplete, onSkip, onRemove, onCopyCode, onMove,
}: QueueCardProps) {
  const [actionLoading, setActionLoading] = useState(false)
  const [dragOver, setDragOver] = useState<number | 'end' | null>(null)
  const [expanded, setExpanded] = useState(false)
  const elapsed = useTimer(q.elapsed_time ?? 0, q.status === QueueState.SERVING)

  const COLLAPSE_AFTER = 5
  const collapsed = !expanded && q.waiting.length > COLLAPSE_AFTER
  const visibleWaiting = collapsed ? q.waiting.slice(0, COLLAPSE_AFTER) : q.waiting
  const hiddenCount = q.waiting.length - visibleWaiting.length

  async function handleAction(fn: () => Promise<void>) {
    setActionLoading(true)
    try { await fn() } finally { setActionLoading(false) }
  }

  function onDragStart(e: React.DragEvent, ticket: string) {
    e.dataTransfer.setData('text/plain', `${q.label}:${ticket}`)
    e.dataTransfer.effectAllowed = 'move'
  }

  function onDropAt(e: React.DragEvent, index: number) {
    e.preventDefault()
    setDragOver(null)
    const payload = e.dataTransfer.getData('text/plain')
    const [, ticket] = payload.split(':')
    if (ticket) onMove(ticket, q.label, index)
  }

  return (
    <Card className="queue-card">
      <div className="queue-card-head">
        <div className="queue-card-title">
          <span className="queue-card-name">Очередь {q.label}</span>
          <span className={`chip ${q.status}`}>
            {q.status === QueueState.SERVING ? 'Идёт приём' : 'Ожидание'}
          </span>
        </div>
        <Button
          variant="secondary"
          size="sm"
          fullWidth={false}
          className="queue-remove-btn"
          aria-label={`Удалить очередь ${q.label}`}
          onClick={() => handleAction(() => onRemove(q.label))}
        >
          ✕
        </Button>
      </div>

      {showCode && q.code && (
        <div className="queue-code-row" onClick={() => onCopyCode(q.code)} title="Скопировать ссылку на очередь">
          <span className="queue-code-label">Код входа</span>
          <span className="queue-code-val">{q.code}</span>
        </div>
      )}

      <div className="adm-ticket-big">{q.current_ticket}</div>

      {q.status === QueueState.SERVING && STATUS_BADGE[q.current_status] && (
        <div className="serving-status">
          <span className={`status-badge ${STATUS_BADGE[q.current_status].cls}`}>
            {q.current_status === TicketStatus.ON_WAY ? 'идёт' : STATUS_BADGE[q.current_status].text}
          </span>
        </div>
      )}

      {q.status === QueueState.SERVING && (
        <div className={`timer-display${elapsed > 0 ? ' active' : ''}`}>
          {fmtTime(elapsed)}
        </div>
      )}

      <div className="queue-card-action">
        {q.status === QueueState.SERVING ? (
          <div className="btn-row">
            <Button
              variant="secondary"
              fullWidth={false}
              className="skip-btn"
              disabled={actionLoading}
              title="Пропустить без учёта в статистике"
              onClick={() => handleAction(() => onSkip(q.label))}
            >
              Пропустить
            </Button>
            <Button
              variant="danger-solid"
              loading={actionLoading}
              onClick={() => handleAction(() => onComplete(q.label))}
            >
              {!actionLoading && `Завершить · ${q.label}`}
            </Button>
          </div>
        ) : (
          <Button
            variant="success-solid"
            loading={actionLoading}
            onClick={() => handleAction(() => onNext(q.label))}
          >
            {!actionLoading && `Вызвать следующего · ${q.label}`}
          </Button>
        )}
      </div>

      {}
      <ul
        className={`waiting-list${dragOver === 'end' ? ' drag-over-end' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragOver('end') }}
        onDragLeave={() => setDragOver(null)}
        onDrop={e => onDropAt(e, q.waiting.length)}
      >
        {q.waiting.length === 0 ? (
          <li className="waiting-empty">Очередь пуста</li>
        ) : (
          visibleWaiting.map((t, i) => {
            const badge = STATUS_BADGE[t.status]
            return (
              <li
                key={t.ticket}
                className={`waiting-item${dragOver === i ? ' drag-over' : ''}`}
                draggable
                onDragStart={e => onDragStart(e, t.ticket)}
                onDragOver={e => { e.preventDefault(); e.stopPropagation(); setDragOver(i) }}
                onDragLeave={e => e.stopPropagation()}
                onDrop={e => { e.stopPropagation(); onDropAt(e, i) }}
              >
                <span className="waiting-pos">{i + 1}</span>
                <span className="waiting-ticket">{t.ticket}</span>
                {badge && <span className={`status-badge ${badge.cls}`}>{badge.text}</span>}
                <span className="drag-handle" aria-hidden>⠿</span>
              </li>
            )
          })
        )}
      </ul>

      {(collapsed || expanded) && q.waiting.length > COLLAPSE_AFTER && (
        <button type="button" className="link-btn" onClick={() => setExpanded(v => !v)}>
          {collapsed ? `Показать ещё ${hiddenCount}` : 'Свернуть'}
        </button>
      )}
    </Card>
  )
}
