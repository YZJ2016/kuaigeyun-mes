/**
 * 文件下载工具
 *
 * 支持 Blob 或字符串内容下载，供各 APP 共享使用。
 */

import { API_BASE_URL, buildAuthTenantHeaders, formatApiErrorDetail } from '../services/api';

function parseDownloadFilename(contentDisposition: string, fallback: string): string {
  const rfc5987 = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (rfc5987?.[1]) {
    try {
      return decodeURIComponent(rfc5987[1]);
    } catch {
      return fallback;
    }
  }
  const quoted = contentDisposition.match(/filename="([^"]+)"/i);
  if (quoted?.[1]) return quoted[1];
  const plain = contentDisposition.match(/filename=([^;]+)/i);
  if (plain?.[1]) return plain[1].trim().replace(/^"|"$/g, '');
  return fallback;
}

/** GET 二进制导出（Excel/PDF 等）；勿走 apiRequest JSON 解析。 */
export async function downloadBinaryFromApi(path: string, fallbackFilename: string): Promise<void> {
  const requestUrl = path.startsWith('http')
    ? path
    : `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
  const response = await fetch(requestUrl, {
    method: 'GET',
    headers: buildAuthTenantHeaders(),
    cache: 'no-store',
  });
  const contentType = (response.headers.get('Content-Type') || '').toLowerCase();

  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown };
      message = formatApiErrorDetail(parsed.detail ?? parsed.message ?? text) || text;
    } catch {
      /* keep text */
    }
    throw new Error(message || `HTTP ${response.status}`);
  }

  if (contentType.includes('application/json')) {
    const text = await response.text();
    try {
      const parsed = JSON.parse(text) as { detail?: unknown; message?: unknown };
      throw new Error(formatApiErrorDetail(parsed.detail ?? parsed.message ?? text) || '下载失败');
    } catch (error) {
      if (error instanceof Error && error.message !== '下载失败') throw error;
      throw new Error('下载失败');
    }
  }

  const blob = await response.blob();
  if (!(blob instanceof Blob) || blob.size <= 0) {
    throw new Error('下载失败：空文件');
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const filename = parseDownloadFilename(disposition, fallbackFilename);
  downloadFile(blob, filename);
}

/**
 * 从 Blob 下载文件
 */
export function downloadFile(blob: Blob, filename: string): void;

/**
 * 从字符串内容下载文件（如 CSV）
 * @param content 文本内容
 * @param filename 文件名
 * @param mimeType 可选，MIME 类型，默认 text/plain
 */
export function downloadFile(
  content: string,
  filename: string,
  mimeType?: string
): void;

export function downloadFile(
  blobOrContent: Blob | string,
  filename: string,
  mimeType?: string
): void {
  const blob =
    typeof blobOrContent === 'string'
      ? new Blob([blobOrContent], { type: mimeType || 'text/plain' })
      : blobOrContent;

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
