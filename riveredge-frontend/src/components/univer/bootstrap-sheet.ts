/**
 * Univer Sheet 初始化入口（import / export 共用）
 */
import '@univerjs/design/lib/index.css';
import '@univerjs/ui/lib/index.css';
import '@univerjs/sheets-ui/lib/index.css';
import '@univerjs/presets/lib/styles/preset-sheets-core.css';
import '@univerjs/presets/lib/styles/preset-sheets-data-validation.css';

import { createUniver, defaultTheme, LocaleType, merge } from '@univerjs/presets';
import { IRenderManagerService } from '@univerjs/engine-render';
import { UniverSheetsCorePreset } from '@univerjs/presets/preset-sheets-core';
import UniverPresetSheetsCoreZhCN from '@univerjs/presets/preset-sheets-core/locales/zh-CN';
import { UniverSheetsDataValidationPreset } from '@univerjs/presets/preset-sheets-data-validation';
import UniverPresetSheetsDataValidationZhCN from '@univerjs/presets/preset-sheets-data-validation/locales/zh-CN';

export type UniverSheetInstance = ReturnType<typeof createUniver>;

export interface CreateUniverSheetOptions {
  containerId: string;
  darkMode?: boolean;
}

export function createUniverSheetInstance(options: CreateUniverSheetOptions): UniverSheetInstance {
  const { containerId, darkMode = false } = options;

  return createUniver({
    locale: LocaleType.ZH_CN,
    locales: {
      [LocaleType.ZH_CN]: merge(
        {},
        UniverPresetSheetsCoreZhCN,
        UniverPresetSheetsDataValidationZhCN,
      ),
    },
    theme: defaultTheme,
    darkMode,
    presets: [
      UniverSheetsCorePreset({
        container: containerId,
      }),
      UniverSheetsDataValidationPreset(),
    ],
  });
}

/**
 * @univerjs/sheets-ui 的 SheetsRenderService 在构造器里通过 `Promise.resolve().then(() => this._init())`
 * 注册 workbook→renderer 监听。createWorkbook 及依赖 renderer 的命令须在该 microtask 之后执行。
 */
export function runAfterUniverSheetsRenderServiceInit(run: () => void): void {
  queueMicrotask(run);
}

/**
 * 容器尺寸变化后通知 Univer 按「可见盒」重排。
 *
 * Engine.resize() 用 getComputedStyle(width)；子树若被外层 overflow:hidden 裁切，
 * 画布父级 clientWidth 仍可能是未裁切布局宽，列已被切掉却不出现横滚条。
 * 传入 clipEl（如 .uni-import-sheet-host）时用其 clientWidth 作为视口宽。
 */
export function relayoutUniverSheet(
  instance: UniverSheetInstance,
  clipEl?: HTMLElement | null,
): void {
  // dispose 后 getUnit 为 null，内部会抛 getSheetBySheetId；须吞掉，禁止冒泡成全局错误
  try {
    const workbook = instance.univerAPI.getActiveWorkbook?.() ?? null;
    if (!workbook) return;

    const unitId = workbook.getId();
    const injector = instance.univer.__getInjector();
    const renderManager = injector.get(IRenderManagerService);
    const engine = renderManager.getRenderById(unitId)?.engine as
      | {
          resize?: () => void;
          resizeBySize?: (width: number, height: number) => void;
          getCanvasElement?: () => HTMLCanvasElement | null;
        }
      | undefined;
    if (!engine) return;

    const canvas = typeof engine.getCanvasElement === 'function' ? engine.getCanvasElement() : null;
    const canvasHost = canvas?.parentElement;
    if (typeof engine.resizeBySize === 'function') {
      // 有裁剪盒时宽必须跟裁剪盒；高优先画布宿主（不含工具栏），但不得大于裁剪盒，
      // 否则内容撑破宿主后引擎仍认「未超高」而不出滚动条。
      const clipW = clipEl?.clientWidth ?? 0;
      const clipH = clipEl?.clientHeight ?? 0;
      const hostW = canvasHost?.clientWidth ?? 0;
      const hostH = canvasHost?.clientHeight ?? 0;
      const width = clipW > 0 ? clipW : hostW;
      let height = hostH > 0 ? hostH : clipH;
      if (clipH > 0 && height > clipH) {
        height = clipH;
      }
      if (width > 0 && height > 0) {
        engine.resizeBySize(width, height);
        return;
      }
    }
    engine.resize?.();
  } catch {
    // workbook 已卸载或渲染器未就绪
  }
}
