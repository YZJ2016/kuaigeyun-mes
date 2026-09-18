/**
 * 工序卡浮窗：与质检概览同一套 Tooltip 内容（只用工序接口已返回字段，禁止另拉接口）。
 */
import React from 'react';
import { useTranslation } from 'react-i18next';

function pickText(operation: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const raw = operation[key];
    if (raw == null) continue;
    const text = String(raw).trim();
    if (text) return text;
  }
  return '';
}

function pickStringList(operation: Record<string, unknown>, ...keys: string[]): string[] {
  for (const key of keys) {
    const raw = operation[key];
    if (!Array.isArray(raw)) continue;
    return raw.map((item) => String(item ?? '').trim()).filter(Boolean);
  }
  return [];
}

/** 与工位终端 / 移动端暂停弹窗、后端 DOWNTIME_REASON_LABELS 对齐 */
const PAUSE_REASON_LABELS: Record<string, string> = {
  material_shortage: '缺料',
  material_wait: '待料',
  equipment_fault: '设备故障',
  tool_change: '换刀/换模',
  quality_issue: '质量异常',
  break: '休息',
  other: '其他',
};

function resolvePausePresetReason(operation: Record<string, unknown>): string {
  const code = pickText(operation, 'pause_reason_code', 'pauseReasonCode');
  const stored = pickText(operation, 'pause_reason_label', 'pauseReasonLabel');
  const fromCode = code ? PAUSE_REASON_LABELS[code] : '';
  if (fromCode) return fromCode;
  if (stored && PAUSE_REASON_LABELS[stored]) return PAUSE_REASON_LABELS[stored];
  if (stored && stored !== code) return stored;
  const remarks = pickText(operation, 'pause_reason_remarks', 'pauseReasonRemarks');
  const presetLabels = new Set(Object.values(PAUSE_REASON_LABELS));
  if (remarks && presetLabels.has(remarks)) return remarks;
  return stored;
}

function OverviewRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 8, lineHeight: 1.5, marginBottom: 4 }}>
      <span style={{ flexShrink: 0, opacity: 0.85 }}>{label}</span>
      <span style={{ minWidth: 0, wordBreak: 'break-word' }}>{value}</span>
    </div>
  );
}

function OverviewShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ maxWidth: 280, padding: '2px 0' }}>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}

export function isOperationAssignedWorkGroup(operation?: Record<string, unknown> | null): boolean {
  const row = (operation ?? {}) as Record<string, unknown>;
  if (pickText(row, 'assigned_worker_name', 'assignedWorkerName')) return false;
  const teamId = Number(row.assigned_team_id ?? row.assignedTeamId);
  if (Number.isInteger(teamId) && teamId > 0) return true;
  return Boolean(pickText(row, 'assigned_team_name', 'assignedTeamName'));
}

export const OperationPauseOverviewTooltip: React.FC<{
  operation: Record<string, unknown> | null | undefined;
}> = ({ operation }) => {
  const { t } = useTranslation();
  const row = (operation ?? {}) as Record<string, unknown>;
  const reason = resolvePausePresetReason(row);
  const remarks = pickText(row, 'pause_reason_remarks', 'pauseReasonRemarks');
  const extraRemarks = remarks && remarks !== reason ? remarks : '';

  return (
    <OverviewShell title={t('app.kuaizhizao.workOrder.opCard.pauseOverview.title')}>
      <OverviewRow
        label={t('app.kuaizhizao.workOrder.opCard.pauseOverview.reason')}
        value={reason || t('app.kuaizhizao.workOrder.opCard.pauseOverview.empty')}
      />
      {extraRemarks ? (
        <OverviewRow
          label={t('app.kuaizhizao.workOrder.opCard.pauseOverview.remarks')}
          value={extraRemarks}
        />
      ) : null}
    </OverviewShell>
  );
};

export const OperationTeamMembersTooltip: React.FC<{
  operation: Record<string, unknown> | null | undefined;
}> = ({ operation }) => {
  const { t } = useTranslation();
  const row = (operation ?? {}) as Record<string, unknown>;
  const teamName = pickText(row, 'assigned_team_name', 'assignedTeamName');
  const members = pickStringList(row, 'assigned_team_member_names', 'assignedTeamMemberNames');

  return (
    <OverviewShell title={t('app.kuaizhizao.workOrder.opCard.teamMembers.title')}>
      {teamName ? (
        <OverviewRow
          label={t('app.kuaizhizao.workOrder.opCard.teamMembers.group')}
          value={teamName}
        />
      ) : null}
      <OverviewRow
        label={t('app.kuaizhizao.workOrder.opCard.teamMembers.members')}
        value={
          members.length > 0 ? (
            <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 2 }}>
              {members.map((name, index) => (
                <span key={`${name}-${index}`}>{name}</span>
              ))}
            </span>
          ) : (
            t('app.kuaizhizao.workOrder.opCard.teamMembers.empty')
          )
        }
      />
    </OverviewShell>
  );
};
