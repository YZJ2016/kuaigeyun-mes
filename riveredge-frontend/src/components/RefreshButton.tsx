/**
 * 标准「刷新」按钮：点击执行 onClick 后统一提示「数据已刷新」。
 * 参照：平台看板 `/infra/operation`。
 */
import React from 'react'
import { Button, type ButtonProps } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { notifyDataRefreshed } from '../utils/notifyDataRefreshed'

export type RefreshButtonProps = Omit<ButtonProps, 'icon' | 'onClick'> & {
  onClick?: () => void | Promise<void>
  /** 为 true 时不在成功后弹 Toast（调用方自行反馈） */
  silent?: boolean
}

export function RefreshButton({
  onClick,
  silent = false,
  children,
  loading,
  ...rest
}: RefreshButtonProps) {
  const { t } = useTranslation()
  const [busy, setBusy] = React.useState(false)

  const handleClick = async () => {
    if (!onClick) {
      if (!silent) notifyDataRefreshed()
      return
    }
    setBusy(true)
    try {
      await onClick()
      if (!silent) notifyDataRefreshed()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Button
      icon={<ReloadOutlined />}
      loading={loading ?? busy}
      {...rest}
      onClick={() => {
        void handleClick()
      }}
    >
      {children ?? t('common.refresh')}
    </Button>
  )
}

export default RefreshButton
