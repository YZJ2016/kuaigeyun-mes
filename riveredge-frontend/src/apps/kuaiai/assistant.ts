/**
 * 打开全局 KU-Ask 助手抽屉（与 BasicLayout 的
 * 'riveredge:open-ai-assistant' 监听对应；抽屉不存在时事件空转）。
 */
export function openAssistantDrawer(): void {
  window.dispatchEvent(new Event('riveredge:open-ai-assistant'));
}
