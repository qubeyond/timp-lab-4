export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface TakeTicketResponse {
  is_admin: boolean
  room_id: string | null
  queue_label: string | null
  access_token: string | null
  ticket: string | null
  position: number | null
}

export interface LeaveQueueResponse {
  status: string
}

export interface RoomCreateResponse {
  room_id: string
  access_token: string
  token_type: string
}

export interface RoomCloseResponse {
  status: string
}

export type TicketStatus = 'waiting' | 'on_way' | 'no_show'

export interface WaitingTicket {
  ticket: string
  status: TicketStatus
  position: number
}

export interface QueueInfo {
  label: string
  code: string
  length: number
  status: 'serving' | 'waiting'
  current_ticket: string
  current_status: TicketStatus | ''
  elapsed_time: number
  waiting: WaitingTicket[]
}

export interface ClientContext {
  ticket_label: string
  queue_label: string
  position_label: string
  ticket_status: TicketStatus | ''
  should_redirect: boolean
}

export interface AdminContext {
  queues: QueueInfo[]
  elapsed_time: number
}

export interface RoomStateResponse {
  room_closed: boolean
  room_id: string
  is_open: boolean
  balancer_enabled: boolean
  is_owner: boolean
  current_status: string | null
  elapsed_time: number | null
  avg_serve_seconds: number | null
  client_context: ClientContext | null
  admin_context: AdminContext | null
}

export interface CallNextResponse {
  status: string
  queue_label: string
  ticket: string
}

export interface CompleteServingResponse {
  status: string
}

export interface QueueMutationResponse {
  status: string
  queue_label: string
  code: string
}

export interface TicketTimeline {
  ticket: string
  queue_label: string
  joined_at: string
  wait_seconds: number | null
  serve_seconds: number | null
}

export interface RoomStatsResponse {
  room_id: string
  total_tickets: number
  completed: number
  avg_serve_seconds: number
  timeline: TicketTimeline[]
}

export type WsMessage =
  | { type: 'welcome'; data: RoomStateResponse }
  | { type: 'update'; data: { room_closed?: boolean } }
