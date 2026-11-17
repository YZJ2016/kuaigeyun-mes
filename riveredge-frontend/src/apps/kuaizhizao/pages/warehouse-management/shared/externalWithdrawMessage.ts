/** 仓储单据撤回响应中的金蝶侧未完全同步提示（与后端 external_withdraw_message 一致）。 */
export function readExternalWithdrawMessage(res: unknown): string | undefined {
  if (res == null || typeof res !== 'object') return undefined;
  const msg = (res as { external_withdraw_message?: unknown }).external_withdraw_message;
  if (typeof msg !== 'string') return undefined;
  const trimmed = msg.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}
