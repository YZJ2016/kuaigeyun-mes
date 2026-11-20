/**
 * 批量操作工具函数
 * 
 * 提供统一的批量导入、导出和处理功能，支持并发处理、错误重试、进度跟踪等。
 */

import React from 'react';
import { Progress } from 'antd';
import { getAntdMessage, getAntdModal } from './antdAppApis';
import { runWithBulkImportErrorSuppress } from './bulkImportErrorSuppress';
import { getApiErrorMessage } from './errorHandler';
import { ImportResultModalContent } from './importResultModalContent';
import { todaySiteDateString } from './format';

/**
 * 批量导入配置
 */
export interface BatchImportConfig<T = any> {
  /**
   * 导入数据列表
   */
  items: T[];
  /**
   * 导入函数（单个数据项的导入逻辑）
   */
  importFn: (item: T, index: number) => Promise<any>;
  /**
   * 并发数（默认5）
   */
  concurrency?: number;
  /**
   * 重试次数（默认3）
   */
  retryCount?: number;
  /**
   * 标题
   */
  title?: string;
  /**
   * 进度回调
   */
  onProgress?: (current: number, total: number, success: number, fail: number) => void;
  /**
   * 完成回调
   */
  onComplete?: (result: BatchImportResult) => void;
}

/**
 * 批量导入结果
 */
export interface BatchImportResult {
  total: number;
  successCount: number;
  failureCount: number;
  errors: Array<{ row: number; error: string }>;
  successItems: any[];
  failureItems: any[];
}

/**
 * 批量导入数据（支持并发和重试）
 * 
 * @param config - 导入配置
 * @returns 导入结果
 */
export async function batchImport<T = any>(
  config: BatchImportConfig<T>
): Promise<BatchImportResult> {
  const {
    items,
    importFn,
    concurrency = 5,
    retryCount = 3,
    title = '正在导入数据',
    onProgress,
    onComplete,
  } = config;

  return runWithBulkImportErrorSuppress(async () => {
  // 显示导入进度 Modal
  const progressModal = getAntdModal().info({
    title,
    width: 600,
    content: (
      <div>
        <Progress percent={0} status="active" />
        <p style={{ marginTop: 16 }}>准备导入 {items.length} 条数据...</p>
      </div>
    ),
    okButtonProps: { style: { display: 'none' } },
  });

  const result: BatchImportResult = {
    total: items.length,
    successCount: 0,
    failureCount: 0,
    errors: [],
    successItems: [],
    failureItems: [],
  };

  // 批量导入（带并发控制和重试）
  const importWithRetry = async (item: T, index: number): Promise<{ success: boolean; error?: string; data?: any }> => {
    let lastError: string | undefined;
    
    for (let attempt = 0; attempt < retryCount; attempt++) {
      try {
        const data = await importFn(item, index);
        return { success: true, data };
      } catch (error: any) {
        lastError = getApiErrorMessage(error, '未知错误');
        if (attempt < retryCount - 1) {
          // 指数退避
          await new Promise(resolve => setTimeout(resolve, 500 * (attempt + 1)));
        }
      }
    }
    
    return { success: false, error: lastError };
  };

  // 真正的并发池：同时最多 concurrency 个在途，禁止 map 后立刻启动全部 Promise
  let nextIndex = 0;
  const workers = Array.from({ length: Math.max(1, concurrency) }, async () => {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      const item = items[index];
      const importResult = await importWithRetry(item, index);

      if (importResult.success) {
        result.successCount++;
        result.successItems.push(importResult.data);
      } else {
        result.failureCount++;
        result.errors.push({
          row: index + 1,
          error: importResult.error || '未知错误',
        });
        result.failureItems.push(item);
      }

      const done = result.successCount + result.failureCount;
      const percent = Math.round((done / items.length) * 100);
      progressModal.update({
        content: (
          <div>
            <Progress percent={percent} status="active" />
            <p style={{ marginTop: 16 }}>
              正在导入第 {done} / {items.length} 条数据...
            </p>
            <p style={{ marginTop: 8, color: '#52c41a' }}>
              成功：{result.successCount} 条 | 失败：{result.failureCount} 条
            </p>
          </div>
        ),
      });

      if (onProgress) {
        onProgress(done, items.length, result.successCount, result.failureCount);
      }
    }
  });

  await Promise.all(workers);

  // 关闭进度 Modal
  progressModal.destroy();

  // 显示导入结果
  if (result.failureCount > 0) {
    getAntdModal().warning({
      title: `${title}（部分失败）`,
      width: 720,
      content: (
        <ImportResultModalContent
          successCount={result.successCount}
          failureCount={result.failureCount}
          errors={result.errors}
        />
      ),
    });
  } else {
    getAntdMessage().success(`成功导入 ${result.successCount} 条数据`);
  }

  if (onComplete) {
    onComplete(result);
  }

  return result;
  });
}

/**
 * 批量导出数据到 CSV
 * 
 * @param data - 数据列表
 * @param headers - CSV 表头
 * @param fieldMapping - 字段映射
 * @param filename - 文件名
 */
export function exportToCSV(
  data: any[],
  headers: string[],
  fieldMapping: Record<string, string>,
  filename: string = `export_${todaySiteDateString()}.csv`
): void {
  // 构建 CSV 内容
  const csvRows: string[] = [];
  
  // 添加表头
  csvRows.push(headers.join(','));
  
  // 添加数据行
  for (const item of data) {
    const row: string[] = [];
    for (const header of headers) {
      const fieldName = fieldMapping[header] || header;
      let value = item[fieldName] || '';
      
      // 处理复杂类型
      if (typeof value === 'object') {
        value = JSON.stringify(value);
      }
      
      // 转义 CSV 特殊字符
      if (typeof value === 'string' && (value.includes(',') || value.includes('"') || value.includes('\n'))) {
        value = `"${value.replace(/"/g, '""')}"`;
      }
      
      row.push(String(value));
    }
    csvRows.push(row.join(','));
  }
  
  // 创建 Blob 并下载
  const csvContent = csvRows.join('\n');
  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' }); // 添加 BOM 以支持 Excel 中文
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  
  getAntdMessage().success(`导出成功，共 ${data.length} 条数据`);
}

export type BatchProcessResult = {
  successCount: number;
  failureCount: number;
  errors: Array<{ index: number; error: string }>;
};

export type BatchProcessOptions = {
  /** 进度弹窗标题（如「删除中」） */
  title: string;
  /** 并发数；删除类建议 1，保证进度文案与完成顺序一致 */
  concurrency?: number;
  /** 开始前文案 */
  preparingText?: (total: number) => React.ReactNode;
  /** 进行中文案 */
  progressText?: (
    current: number,
    total: number,
    success: number,
    fail: number,
  ) => React.ReactNode;
  /**
   * 是否由工具函数弹出成功/部分失败提示。
   * 默认 false：由调用方根据业务文案展示「删除完成」与失败明细。
   */
  showResultToast?: boolean;
  /** showResultToast 时的成功文案 */
  successMessage?: (successCount: number) => string;
  /** showResultToast 时部分失败标题 */
  partialTitle?: string;
  /** showResultToast 时部分失败正文；未传则只展示成功/失败条数 */
  partialContent?: (result: BatchProcessResult) => React.ReactNode;
};

/**
 * 批量处理（删除/更新等）：进度弹窗 + 并发池；错误文案走 getApiErrorMessage。
 * 结果提示默认交给调用方（便于 i18n「删除中 / 删除完成」与失败明细）。
 */
export async function batchProcess<T = any>(
  items: T[],
  processFn: (item: T, index: number) => Promise<any>,
  options: BatchProcessOptions,
): Promise<BatchProcessResult> {
  const {
    title,
    concurrency = 1,
    preparingText,
    progressText,
    showResultToast = false,
    successMessage,
    partialTitle,
    partialContent,
  } = options;

  const result: BatchProcessResult = {
    successCount: 0,
    failureCount: 0,
    errors: [],
  };

  if (items.length === 0) {
    return result;
  }

  const renderProgress = (
    current: number,
    total: number,
    success: number,
    fail: number,
  ) => (
    <div>
      <Progress
        percent={total > 0 ? Math.round((current / total) * 100) : 0}
        status="active"
      />
      <p style={{ marginTop: 16 }}>
        {current === 0
          ? (preparingText?.(total) ?? `准备处理 ${total} 条数据...`)
          : (progressText?.(current, total, success, fail) ??
            `正在处理第 ${current} / ${total} 条数据...`)}
      </p>
      {current > 0 ? (
        <p style={{ marginTop: 8, color: '#52c41a' }}>
          成功：{success} 条 | 失败：{fail} 条
        </p>
      ) : null}
    </div>
  );

  const progressModal = getAntdModal().info({
    title,
    width: 600,
    content: renderProgress(0, items.length, 0, 0),
    okButtonProps: { style: { display: 'none' } },
  });

  let nextIndex = 0;
  const workers = Array.from({ length: Math.max(1, concurrency) }, async () => {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      const item = items[index];
      try {
        await processFn(item, index);
        result.successCount += 1;
      } catch (error: unknown) {
        result.failureCount += 1;
        result.errors.push({
          index,
          error: getApiErrorMessage(error, '操作失败'),
        });
      }
      const done = result.successCount + result.failureCount;
      progressModal.update({
        content: renderProgress(
          done,
          items.length,
          result.successCount,
          result.failureCount,
        ),
      });
    }
  });

  await Promise.all(workers);
  progressModal.destroy();

  if (showResultToast) {
    if (result.failureCount > 0) {
      getAntdModal().warning({
        title: partialTitle ?? `${title}（部分失败）`,
        width: 640,
        content:
          partialContent?.(result) ??
          `成功处理 ${result.successCount} 条，失败 ${result.failureCount} 条`,
      });
    } else if (result.successCount > 0) {
      getAntdMessage().success(
        successMessage?.(result.successCount) ??
          `成功处理 ${result.successCount} 条数据`,
      );
    }
  }

  return result;
}

