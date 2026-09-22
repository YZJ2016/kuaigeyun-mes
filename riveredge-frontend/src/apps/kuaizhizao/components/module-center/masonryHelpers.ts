/** 图表卡装箱权重：约等于 6 行小表 + 240px 图区，与默认表卡封顶对齐 */
export const MASONRY_CHART_WEIGHT = 6;

/**
 * 瀑布流卡可见性：模块中心事项卡一律挂载（含空数据，由卡内 Empty / 空表展示）。
 * 保留参数签名，避免各页调用处机械改签名；参数不再参与可见性判断。
 */
export function showMasonryCard(
  _loading?: boolean,
  _hasData?: boolean,
  _emptyFallback?: boolean,
): boolean {
  return true;
}

/** balanced 装箱权重：表/列表/动态按行数，封顶 8；空卡按 1 */
export function masonryWeightFromRows(rowCount: number, cap = 8): number {
  return Math.min(cap, Math.max(1, rowCount));
}

/**
 * @deprecated 卡已一律挂载，不再需要「全空才挂壳」；保留供旧调用兼容，恒为 true。
 */
export function resolveMasonryEmptyFallback(
  _masonryLoading: boolean,
  _hasDataFlags: boolean[],
): boolean {
  return true;
}
