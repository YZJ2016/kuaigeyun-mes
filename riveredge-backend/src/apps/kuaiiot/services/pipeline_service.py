"""快数采链路拓扑。"""

from __future__ import annotations

from apps.kuaizhizao.models.equipment import Equipment
from apps.kuaiiot.models.iot import IotAlert, IotConnection, IotDevice, IotTagDefinition
from apps.kuaiiot.schemas.iot import PipelineEdgeResponse, PipelineGraphResponse, PipelineNodeResponse


class PipelineService:
    @staticmethod
    async def build_graph(tenant_id: int) -> PipelineGraphResponse:
        connections = await IotConnection.filter(tenant_id=tenant_id, deleted_at__isnull=True).order_by("name")
        devices = await IotDevice.filter(tenant_id=tenant_id, deleted_at__isnull=True).order_by("name")
        tags = await IotTagDefinition.filter(tenant_id=tenant_id, deleted_at__isnull=True).order_by("device_id", "tag_key")
        open_alerts = await IotAlert.filter(tenant_id=tenant_id, status="open", deleted_at__isnull=True).count()

        conn_map = {item.id: item for item in connections}
        equipment_uuids = [item.equipment_uuid for item in devices if item.equipment_uuid]
        equipment_map: dict[str, Equipment] = {}
        if equipment_uuids:
            rows = await Equipment.filter(
                tenant_id=tenant_id,
                uuid__in=list(set(equipment_uuids)),
                deleted_at__isnull=True,
            )
            equipment_map = {item.uuid: item for item in rows}

        nodes: list[PipelineNodeResponse] = []
        edges: list[PipelineEdgeResponse] = []

        for connection in connections:
            nodes.append(
                PipelineNodeResponse(
                    id=f"connection:{connection.uuid}",
                    node_type="connection",
                    label=connection.name,
                    status=connection.health_status,
                    meta={
                        "connection_type": connection.connection_type,
                        "is_enabled": connection.is_enabled,
                    },
                )
            )

        for device in devices:
            connection = conn_map.get(device.connection_id) if device.connection_id else None
            nodes.append(
                PipelineNodeResponse(
                    id=f"device:{device.uuid}",
                    node_type="device",
                    label=device.name,
                    status="online" if device.is_online else "offline",
                    meta={
                        "code": device.code,
                        "equipment_uuid": device.equipment_uuid,
                        "last_seen_at": device.last_seen_at,
                    },
                )
            )
            if connection:
                edges.append(
                    PipelineEdgeResponse(
                        source=f"connection:{connection.uuid}",
                        target=f"device:{device.uuid}",
                        edge_type="ingress",
                    )
                )
            if device.equipment_uuid:
                mes_node_id = f"equipment:{device.equipment_uuid}"
                if not any(node.id == mes_node_id for node in nodes):
                    equipment = equipment_map.get(device.equipment_uuid)
                    eq_name = (equipment.name or "").strip() if equipment else ""
                    eq_code = (equipment.code or "").strip() if equipment else ""
                    if eq_name and eq_code:
                        eq_label = f"{eq_name} / {eq_code}"
                    else:
                        eq_label = eq_name or eq_code or device.equipment_uuid
                    nodes.append(
                        PipelineNodeResponse(
                            id=mes_node_id,
                            node_type="equipment",
                            label=eq_label,
                            status="bound",
                            meta={
                                "equipment_uuid": device.equipment_uuid,
                                "name": eq_name or None,
                                "code": eq_code or None,
                            },
                        )
                    )
                edges.append(
                    PipelineEdgeResponse(
                        source=f"device:{device.uuid}",
                        target=mes_node_id,
                        edge_type="mes_sync",
                    )
                )

        for tag in tags:
            device = next((item for item in devices if item.id == tag.device_id), None)
            if not device:
                continue
            tag_name = (tag.name or "").strip() or tag.tag_key
            tag_node_id = f"tag:{device.uuid}:{tag.tag_key}"
            nodes.append(
                PipelineNodeResponse(
                    id=tag_node_id,
                    node_type="tag",
                    label=f"{tag_name} / {tag.tag_key}" if tag_name != tag.tag_key else tag.tag_key,
                    status="enabled" if tag.is_enabled else "disabled",
                    meta={
                        "tag_key": tag.tag_key,
                        "name": tag_name,
                        "map_target": tag.map_target,
                        "fill_target": tag.fill_target,
                        "value_type": tag.value_type,
                    },
                )
            )
            edges.append(
                PipelineEdgeResponse(
                    source=f"device:{device.uuid}",
                    target=tag_node_id,
                    edge_type="mapping",
                )
            )

        summary = {
            "connections": len(connections),
            "devices": len(devices),
            "tags": len(tags),
            "bound_devices": sum(1 for item in devices if item.equipment_uuid),
            "open_alerts": open_alerts,
        }
        return PipelineGraphResponse(nodes=nodes, edges=edges, summary=summary)
