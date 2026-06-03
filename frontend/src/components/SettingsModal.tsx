import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui/Button'
import { Toggle } from '@/components/ui/Toggle'

interface Props {
  isOpen: boolean
  balancerEnabled: boolean
  isOwner: boolean
  onToggleEntry: (v: boolean) => void
  onToggleBalancer: (v: boolean) => void
  onInvite: () => void
  onClose: () => void
}

export function SettingsModal({
  isOpen,
  balancerEnabled,
  isOwner,
  onToggleEntry,
  onToggleBalancer,
  onInvite,
  onClose,
}: Props) {
  return (
    <Modal onClose={onClose} size="md" title="Настройки комнаты" showClose>
      <Toggle
        checked={isOpen}
        onChange={onToggleEntry}
        label={isOpen ? 'Приём открыт' : 'Приём закрыт'}
        hint={isOpen ? 'Гости могут занимать места.' : 'Новые гости ждут открытия.'}
      />
      <Toggle
        checked={balancerEnabled}
        onChange={onToggleBalancer}
        label="Балансировщик"
        hint="Авто-распределение. Выключите для входа по коду очереди (VIP)."
      />

      {isOwner && (
        <div className="invite-row">
          <Button variant="secondary" onClick={onInvite}>
            Пригласить со-администратора
          </Button>
          <p className="toggle-hint" style={{ marginTop: 6 }}>
            Скопирует ссылку. Открывший её получит права админа этой комнаты
            (кроме закрытия и приглашений).
          </p>
        </div>
      )}
    </Modal>
  )
}
