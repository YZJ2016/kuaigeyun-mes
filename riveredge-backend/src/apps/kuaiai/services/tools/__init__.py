"""KU-AI 场景 Tool 适配层（spec 195–218 按领域分文件）。

各模块 handler 约定与 ``scene_tools`` 相同：``async def handler(**args) -> str``，
签名声明 ``ctx`` 形参由 tool_bridge 补传 ``AiRuntimeContext``；闭集参数、
limit≤20、有界摘要、空结果真实文案、底层异常固定错误文案（失败关闭）。
"""
