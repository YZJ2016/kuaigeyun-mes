/**
 * UniTable DOM 测量纯函数（布局 / sticky 偏移 / 工具栏占用宽）。
 */

import { getUniTableVerticalScrollbarWidth } from '../../utils/uniTableLayoutColumns'

/**
 * rc-table 的粘性 left/right 来自测宽行的一次性记录。
 * 操作列和托盘宽度在那次记录之后才提交，首帧固定列会按旧偏移画出，
 * 绘制后再被 ResizeObserver 挪到新位置。中间列只用 col 宽，所以不动。
 * 这里在绘制前按当前测宽行写回表头 col 与固定列偏移，与随后的实测一致。
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
    const colgroup = Array.from(table.children).find((el) => el.tagName === 'COLGROUP')
    const cols = colgroup
      ? (Array.from(colgroup.children).filter((el) => el.tagName === 'COL') as HTMLElement[])
      : []
    const dataColCount =
      withGutter && cols.length === widths.length + 1 ? widths.length : Math.min(widths.length, cols.length)
    const indexRow = Array.from(table.rows).find((row) => {
      if (row.classList.contains('ant-table-measure-row')) return false
      const dataCells = Array.from(row.cells).filter(
        (cell) => !cell.classList.contains('ant-table-cell-scrollbar'),
      )
      return dataCells.length === widths.length
    })
    const indexCells = indexRow
      ? Array.from(indexRow.cells).filter((cell) => !cell.classList.contains('ant-table-cell-scrollbar'))
      : []
    for (let i = 0; i < dataColCount; i += 1) {
      const cell = indexCells[i]
      const col = cols[i]
      if (!cell || !col) continue
      const fixed =
        cell.classList.contains('ant-table-cell-fix-left') ||
        cell.classList.contains('ant-table-cell-fix-right')
      if (!fixed) continue
      const width = widths[i]
      if (!(width > 0)) continue
      const next = `${width}px`
      if (col.style.width !== next) col.style.width = next
    }

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
 * 列宽预算用表格托盘的内容宽，不读 `.ant-table-body` / `.ant-table-content`。
 * 滚动口宽度会随刚设上的列宽变化，读它会在首帧之后再改一版标题列宽。
 */
export function readStableTableBudgetWidth(root: HTMLElement): number {
  const wrapper = root.querySelector('.uni-table-pro-table .ant-table-wrapper') as HTMLElement | null
  const host = wrapper ?? root
  const tableContainer = host.querySelector('.ant-table-container') as HTMLElement | null
  let borderX = 0
  if (tableContainer) {
    const style = getComputedStyle(tableContainer)
    borderX = (parseFloat(style.borderLeftWidth) || 0) + (parseFloat(style.borderRightWidth) || 0)
  }
  return Math.max(0, Math.round(host.clientWidth - borderX))
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
