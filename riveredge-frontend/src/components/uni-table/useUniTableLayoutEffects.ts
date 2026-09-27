/**
 * UniTable 布局相关 useLayoutEffect（fillViewport / report / overflow /
 * syncContainerLayout / selectionAlertLayout）。
 * 统一经 observeLayoutTargets（单例 RO + resize bus）。
 * sticky 偏移留在 index（须排在操作列实测之后）。
 */

import React from 'react'
import {
  measureTableBodyOverflowsViewport,
  measureFillViewportTableBodyScrollY,
} from './uniTableScrollPolicy'
import { resolveUniReportTableBodyScrollY } from '../uni-report/uniReportScrollPolicy'
import { observeLayoutTargets } from './observeLayoutTargets'
import {
  measureOccupiedWidth,
  readStableTableBudgetWidth,
} from './uniTableDomMeasure'

/** 工具栏 DOM 尚未就绪时的回退：整表宽度低于此值则打印/导入/导出/同步仅图标 */
const DATA_ACTION_ICON_ONLY_MAX_WIDTH = 1280

/** 工具栏左簇 / 数据能力 / 设定图标之间的间距预算 */
const TOOLBAR_CLUSTER_GAP = 16

export type UseUniTableLayoutEffectsParams = {
  containerRef: React.RefObject<HTMLDivElement>
  tableBodyPaneRef: React.RefObject<HTMLDivElement>
  fillViewportBody: boolean
  proTableBodyScrollYEnabled: boolean
  setFillViewportMeasuredScrollY: React.Dispatch<React.SetStateAction<number | undefined>>
  reportLayout: boolean
  reportHasFixedSummary: boolean
  reportMeasuredScrollYRef: React.MutableRefObject<number | undefined>
  setReportMeasuredScrollY: React.Dispatch<React.SetStateAction<number | undefined>>
  policyScrollYEnabled: boolean
  setViewportScrollForced: React.Dispatch<React.SetStateAction<boolean>>
  viewportRemeasureKey: string
  viewportRemeasureKeyRef: React.MutableRefObject<string>
  currentViewType: string
  columnStructureSig: string
  showDelayedLoading: boolean
  tableSummaryProp: unknown
  tableDataLength: number
  setContainerLayoutWidth: React.Dispatch<React.SetStateAction<number>>
  setDataActionIconOnly: React.Dispatch<React.SetStateAction<boolean>>
  dataActionIconOnlyRef: React.MutableRefObject<boolean>
  labeledDataActionsWidthRef: React.MutableRefObject<number>
  enableRowSelection: boolean
  selectedRowKeysLength: number
  isMobile: boolean
  setSelectionAlertLayout: React.Dispatch<
    React.SetStateAction<{ top: number; height: number } | null>
  >
}

export function useUniTableLayoutEffects(p: UseUniTableLayoutEffectsParams): void {
  const {
    containerRef,
    tableBodyPaneRef,
    fillViewportBody,
    proTableBodyScrollYEnabled,
    setFillViewportMeasuredScrollY,
    reportLayout,
    reportHasFixedSummary,
    reportMeasuredScrollYRef,
    setReportMeasuredScrollY,
    policyScrollYEnabled,
    setViewportScrollForced,
    viewportRemeasureKey,
    viewportRemeasureKeyRef,
    currentViewType,
    columnStructureSig,
    showDelayedLoading,
    tableSummaryProp,
    tableDataLength,
    setContainerLayoutWidth,
    setDataActionIconOnly,
    dataActionIconOnlyRef,
    labeledDataActionsWidthRef,
    enableRowSelection,
    selectedRowKeysLength,
    isMobile,
    setSelectionAlertLayout,
  } = p

  React.useLayoutEffect(() => {
    if (!fillViewportBody || !proTableBodyScrollYEnabled) {
      setFillViewportMeasuredScrollY(undefined)
      return
    }
    const root = containerRef.current
    if (!root) return

    const measure = () => {
      const next = measureFillViewportTableBodyScrollY(root)
      if (next == null) return
      setFillViewportMeasuredScrollY((prev) => (prev === next ? prev : next))
    }

    measure()
    return observeLayoutTargets(
      [
        root,
        root.querySelector('.ant-table-wrapper'),
        root.querySelector('.ant-table-summary'),
        root.querySelector('.ant-table-pagination'),
      ],
      measure,
    )
  }, [
    containerRef,
    fillViewportBody,
    proTableBodyScrollYEnabled,
    setFillViewportMeasuredScrollY,
    tableDataLength,
    showDelayedLoading,
    columnStructureSig,
    tableSummaryProp,
    currentViewType,
  ])

  React.useLayoutEffect(() => {
    if (!reportLayout) {
      reportMeasuredScrollYRef.current = undefined
      setReportMeasuredScrollY(undefined)
      return
    }
    if (currentViewType !== 'table' && currentViewType !== 'detailTable') {
      reportMeasuredScrollYRef.current = undefined
      setReportMeasuredScrollY(undefined)
      return
    }

    const root = containerRef.current
    if (!root) return

    const allowTurnOff = viewportRemeasureKeyRef.current !== viewportRemeasureKey
    viewportRemeasureKeyRef.current = viewportRemeasureKey

    const applyMeasure = (canTurnOff: boolean) => {
      const next = resolveUniReportTableBodyScrollY(root, reportHasFixedSummary)
      setReportMeasuredScrollY((prev) => {
        if (next == null) {
          if (prev == null) return prev
          if (canTurnOff) {
            reportMeasuredScrollYRef.current = undefined
            return undefined
          }
          return prev
        }
        if (prev === next) return prev
        reportMeasuredScrollYRef.current = next
        return next
      })
    }

    applyMeasure(allowTurnOff)
    return observeLayoutTargets(
      [
        root,
        root.querySelector('.ant-table-wrapper'),
        root.querySelector('.ant-table-summary'),
        root.querySelector('.ant-table-pagination'),
        root.querySelector('.ant-table-body'),
      ],
      () => applyMeasure(false),
      { onWindowResize: () => applyMeasure(true) },
    )
  }, [
    containerRef,
    reportLayout,
    reportHasFixedSummary,
    reportMeasuredScrollYRef,
    setReportMeasuredScrollY,
    viewportRemeasureKey,
    viewportRemeasureKeyRef,
    currentViewType,
    columnStructureSig,
    showDelayedLoading,
    tableSummaryProp,
  ])

  React.useLayoutEffect(() => {
    const turnOffForced = () => setViewportScrollForced((prev) => (prev ? false : prev))
    const turnOnForced = () => setViewportScrollForced((prev) => (prev ? prev : true))

    if (reportLayout) {
      turnOffForced()
      return
    }

    if (policyScrollYEnabled) {
      viewportRemeasureKeyRef.current = viewportRemeasureKey
      turnOffForced()
      return
    }
    if (tableDataLength === 0) {
      viewportRemeasureKeyRef.current = viewportRemeasureKey
      turnOffForced()
      return
    }
    if (currentViewType !== 'table' && currentViewType !== 'detailTable') {
      viewportRemeasureKeyRef.current = viewportRemeasureKey
      turnOffForced()
      return
    }

    const root = containerRef.current
    if (!root) return

    // 数据/分页/视图变化才允许关回。列宽、loading、拆表后的二次测量只能开不能关，
    // 否则 natural ↔ scroll.y 在 useLayoutEffect 里同步振荡（生产 React #185）。
    const allowTurnOff = viewportRemeasureKeyRef.current !== viewportRemeasureKey
    viewportRemeasureKeyRef.current = viewportRemeasureKey
    const overflows = measureTableBodyOverflowsViewport(root)
    if (overflows) {
      turnOnForced()
    } else if (allowTurnOff) {
      turnOffForced()
    }

    const observeOverflowOn = () => {
      if (!measureTableBodyOverflowsViewport(root)) return
      turnOnForced()
    }

    const scrollBody = root.querySelector('.ant-table-body')
    const tbody = (scrollBody?.querySelector('.ant-table-tbody') ??
      root.querySelector('.ant-table-tbody')) as Element | null
    return observeLayoutTargets(
      [tbody, scrollBody, root.querySelector('.ant-table-wrapper')],
      observeOverflowOn,
    )
    // 依赖列结构签名而非 effectiveTableColumns：实测会改列宽并生成新 columns 引用，
    // 若再依赖 columns 会在树表展开时 useLayoutEffect → setState → 同步死循环。
  }, [
    containerRef,
    policyScrollYEnabled,
    viewportRemeasureKey,
    viewportRemeasureKeyRef,
    setViewportScrollForced,
    currentViewType,
    columnStructureSig,
    showDelayedLoading,
    reportLayout,
  ])

  React.useLayoutEffect(() => {
    const root = containerRef.current
    if (!root) return

    const syncContainerLayout = () => {
      // 只用托盘宽度。纵向滚动条由布局引擎按 scroll.y 扣除，不再改读滚动口。
      const width = readStableTableBudgetWidth(root)
      if (width > 0) {
        setContainerLayoutWidth((prev) => (prev === width ? prev : width))
      }

      const toolbar = root.querySelector(
        '.ant-pro-table-list-toolbar-container',
      ) as HTMLElement | null
      if (!toolbar) {
        const next = width > 0 && width < DATA_ACTION_ICON_ONLY_MAX_WIDTH
        setDataActionIconOnly((prev) => (prev === next ? prev : next))
        return
      }

      const left = toolbar.querySelector('.ant-pro-table-list-toolbar-left') as HTMLElement | null
      const dataActions = toolbar.querySelector('.uni-table-data-actions') as HTMLElement | null
      const settings = toolbar.querySelector(
        '.ant-pro-table-list-toolbar-setting-items',
      ) as HTMLElement | null

      // 仅在「带文案」时刷新基准宽，icon-only 时继续用该值判断是否恢复文案（防振荡）
      if (dataActions && !dataActionIconOnlyRef.current) {
        labeledDataActionsWidthRef.current = measureOccupiedWidth(dataActions)
      }
      const labeledNeed =
        labeledDataActionsWidthRef.current || measureOccupiedWidth(dataActions)

      const leftNeed = measureOccupiedWidth(left)
      const optionsWidth = measureOccupiedWidth(settings)

      // 剩余给「打印/导入/导出/同步」的宽度；够放文案则显示文字，否则仅图标
      const available = toolbar.clientWidth - leftNeed - optionsWidth - TOOLBAR_CLUSTER_GAP
      const next = labeledNeed > 0 && available < labeledNeed
      setDataActionIconOnly((prev) => (prev === next ? prev : next))
    }

    syncContainerLayout()
    return observeLayoutTargets(
      [
        root,
        root.querySelector('.ant-pro-table-list-toolbar-container'),
        root.querySelector('.ant-pro-table-list-toolbar-left'),
        root.querySelector('.ant-pro-table-list-toolbar-right'),
        root.querySelector('.uni-table-data-actions'),
        root.querySelector('.ant-pro-table-list-toolbar-setting-items'),
      ],
      syncContainerLayout,
    )
  }, [
    containerRef,
    currentViewType,
    setContainerLayoutWidth,
    setDataActionIconOnly,
    dataActionIconOnlyRef,
    labeledDataActionsWidthRef,
  ])

  React.useLayoutEffect(() => {
    if (!enableRowSelection || selectedRowKeysLength === 0) return
    const host = tableBodyPaneRef.current
    if (!host) return

    const syncLayout = () => {
      const pager = host.querySelector('.ant-table-wrapper .ant-table-pagination') as HTMLElement | null
      if (!pager) return
      const hostRect = host.getBoundingClientRect()
      const pagerRect = pager.getBoundingClientRect()
      const next = {
        top: Math.max(0, pagerRect.top - hostRect.top),
        height: Math.max(1, pagerRect.height),
      }
      setSelectionAlertLayout((prev) => {
        if (!prev) return next
        if (Math.abs(prev.top - next.top) < 0.5 && Math.abs(prev.height - next.height) < 0.5) return prev
        return next
      })
    }

    syncLayout()
    return observeLayoutTargets(
      [host, host.querySelector('.ant-table-wrapper .ant-table-pagination')],
      syncLayout,
    )
  }, [
    tableBodyPaneRef,
    enableRowSelection,
    selectedRowKeysLength,
    currentViewType,
    isMobile,
    setSelectionAlertLayout,
  ])
}
