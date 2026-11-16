/**
 * 数据刷新成功反馈（唯一文案真源）
 *
 * 对齐平台看板：点击刷新后提示「数据已刷新」。
 * UniTable 工具栏 reload、页签右键刷新、RefreshButton 均走此函数。
 */
import i18n from 'i18next'
import { getAntdMessage } from './antdAppApis'

export function notifyDataRefreshed(): void {
  getAntdMessage().success(i18n.t('common.refreshSuccess'))
}
