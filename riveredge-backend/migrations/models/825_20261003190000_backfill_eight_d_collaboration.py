"""
未关闭 8D 报告：切换协同模式并回填当前阶段负责人。

已完成阶段正文的当前阶段记为 approved，便于沿用旧单进度继续推进；
已关闭单保持 legacy，不写入指派表。
"""

from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE "apps_kuaizhizao_quality_8d_reports" AS r
        SET "coordination_mode" = 'collaborative'
        WHERE r."deleted_at" IS NULL
          AND r."status" <> 'closed';

        INSERT INTO "apps_kuaizhizao_quality_8d_stage_assignments" (
            "uuid",
            "tenant_id",
            "created_at",
            "updated_at",
            "report_id",
            "stage_key",
            "assignee_user_id",
            "assignee_name",
            "status",
            "approved_at",
            "approved_by",
            "approved_by_name"
        )
        SELECT
            gen_random_uuid(),
            r."tenant_id",
            NOW(),
            NOW(),
            r."id",
            r."status",
            COALESCE(r."owner_id", r."created_by"),
            COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), '')),
            CASE
                WHEN r."status" = 'd0_prepare' AND length(trim(COALESCE(r."d0_prepare", ''))) > 0 THEN 'approved'
                WHEN r."status" = 'd1_team' AND length(trim(COALESCE(r."d1_team", ''))) > 0 THEN 'approved'
                WHEN r."status" = 'd2_problem' AND length(trim(COALESCE(r."d2_problem", ''))) > 0 THEN 'approved'
                WHEN r."status" = 'd3_containment' AND length(trim(COALESCE(r."d3_containment", ''))) > 0 THEN 'approved'
                WHEN r."status" = 'd4_root_cause' AND length(trim(COALESCE(r."d4_root_cause", ''))) > 0 THEN 'approved'
                WHEN r."status" = 'd5_corrective_action' AND length(trim(COALESCE(r."d5_corrective_action", ''))) > 0 THEN 'approved'
                WHEN r."status" = 'd6_implement_result' AND length(trim(COALESCE(r."d6_implement_result", ''))) > 0 THEN 'approved'
                WHEN r."status" = 'd7_prevent_recurrence' AND length(trim(COALESCE(r."d7_prevent_recurrence", ''))) > 0 THEN 'approved'
                WHEN r."status" = 'd8_team_congratulation' AND length(trim(COALESCE(r."d8_team_congratulation", ''))) > 0 THEN 'approved'
                ELSE 'in_progress'
            END,
            CASE
                WHEN r."status" = 'd0_prepare' AND length(trim(COALESCE(r."d0_prepare", ''))) > 0 THEN NOW()
                WHEN r."status" = 'd1_team' AND length(trim(COALESCE(r."d1_team", ''))) > 0 THEN NOW()
                WHEN r."status" = 'd2_problem' AND length(trim(COALESCE(r."d2_problem", ''))) > 0 THEN NOW()
                WHEN r."status" = 'd3_containment' AND length(trim(COALESCE(r."d3_containment", ''))) > 0 THEN NOW()
                WHEN r."status" = 'd4_root_cause' AND length(trim(COALESCE(r."d4_root_cause", ''))) > 0 THEN NOW()
                WHEN r."status" = 'd5_corrective_action' AND length(trim(COALESCE(r."d5_corrective_action", ''))) > 0 THEN NOW()
                WHEN r."status" = 'd6_implement_result' AND length(trim(COALESCE(r."d6_implement_result", ''))) > 0 THEN NOW()
                WHEN r."status" = 'd7_prevent_recurrence' AND length(trim(COALESCE(r."d7_prevent_recurrence", ''))) > 0 THEN NOW()
                WHEN r."status" = 'd8_team_congratulation' AND length(trim(COALESCE(r."d8_team_congratulation", ''))) > 0 THEN NOW()
                ELSE NULL
            END,
            CASE
                WHEN r."status" = 'd0_prepare' AND length(trim(COALESCE(r."d0_prepare", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                WHEN r."status" = 'd1_team' AND length(trim(COALESCE(r."d1_team", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                WHEN r."status" = 'd2_problem' AND length(trim(COALESCE(r."d2_problem", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                WHEN r."status" = 'd3_containment' AND length(trim(COALESCE(r."d3_containment", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                WHEN r."status" = 'd4_root_cause' AND length(trim(COALESCE(r."d4_root_cause", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                WHEN r."status" = 'd5_corrective_action' AND length(trim(COALESCE(r."d5_corrective_action", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                WHEN r."status" = 'd6_implement_result' AND length(trim(COALESCE(r."d6_implement_result", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                WHEN r."status" = 'd7_prevent_recurrence' AND length(trim(COALESCE(r."d7_prevent_recurrence", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                WHEN r."status" = 'd8_team_congratulation' AND length(trim(COALESCE(r."d8_team_congratulation", ''))) > 0 THEN COALESCE(r."owner_id", r."created_by")
                ELSE NULL
            END,
            CASE
                WHEN r."status" = 'd0_prepare' AND length(trim(COALESCE(r."d0_prepare", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                WHEN r."status" = 'd1_team' AND length(trim(COALESCE(r."d1_team", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                WHEN r."status" = 'd2_problem' AND length(trim(COALESCE(r."d2_problem", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                WHEN r."status" = 'd3_containment' AND length(trim(COALESCE(r."d3_containment", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                WHEN r."status" = 'd4_root_cause' AND length(trim(COALESCE(r."d4_root_cause", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                WHEN r."status" = 'd5_corrective_action' AND length(trim(COALESCE(r."d5_corrective_action", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                WHEN r."status" = 'd6_implement_result' AND length(trim(COALESCE(r."d6_implement_result", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                WHEN r."status" = 'd7_prevent_recurrence' AND length(trim(COALESCE(r."d7_prevent_recurrence", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                WHEN r."status" = 'd8_team_congratulation' AND length(trim(COALESCE(r."d8_team_congratulation", ''))) > 0 THEN COALESCE(NULLIF(trim(r."owner_name"), ''), NULLIF(trim(r."created_by_name"), ''))
                ELSE NULL
            END
        FROM "apps_kuaizhizao_quality_8d_reports" AS r
        WHERE r."deleted_at" IS NULL
          AND r."status" <> 'closed'
          AND NOT EXISTS (
            SELECT 1
            FROM "apps_kuaizhizao_quality_8d_stage_assignments" AS a
            WHERE a."tenant_id" = r."tenant_id"
              AND a."report_id" = r."id"
              AND a."stage_key" = r."status"
          );
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return "-- noop: 8D collaboration backfill is irreversible"
