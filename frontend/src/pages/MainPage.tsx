import { useState, useEffect, useRef, KeyboardEvent } from 'react'
import { Logo } from '@/components/Logo'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { apiFetch, ensureToken, setAccessToken } from '@/lib/auth'
import type { TakeTicketResponse, RoomCreateResponse } from '@/types/api'

interface Props {
  onJoinAsUser: (roomId: string) => void
  onJoinAsAdmin: (roomId: string) => void
}

export function MainPage({ onJoinAsUser, onJoinAsAdmin }: Props) {
  const [roomInput, setRoomInput] = useState('')
  const [joinLoading, setJoinLoading] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [inlineError, setInlineError] = useState('')

  const [closedRoom, setClosedRoom] = useState<{ room: string; code?: string } | null>(null)

  const autoJoinDone = useRef(false)

  useEffect(() => {
    if (autoJoinDone.current) return
    const params = new URLSearchParams(window.location.search)
    const roomFromQr = params.get('room')
    const codeFromQr = params.get('code')
    const inviteFromQr = params.get('invite')
    if (!roomFromQr) return
    autoJoinDone.current = true
    window.history.replaceState({}, '', '/')
    if (inviteFromQr) {
      acceptInvite(roomFromQr.trim().toUpperCase(), inviteFromQr.trim())
    } else {
      joinRoom(roomFromQr.trim().toUpperCase(), codeFromQr?.trim().toUpperCase() || undefined)
    }
  }, [])

  async function acceptInvite(rId: string, token: string) {
    setJoinLoading(true)
    setInlineError('')
    try {
      await ensureToken()
      const res = await apiFetch('/api/v1/admin/accept-invite', {
        method: 'POST',
        body: JSON.stringify({ room_id: rId, token }),
      })
      const data = await res.json() as { detail?: string; access_token?: string; room_id?: string }
      if (!res.ok || !data.access_token) {
        setInlineError(data.detail || 'Приглашение недействительно')
        return
      }
      setAccessToken(data.access_token)
      onJoinAsAdmin(data.room_id || rId)
    } catch (e) {
      setInlineError((e as Error).message)
    } finally {
      setJoinLoading(false)
    }
  }

  function clearError() {
    setInlineError('')
  }

  async function joinRoom(rId: string, code?: string) {
    setJoinLoading(true)
    setInlineError('')
    try {
      await ensureToken()
      const body: { room_id: string; queue_code?: string } = { room_id: rId }
      if (code) body.queue_code = code
      const res = await apiFetch('/api/v1/queue/ticket', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      const data: TakeTicketResponse = await res.json()
      if (!res.ok) {
        const detail = (data as { detail?: string }).detail || ''

        if (res.status === 403 && detail.toLowerCase().includes('закрыт')) {
          setClosedRoom({ room: rId, code })
          return
        }

        setClosedRoom(null)
        setInlineError(detail || 'Комната не найдена')
        return
      }

      setClosedRoom(null)
      if (data.is_admin && data.access_token) {
        setAccessToken(data.access_token)
        onJoinAsAdmin(rId)
      } else {
        onJoinAsUser(rId)
      }
    } catch (e) {
      setInlineError((e as Error).message)
    } finally {
      setJoinLoading(false)
    }
  }

  async function handleJoin() {
    const rId = roomInput.trim().toUpperCase()
    if (!rId || rId.length < 4) {
      setInlineError('Введите корректный ID комнаты')
      return
    }
    await joinRoom(rId)
  }

  async function handleCreate() {
    setCreateLoading(true)
    clearError()
    try {
      await ensureToken()

      const res = await apiFetch('/api/v1/rooms', { method: 'POST' })
      const data: RoomCreateResponse = await res.json()
      if (!res.ok) {
        setInlineError((data as { detail?: string }).detail || 'Ошибка создания комнаты')
        return
      }
      setAccessToken(data.access_token)
      onJoinAsAdmin(data.room_id)
    } catch (e) {
      setInlineError((e as Error).message)
    } finally {
      setCreateLoading(false)
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') handleJoin()
  }

  if (closedRoom) {
    return (
      <div className="page-wrap centered">
        <div className="center-wrap">
          <Logo />
          <Card title="Комната закрыта">
            <p className="modal-text" style={{ marginBottom: 16 }}>
              Приём в комнате <b>{closedRoom.room}</b> сейчас закрыт. Дождитесь, пока
              администратор откроет вход, и попробуйте снова.
            </p>
            <Button
              variant="primary"
              loading={joinLoading}
              onClick={() => joinRoom(closedRoom.room, closedRoom.code)}
            >
              Попробовать снова
            </Button>
            <Button variant="secondary" onClick={() => setClosedRoom(null)}>
              Назад
            </Button>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="page-wrap centered">
      <div className="center-wrap">
        <Logo />

        <Card title="Войти в комнату">
          {inlineError && <div className="inline-error">{inlineError}</div>}
          <label className="field-label" htmlFor="input-room-id">ID комнаты</label>
          <input
            id="input-room-id"
            type="text"
            placeholder="6 символов"
            maxLength={6}
            autoComplete="off"
            value={roomInput}
            onChange={e => setRoomInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <Button variant="primary" loading={joinLoading} onClick={handleJoin}>
            {joinLoading ? 'Подключение...' : 'Войти в очередь'}
          </Button>
          <div className="divider">или</div>
          <Button variant="secondary" loading={createLoading} onClick={handleCreate}>
            {createLoading ? 'Создание...' : 'Создать комнату (администратор)'}
          </Button>
        </Card>
      </div>
    </div>
  )
}
