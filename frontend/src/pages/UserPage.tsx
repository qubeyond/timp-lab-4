import { useEffect, useRef, useState } from 'react'
import { RoomHeader } from '@/components/RoomHeader'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/Button'
import { Card, StatRow } from '@/components/ui/Card'
import { apiFetch, getAccessToken, ensureToken } from '@/lib/auth'
import { useTimer, fmtTime, fmtDuration } from '@/hooks/useTimer'
import { useConfirm } from '@/hooks/useConfirm'
import {
  notificationsSupported,
  notificationPermission,
  requestNotificationPermission,
  showNotification,
  clearTicketNotification,
} from '@/lib/notifications'
import type { RoomStateResponse, WsMessage } from '@/types/api'
import { QueueState, WsMessageType } from '@/constants'

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

function notifyServing(ticket: string) {

  void showNotification({
    title: 'Ваша очередь подошла!',
    body: `Талон ${ticket} — подойдите к администратору`,
    sticky: true,
  })
}

export function UserPage({ roomId, onLeave, onServed, onRoomClosed, onToast }: Props) {
  const [state, setState] = useState<RoomStateResponse | null>(null)
  const [notifPerm, setNotifPerm] = useState<NotificationPermission>(notificationPermission())
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

  const isServing = state?.current_status === QueueState.SERVING
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
      data.current_status === QueueState.SERVING &&
      prevStatusRef.current !== QueueState.SERVING &&
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
    return () => { void clearTicketNotification() }
  }, [])

  async function handleEnableNotifications() {
    const perm = await requestNotificationPermission()
    setNotifPerm(perm)
    if (perm === 'granted') {
      onToast('Уведомления включены', 'success')
    } else if (perm === 'denied') {
      onToast('Уведомления заблокированы в браузере', 'error')
    }
  }

  async function handleTestNotification() {
    if (notificationPermission() !== 'granted') {
      await handleEnableNotifications()
      if (notificationPermission() !== 'granted') return
    }
    void showNotification({
      title: 'Проверка уведомлений',
      body: 'Так вы узнаете, когда подойдёт ваша очередь.',
      sticky: false,
    })
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
        if (destroyed || closedRef.current || exitedRef.current) return
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

  async function handleSetStatus(status: 'on_way' | 'no_show') {
    try {
      const res = await apiFetch('/api/v1/queue/status', {
        method: 'POST',
        body: JSON.stringify({ room_id: roomId, status }),
      })
      if (!res.ok) { onToast('Не удалось обновить статус', 'error'); return }
      onToast(status === 'on_way' ? 'Отметили: вы в пути' : 'Отметили: вы не придёте', 'success')
    } catch (e) { onToast((e as Error).message, 'error') }
  }

  async function handleLeave() {
    if (!await confirm({
      message: 'Покинуть очередь? Вернуться можно будет только заняв новое место.',
      confirmLabel: 'Покинуть',
      danger: true,
    })) return
    leftVoluntarily.current = true
    try {
      await apiFetch('/api/v1/queue/leave', { method: 'POST', body: JSON.stringify({ room_id: roomId }) })
    } catch (_) {}
    onLeave()
  }

  function handleCopy() {
    const link = `${location.origin}/?room=${roomId}`
    navigator.clipboard.writeText(link).then(
      () => onToast('Ссылка на комнату скопирована', 'success'),
      () => onToast('Не удалось скопировать', 'error'),
    )
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
          <Button variant="danger" size="sm" fullWidth={false} onClick={handleLeave}>
            Покинуть
          </Button>
        }
      />

      <div className="page-content">
        <Card>
          <div className="ticket-hero">
            <div className="ticket-label">Ваш талон</div>
            <div className={`ticket-num${isPositionServing ? ' serving' : ''}`}>
              {ctx?.ticket_label || '—'}
            </div>
          </div>

          <StatRow label="Позиция в очереди" accent="blue">{positionText}</StatRow>

          <div className="stat-row">
            <span className="stat-label">Статус</span>
            <span className={`chip ${state?.current_status === QueueState.SERVING ? QueueState.SERVING : QueueState.WAITING}`}>
              {state?.current_status === QueueState.SERVING ? 'Идёт приём' : 'Ожидание'}
            </span>
          </div>

          <StatRow label="Время обслуживания" accent="green">
            {isServing ? fmtTime(elapsed) : '—'}
          </StatRow>

          <StatRow label="Среднее время">
            {state?.avg_serve_seconds ? fmtDuration(state.avg_serve_seconds) : '—'}
          </StatRow>
        </Card>

        {ctx && isServing && (
          <Card title="Вас вызвали — сообщите администратору">
            <div className="btn-row">
              <Button
                variant={ctx.ticket_status === 'on_way' ? 'success-solid' : 'secondary'}
                onClick={() => handleSetStatus('on_way')}
              >
                Я иду
              </Button>
              <Button
                variant={ctx.ticket_status === 'no_show' ? 'danger-solid' : 'secondary'}
                onClick={() => handleSetStatus('no_show')}
              >
                Не приду
              </Button>
            </div>
          </Card>
        )}

        {notificationsSupported() && (
          <Card title="Уведомления">
            {notifPerm === 'granted' ? (
              <>
                <p className="toggle-hint" style={{ marginBottom: 10 }}>
                  Уведомления включены. Мы пришлём оповещение, когда подойдёт ваша очередь.
                </p>
                <Button variant="secondary" onClick={handleTestNotification}>
                  Проверить уведомление
                </Button>
              </>
            ) : notifPerm === 'denied' ? (
              <p className="toggle-hint">
                Уведомления заблокированы. Разрешите их в настройках браузера, чтобы не пропустить
                вызов.
              </p>
            ) : (
              <>
                <p className="toggle-hint" style={{ marginBottom: 10 }}>
                  Включите уведомления, чтобы получить оповещение, когда подойдёт ваша очередь —
                  даже если вкладка свёрнута.
                </p>
                <Button variant="primary" onClick={handleEnableNotifications}>
                  Включить уведомления
                </Button>
              </>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}
