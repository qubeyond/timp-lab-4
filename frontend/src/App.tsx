import { useState, useEffect } from 'react'
import { MainPage } from '@/pages/MainPage'
import { UserPage } from '@/pages/UserPage'
import { AdminPage } from '@/pages/AdminPage'
import { ErrorPage } from '@/pages/ErrorPage'
import { ToastContainer } from '@/components/ToastContainer'
import { useToast } from '@/hooks/useToast'
import {
  ROOM_KEY,
  ROLE_KEY,
  ensureToken,
  apiFetch,
  setAccessToken,
  clearAccessToken,
} from '@/lib/auth'
import type { TakeTicketResponse } from '@/types/api'

type Page = 'main' | 'user' | 'admin'
type AppState = 'loading' | 'ok' | 'unavailable' | '404' | 'error'

export default function App() {
  const [page, setPage] = useState<Page>('main')
  const [roomId, setRoomId] = useState('')
  const [appState, setAppState] = useState<AppState>('loading')
  const { toasts, addToast, removeToast } = useToast()

  useEffect(() => {
    checkHealth()
  }, [])

  async function checkHealth() {
    try {
      const res = await fetch('/health')
      if (res.ok) {
        setAppState('ok')
        restoreSession()
      } else {
        setAppState('unavailable')
      }
    } catch {
      setAppState('unavailable')
    }
  }

  async function restoreSession() {
    const savedRoom = localStorage.getItem(ROOM_KEY)
    const savedRole = localStorage.getItem(ROLE_KEY)
    if (!savedRoom || !savedRole) return

    try {
      await ensureToken()
    } catch (_) {
      goMain()
      return
    }

    if (savedRole === 'admin') {
      try {
        const res = await apiFetch('/api/v1/queue/ticket', {
          method: 'POST',
          body: JSON.stringify({ room_id: savedRoom }),
        })
        const data: TakeTicketResponse = await res.json()
        if (res.ok && data.is_admin && data.access_token) {
          setAccessToken(data.access_token)
          localStorage.setItem(ROLE_KEY, 'admin')
          setRoomId(savedRoom)
          setPage('admin')
          return
        }
      } catch (_) {}
      goMain()
      return
    }

    setRoomId(savedRoom)
    setPage('user')
  }

  function goMain() {
    clearAccessToken()
    setRoomId('')
    setPage('main')
    localStorage.removeItem(ROOM_KEY)
    localStorage.removeItem(ROLE_KEY)
  }

  function handleJoinAsUser(rId: string) {
    localStorage.setItem(ROOM_KEY, rId)
    localStorage.setItem(ROLE_KEY, 'user')
    setRoomId(rId)
    setPage('user')
  }

  function handleJoinAsAdmin(rId: string) {
    localStorage.setItem(ROOM_KEY, rId)
    localStorage.setItem(ROLE_KEY, 'admin')
    setRoomId(rId)
    setPage('admin')
  }

  function handleServed() {
    addToast('Вы были обслужены. Спасибо!', 'success')
    goMain()
  }

  function handleRoomClosed() {
    addToast('Комната закрыта', 'info')
    goMain()
  }

  if (appState === 'loading') return null

  if (appState === 'unavailable') {
    return (
      <ErrorPage
        title="Сервис временно недоступен"
        message="Ведутся технические работы. Пожалуйста, попробуйте позже."
      />
    )
  }

  if (appState === '404') {
    return (
      <ErrorPage
        code={404}
        title="Страница не найдена"
        message="Такой страницы не существует. Возможно, ссылка устарела."
      />
    )
  }

  if (appState === 'error') {
    return (
      <ErrorPage
        title="Что-то пошло не так"
        message="Произошла непредвиденная ошибка. Попробуйте обновить страницу."
        onRetry={() => window.location.reload()}
      />
    )
  }

  return (
    <>
      <ToastContainer toasts={toasts} onRemove={removeToast} />

      {page === 'main' && (
        <MainPage
          onJoinAsUser={handleJoinAsUser}
          onJoinAsAdmin={handleJoinAsAdmin}
        />
      )}
      {page === 'user' && (
        <UserPage
          roomId={roomId}
          onLeave={goMain}
          onServed={handleServed}
          onRoomClosed={handleRoomClosed}
          onToast={addToast}
        />
      )}
      {page === 'admin' && (
        <AdminPage
          roomId={roomId}
          onClose={goMain}
          onRoomClosed={handleRoomClosed}
          onToast={addToast}
        />
      )}
    </>
  )
}
