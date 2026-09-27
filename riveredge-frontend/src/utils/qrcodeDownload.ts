/**
 * 从二维码 data URI 触发 PNG 下载（与 QRCodeGenerator 行为一致）
 */
export function downloadQrcodePngFromDataUri(dataUri: string, fileName: string): void {
  const base64Data = dataUri.split(',')[1];
  if (!base64Data) {
    throw new Error('Invalid qrcode image data');
  }
  const byteCharacters = window.atob(base64Data);
  const byteNumbers = new Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i += 1) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  const blob = new window.Blob([byteArray], { type: 'image/png' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName.endsWith('.png') ? fileName : `${fileName}.png`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

export function sanitizeQrcodeFileName(boxNo: string, bindingId: number): string {
  const safe = String(boxNo || bindingId)
    .replace(/[^\w\u4e00-\u9fff-]+/g, '_')
    .slice(0, 80);
  return `packing-box-${safe || bindingId}`;
}
