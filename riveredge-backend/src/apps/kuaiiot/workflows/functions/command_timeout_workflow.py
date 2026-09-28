"""已下发且超过 expires_at 的指令改为 timeout。不改 success 或 failed。"""

from apps.kuaiiot.services.command_service import timeout_sent_commands


async def run_kuaiiot_command_timeout_check() -> dict:
    count = await timeout_sent_commands()
    return {"commands_timed_out": count}
