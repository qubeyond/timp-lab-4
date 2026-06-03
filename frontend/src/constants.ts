export const TicketStatus = {
  WAITING: 'waiting',
  ON_WAY: 'on_way',
  NO_SHOW: 'no_show',
} as const

export const QueueState = {
  SERVING: 'serving',
  WAITING: 'waiting',
} as const

export const WsMessageType = {
  WELCOME: 'welcome',
  UPDATE: 'update',
} as const

export const Role = {
  USER: 'user',
  ADMIN: 'admin',
} as const

export const AdminRole = {
  FULL: 'full',
  QUEUES: 'queues',
} as const
