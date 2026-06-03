// Service worker для устойчивых уведомлений очереди.
// Лёгкий: без офлайн-кэша, только нотификации и фокус по клику.

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()))

// Клик по уведомлению — переводим фокус на открытую вкладку или открываем новую.
self.addEventListener('notificationclick', event => {
  event.notification.close()
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
      for (const client of clients) {
        if ('focus' in client) return client.focus()
      }
      if (self.clients.openWindow) return self.clients.openWindow('/')
    }),
  )
})
