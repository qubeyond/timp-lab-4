
let swReg: ServiceWorkerRegistration | null = null

const NOTIF_TAG = 'queue-ticket'

export function notificationsSupported(): boolean {
  return 'Notification' in window && 'serviceWorker' in navigator
}

export function notificationPermission(): NotificationPermission {
  return notificationsSupported() ? Notification.permission : 'denied'
}

export async function registerServiceWorker(): Promise<void> {
  if (!('serviceWorker' in navigator)) return
  try {
    swReg = await navigator.serviceWorker.register('/sw.js')
  } catch {
    swReg = null
  }
}

export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!notificationsSupported()) return 'denied'
  if (Notification.permission === 'default') {
    return await Notification.requestPermission()
  }
  return Notification.permission
}

interface NotifyOptions {
  title: string
  body?: string

  sticky?: boolean
}

async function getReg(): Promise<ServiceWorkerRegistration | null> {
  if (swReg) return swReg
  if ('serviceWorker' in navigator) {
    try {
      swReg = (await navigator.serviceWorker.ready) ?? null
    } catch {
      swReg = null
    }
  }
  return swReg
}

export async function showNotification({ title, body, sticky }: NotifyOptions): Promise<void> {
  if (notificationPermission() !== 'granted') return

  const options: NotificationOptions = {
    body,
    tag: NOTIF_TAG,

    requireInteraction: !!sticky,
    renotify: true,
  } as NotificationOptions

  const reg = await getReg()
  if (reg) {
    await reg.showNotification(title, options)
  } else if ('Notification' in window) {

    new Notification(title, options)
  }
}

export async function clearTicketNotification(): Promise<void> {
  const reg = await getReg()
  if (!reg) return
  const notes = await reg.getNotifications({ tag: NOTIF_TAG })
  notes.forEach(n => n.close())
}
