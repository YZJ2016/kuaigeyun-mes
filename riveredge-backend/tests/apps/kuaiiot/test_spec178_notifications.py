from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from core.services.business import business_notification_service as service
from core.models.message_log import MessageLog


@pytest.mark.asyncio
async def test_partial_retry_skips_only_successful_recipient_and_same_rule(monkeypatch):
    rules = [{'id': name, 'trigger_document': 'kuaiiot_alert', 'trigger_action': 'raised', 'template_code': name} for name in ['first', 'second']]
    monkeypatch.setattr(service.BusinessConfigService, 'get_business_config', AsyncMock(return_value={'parameters': {'notifications': {'rules': rules}}}))
    monkeypatch.setattr(service.BusinessNotificationService, '_resolve_recipient_ids', AsyncMock(return_value=[1, 2]))
    monkeypatch.setattr(service.BusinessNotificationService, '_resolve_channels', AsyncMock(return_value=[{'type': 'internal', 'config_uuid': None}]))
    monkeypatch.setattr(service.BusinessNotificationService, '_load_user_contacts', AsyncMock(return_value={}))
    saved = []
    def query(**kwargs):
        return SimpleNamespace(all=AsyncMock(return_value=[r for recipient, r in saved if recipient == kwargs['recipient']]))
    monkeypatch.setattr(MessageLog, 'filter', query)
    failed = False
    requests = []
    async def send(tenant, request):
        nonlocal failed
        requests.append((request.recipient, request.template_code))
        if request.recipient == '2' and not failed:
            failed = True
            return SimpleNamespace(success=False, error='temporary')
        saved.append((request.recipient, SimpleNamespace(variables=request.variables)))
        return SimpleNamespace(success=True)
    monkeypatch.setattr(service.MessageService, 'send_message', send)
    args = dict(trigger_document='kuaiiot_alert', trigger_action='raised', context={'entity_id': 1, 'reliable_delivery': True})
    with pytest.raises(RuntimeError):
        await service.BusinessNotificationService.dispatch(1, **args)
    assert await service.BusinessNotificationService.dispatch(1, **args) == 4
    assert requests.count(('1', 'first')) == 1
    assert requests.count(('1', 'second')) == 1
    assert requests.count(('2', 'first')) == 2
    assert requests.count(('2', 'second')) == 1
