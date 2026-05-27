import { useEffect, useRef, useState } from 'react'
import { RoomHeader } from '@/components/RoomHeader'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { apiFetch, getAccessToken, ensureToken } from '@/lib/auth'
import { useTimer, fmtTime, fmtDuration } from '@/hooks/useTimer'
import { useConfirm } from '@/hooks/useConfirm'
import type { RoomStateResponse, WsMessage } from '@/types/api'

interface Props {
  roomId: string
  onLeave: () => void
  onServed: () => void
  onRoomClosed: () => void
  onToast: (msg: string, type?: 'info' | 'success' | 'error') => void
}

function formatPosition(posLabel: string, queueLabel: string): string {
  if (!posLabel || posLabel === '—') return '—'
  if (posLabel === 'На приеме') return 'Идёт приём'
  const pos = parseInt(posLabel, 10)
  if (!isNaN(pos)) {
    const suffix = queueLabel ? ` · очередь ${queueLabel}` : ''
    const ahead = pos - 1
    if (ahead === 0) return `Вы следующий${suffix}`
    if (ahead === 1) return `1 человек впереди${suffix}`
    if (ahead >= 2 && ahead <= 4) return `${ahead} человека впереди${suffix}`
    return `${ahead} человек впереди${suffix}`
  }
  return posLabel + (queueLabel ? ` · очередь ${queueLabel}` : '')
}

function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}

function notifyServing(ticket: string) {
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification(`Ваша очередь подошла · ${ticket}`)
  }
}

export function UserPage({ roomId, onLeave, onServed, onRoomClosed, onToast }: Props) {
  const [state, setState] = useState<RoomStateResponse | null>(null)
  const { confirm, dialogProps } = useConfirm()

  const hadTicket = useRef(false)
  const leftVoluntarily = useRef(false)
  const closedRef = useRef(false)
  const exitedRef = useRef(false)
  const prevStatusRef = useRef<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const onRoomClosedRef = useRef(onRoomClosed)
  const onServedRef = useRef(onServed)
  const onLeaveRef = useRef(onLeave)
  const onToastRef = useRef(onToast)
  onRoomClosedRef.current = onRoomClosed
  onServedRef.current = onServed
  onLeaveRef.current = onLeave
  onToastRef.current = onToast

  const roomIdRef = useRef(roomId)
  roomIdRef.current = roomId

  const isServing = state?.current_status === 'serving'
  const elapsed = useTimer(state?.elapsed_time ?? 0, isServing)

  function handleState(data: RoomStateResponse) {
    if (data.room_closed) {
      if (!closedRef.current) { closedRef.current = true; onRoomClosedRef.current() }
      return
    }
    setState(data)
    const ctx = data.client_context
    if (ctx?.ticket_label && ctx.ticket_label !== '--') hadTicket.current = true

    if (
      data.current_status === 'serving' &&
      prevStatusRef.current !== 'serving' &&
      ctx?.ticket_label &&
      ctx.ticket_label !== '--'
    ) {
      notifyServing(ctx.ticket_label)
    }
    prevStatusRef.current = data.current_status

    if (hadTicket.current && ctx?.should_redirect && !exitedRef.current) {
      exitedRef.current = true
      if (!leftVoluntarily.current) onServedRef.current()
      else onLeaveRef.current()
    }
  }

  function fetchState() {
    apiFetch(`/api/v1/rooms/${roomIdRef.current}/state`)
      .then(r => r.ok ? r.json() : null)
      .then((d: RoomStateResponse | null) => { if (d) handleState(d) })
      .catch(() => {})
  }

  useEffect(() => {
    requestNotificationPermission()
  }, [])

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
        if (destroyed || closedRef.current || exitedRef.current) return
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

  async function handleLeave() {
    if (!await confirm('Покинуть очередь?')) return
    leftVoluntarily.current = true
    try {
      await apiFetch('/api/v1/queue/leave', { method: 'POST', body: JSON.stringify({ room_id: roomId }) })
    } catch (_) {}
    onLeave()
  }

  function handleCopy() {
    navigator.clipboard.writeText(roomId).then(() => onToast('ID скопирован', 'info'))
  }

  const ctx = state?.client_context
  const isPositionServing = ctx?.position_label === 'На приеме'
  const positionText = ctx ? formatPosition(ctx.position_label, ctx.queue_label) : '—'

  return (
    <div className="page-wrap">
      {dialogProps && <ConfirmDialog {...dialogProps} />}
      <RoomHeader
        roomId={roomId}
        label="Комната"
        onCopy={handleCopy}
        action={
          <button className="btn btn-danger btn-sm" onClick={handleLeave}>Покинуть</button>
        }
      />

      <div style={{ width: '100%', maxWidth: 440 }}>
        <div className="card">
          <div className="ticket-hero">
            <div className="ticket-label">Ваш талон</div>
            <div className={`ticket-num${isPositionServing ? ' serving' : ''}`}>
              {ctx?.ticket_label || '—'}
            </div>
          </div>

          <div className="stat-row">
            <span className="stat-label">Позиция в очереди</span>
            <span className="stat-value blue">{positionText}</span>
          </div>

          <div className="stat-row">
            <span className="stat-label">Статус</span>
            <span className={`chip ${state?.current_status === 'serving' ? 'serving' : 'waiting'}`}>
              {state?.current_status === 'serving' ? 'Идёт приём' : 'Ожидание'}
            </span>
          </div>

          <div className="stat-row">
            <span className="stat-label">Время обслуживания</span>
            <span className="stat-value green">
              {isServing ? fmtTime(elapsed) : '—'}
            </span>
          </div>

          <div className="stat-row">
            <span className="stat-label">Среднее время</span>
            <span className="stat-value">
              {state?.avg_serve_seconds ? fmtDuration(state.avg_serve_seconds) : '—'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
