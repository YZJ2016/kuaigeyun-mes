/**
 * UniTable DOM 测量纯函数（布局 / sticky 偏移 / 工具栏占用宽）。
 */

import { getUniTableVerticalScrollbarWidth } from '../../utils/uniTableLayoutColumns'

/**
 * rc-table 的粘性 left/right 来自测宽行的一次性记录。
 * 操作列和托盘宽度在那次记录之后才提交，首帧固定列会按旧偏移画出，
 * 绘制后再被 ResizeObserver 挪到新位置。
 * 列宽只由布局引擎写入 col，这里只按测宽行回写 left/right，不再改 col 宽。
 */
export function syncFixedColumnStickyOffsets(root: HTMLElement): void {
  const container = root.querySelector<HTMLElement>('.uni-table-pro-table .ant-table-wrapper .ant-table-container')
  if (!container) return
  const measureRow = container.querySelector<HTMLElement>('tr.ant-table-measure-row')
  if (!measureRow || measureRow.children.length === 0) return
  const widths = Array.from(measureRow.children, (cell) => (cell as HTMLElement).offsetWidth)
  if (widths.every((width) => width <= 0)) return

  const gutter = root.classList.contains('uni-table-scroll-y-mode')
    ? getUniTableVerticalScrollbarWidth()
    : 0
  const holders = [
    container.querySelector<HTMLElement>(':scope > .ant-table-header'),
    container.querySelector<HTMLElement>(':scope > .ant-table-body'),
    container.querySelector<HTMLElement>(':scope > .ant-table-summary'),
    container.querySelector<HTMLElement>(':scope > .ant-table-content'),
  ].filter((holder): holder is HTMLElement => holder != null)

  holders.forEach((holder) => {
    const table = holder.firstElementChild
    if (!(table instanceof HTMLTableElement)) return
    const withGutter =
      gutter > 0 &&
      (holder.classList.contains('ant-table-header') || holder.classList.contains('ant-table-summary'))
    const rightGutter = withGutter ? gutter : 0
    for (const row of table.rows) {
      if (row.classList.contains('ant-table-measure-row')) continue
      applyFixedRowOffsets(row, widths, rightGutter)
    }
  })
}

function applyFixedRowOffsets(row: HTMLElement, widths: number[], rightGutter: number): void {
  const cells: HTMLElement[] = []
  for (let i = 0; i < row.children.length; i += 1) {
    const cell = row.children[i] as HTMLElement
    if (cell.classList.contains('ant-table-cell-scrollbar')) continue
    cells.push(cell)
  }
  const useMeasure = cells.length === widths.length
  let left = 0
  const rightIndexes: number[] = []
  for (let i = 0; i < cells.length; i += 1) {
    const cell = cells[i]
    const width = useMeasure ? widths[i] : cell.offsetWidth
    if (cell.classList.contains('ant-table-cell-fix-left')) {
      const next = `${left}px`
      if (cell.style.left !== next) cell.style.left = next
      left += width
    }
    if (cell.classList.contains('ant-table-cell-fix-right')) rightIndexes.push(i)
  }
  let right = rightGutter
  for (let k = rightIndexes.length - 1; k >= 0; k -= 1) {
    const index = rightIndexes[k]
    const cell = cells[index]
    const next = `${right}px`
    if (cell.style.right !== next) cell.style.right = next
    right += useMeasure ? widths[index] : cell.offsetWidth
  }
}

/**
 * 列宽预算的唯一宽度：滚动口 clientWidth。
 * 三桶规范只认 `.ant-table-body` / `.ant-table-content`，不用外层托盘。
 * 托盘比滚动口宽，余量列会按偏大的宽度撑开，右固定列被顶出滚动口。
 * 滚动口尚未挂载时返回 0，布局保持各列最小宽度，禁止改读外层。
 */
export function readStableTableBudgetWidth(root: HTMLElement): number {
  const scrollHost =
    (root.querySelector('.uni-table-pro-table .ant-table-body') as HTMLElement | null) ??
    (root.querySelector('.uni-table-pro-table .ant-table-content') as HTMLElement | null)
  if (!scrollHost || scrollHost.clientWidth <= 0) return 0
  return Math.round(scrollHost.clientWidth)
}

/**
 * 测量元素「内容实际占用」宽度。
 * ProTable 工具栏 left/right 常带 flex:1，直接读 scrollWidth 会被撑满，导致永远判定为仅图标。
 */
export function measureOccupiedWidth(el: HTMLElement | null | undefined): number {
  if (!el) return 0
  const kids = Array.from(el.children) as HTMLElement[]
  if (kids.length === 0) return 0
  let minL = Infinity
  let maxR = -Infinity
  for (const kid of kids) {
    const r = kid.getBoundingClientRect()
    if (r.width <= 0) continue
    minL = Math.min(minL, r.left)
    maxR = Math.max(maxR, r.right)
  }
  if (!Number.isFinite(minL) || !Number.isFinite(maxR) || maxR <= minL) {
    return Math.ceil(el.scrollWidth) || 0
  }
  return Math.ceil(maxR - minL)
}
