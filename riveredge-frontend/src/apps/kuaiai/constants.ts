/**
 * KU-AI 前端共享常量（与后端 apps/kuaiai/constants.py 同口径）。
 */

/** 受控写 Tool 闭集五值（KR-D10）：与后端 ENABLED_TOOL_NAMES 一致 */
export const KUAI_AI_TOOL_NAMES = [
  'search_knowledge',
  'query_workorder',
  'list_workorder_tasks',
  'submit_production_feedback',
  'update_workorder_status',
] as const;

export type KuaiAiToolName = (typeof KUAI_AI_TOOL_NAMES)[number];

/** 模型目录 model_type 闭集（KR-D5） */
export const KUAI_AI_MODEL_TYPES = ['chat', 'embed', 'vision'] as const;

export type KuaiAiModelType = (typeof KUAI_AI_MODEL_TYPES)[number];

/** 下拉选项共用 QueryKey（统一前缀 ['kuaiai','options',*] 便于管理页保存后整体失效） */
export const KUAI_AI_OPTION_KEYS = {
  agents: ['kuaiai', 'options', 'agents'],
  chatModels: ['kuaiai', 'options', 'chat-models'],
  embedModels: ['kuaiai', 'options', 'embed-models'],
  knowledgeBases: ['kuaiai', 'options', 'knowledge-bases'],
  mcpServers: ['kuaiai', 'options', 'mcp-servers'],
} as const;

/** options 失效前缀：管理页新增/编辑/删除后 invalidateQueries({queryKey: KUAI_AI_OPTIONS_PREFIX}) */
export const KUAI_AI_OPTIONS_PREFIX = ['kuaiai', 'options'] as const;

/**
 * 后端 agents / llm-providers / llm-models 列表回裸数组（无 total）。
 * 满页时总数置 page*pageSize+1 诱使表格再拉一页探明；不足页时即为真实总数。
 * 副作用：恰好满页的最后一页会多出一个空页指示，点进去后自行收敛。
 */
export function bareListPageTotal(page: number, pageSize: number, count: number): number {
  return count < pageSize ? (page - 1) * pageSize + count : page * pageSize + 1;
}
