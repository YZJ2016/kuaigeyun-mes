"""定制应用可见性：全局未绑定则全员可见。"""

from core.services.application.application_dedicated_binding_service import (
    ApplicationDedicatedBindingService,
)


def test_unbound_globally_visible_to_all_tenants():
    assert ApplicationDedicatedBindingService.is_dedicated_visible_to_tenant(
        "funide-oa",
        tenant_bound_codes=set(),
        globally_bound_codes=set(),
    )


def test_bound_globally_only_bound_tenant_sees():
    globally = {"haoligo"}
    assert ApplicationDedicatedBindingService.is_dedicated_visible_to_tenant(
        "haoligo",
        tenant_bound_codes={"haoligo"},
        globally_bound_codes=globally,
    )
    assert not ApplicationDedicatedBindingService.is_dedicated_visible_to_tenant(
        "haoligo",
        tenant_bound_codes=set(),
        globally_bound_codes=globally,
    )


def test_other_app_not_affected_when_one_app_bound():
    globally = {"haoligo"}
    assert ApplicationDedicatedBindingService.is_dedicated_visible_to_tenant(
        "funide-oa",
        tenant_bound_codes=set(),
        globally_bound_codes=globally,
    )
