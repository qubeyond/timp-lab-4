import { useEffect, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Toggle } from '@/components/ui/Toggle'
import { Select } from '@/components/ui/Select'
import type { AdminRole, CoAdminItem } from '@/types/api'

interface Props {
  isOpen: boolean
  balancerEnabled: boolean
  isOwner: boolean
  coAdmins: CoAdminItem[]
  onToggleEntry: (v: boolean) => void
  onToggleBalancer: (v: boolean) => void
  onInvite: (role: AdminRole) => void
  onRevoke: (userId: string) => void
  onRefreshAdmins: () => void
  onClose: () => void
}

const ROLE_LABELS: Record<AdminRole, string> = {
  full: 'Полный доступ',
  queues: 'Только очереди',
}

export function SettingsModal({
  isOpen,
  balancerEnabled,
  isOwner,
  coAdmins,
  onToggleEntry,
  onToggleBalancer,
  onInvite,
  onRevoke,
  onRefreshAdmins,
  onClose,
}: Props) {
  const [role, setRole] = useState<AdminRole>('full')

  useEffect(() => {
    if (isOwner) onRefreshAdmins()
  }, [isOwner])

  return (
    <Modal onClose={onClose} size="md" title="Настройки комнаты" showClose>
      <Toggle
        checked={isOpen}
        onChange={onToggleEntry}
        label={isOpen ? 'Комната открыта' : 'Комната закрыта'}
      />
      <Toggle
        checked={balancerEnabled}
        onChange={onToggleBalancer}
        label="Автораспределение"
        hint="Сами распределяем по очередям. Выключите, чтобы вход был по коду очереди."
      />

      {isOwner && (
        <div className="invite-block">
          <div className="settings-section-title">Со-администраторы</div>

          <label className="field-label">Роль приглашаемого</label>
          <Select<AdminRole>
            value={role}
            onChange={setRole}
            ariaLabel="Роль приглашаемого"
            options={[
              { value: 'full', label: 'Полный доступ', hint: 'Очереди и настройки комнаты' },
              { value: 'queues', label: 'Только очереди', hint: 'Вызов, завершение, перемещение' },
            ]}
          />

          <Button variant="secondary" onClick={() => onInvite(role)}>
            Создать ссылку-приглашение
          </Button>
          <p className="toggle-hint" style={{ marginTop: 6 }}>
            Ссылка действует один раз. Закрыть комнату может только владелец.
          </p>

          {coAdmins.length > 0 && (
            <ul className="coadmin-list">
              {coAdmins.map(a => (
                <li key={a.user_id} className="coadmin-item">
                  <span className="coadmin-role">{ROLE_LABELS[a.role] ?? a.role}</span>
                  <span className="coadmin-id">{a.user_id.slice(0, 10)}…</span>
                  <button
                    type="button"
                    className="coadmin-revoke"
                    title="Отозвать права"
                    onClick={() => onRevoke(a.user_id)}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Modal>
  )
}
