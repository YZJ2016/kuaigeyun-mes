/**
 * KU-AI Agent 授权弹窗（spec 138）。
 *
 * - 先 GET `/agents/{id}/grants` 取 {grant_mode, target_ids}；PUT 整体替换当前模式一侧名单。
 * - grant_mode=ROLE：角色多选。角色列表 `GET /core/roles` 只回 uuid/code/name，
 *   int id 逐个经 `by-code/{code}/scenarios` 解析；getRoleList 需要 system:role:read，
 *   无权限时显示提示且不影响已授权名单查看/保存（已授权 id 经 `/{id}/scenarios` 回显，
 *   失败降级为 #id）。
 * - grant_mode=USER：人员多选（display-search 搜索 / display-resolve 回显，value 为 int id）。
 * - 启用档案空名单后端 400；提交前同样校验提示。
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, App, Modal, Select, Spin, Tag } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  getAgentGrants,
  putAgentGrants,
  getRoleRefByCode,
  getRoleRefById,
  type AgentProfileOut,
} from '../../services/agents';
import { getRoleList } from '../../../../services/role';
import { resolveUserDisplay, searchUserDisplay } from '../../../../services/user';

interface OptionItem {
  value: number;
  label: string;
}

interface AgentGrantsModalProps {
  open: boolean;
  agent: AgentProfileOut | null;
  onClose: () => void;
}

export function AgentGrantsModal({ open, agent, onClose }: AgentGrantsModalProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [grantMode, setGrantMode] = useState<'ROLE' | 'USER'>('ROLE');
  const [targetIds, setTargetIds] = useState<number[]>([]);
  const [roleOptions, setRoleOptions] = useState<OptionItem[]>([]);
  const [rolesDenied, setRolesDenied] = useState(false);
  const [userOptions, setUserOptions] = useState<OptionItem[]>([]);
  const [userSearching, setUserSearching] = useState(false);
  const userSearchTimer = useRef<ReturnType<typeof setTimeout>>();

  const mergeUserOptions = useCallback((items: OptionItem[]) => {
    setUserOptions((prev) => {
      const map = new Map(prev.map((o) => [o.value, o]));
      items.forEach((o) => map.set(o.value, o));
      return Array.from(map.values());
    });
  }, []);

  const mergeRoleOptions = useCallback((items: OptionItem[]) => {
    setRoleOptions((prev) => {
      const map = new Map(prev.map((o) => [o.value, o]));
      items.forEach((o) => map.set(o.value, o));
      return Array.from(map.values());
    });
  }, []);

  /** 已授权角色 id 的名称回显（逐个 scenarios，失败降级 #id） */
  const resolveGrantedRoles = useCallback(
    async (ids: number[]) => {
      const resolved = await Promise.all(
        ids.map(async (id): Promise<OptionItem> => {
          try {
            const ref = await getRoleRefById(id);
            if (ref) return { value: ref.id, label: `${ref.name}（${ref.code}）` };
          } catch {
            /* ignore */
          }
          return { value: id, label: `#${id}` };
        }),
      );
      mergeRoleOptions(resolved);
    },
    [mergeRoleOptions],
  );

  /** 角色列表 → by-code 逐个解析 int id */
  const loadRoleOptions = useCallback(async () => {
    try {
      const res = await getRoleList({ page: 1, page_size: 100 });
      const items = res.items ?? [];
      const resolved = await Promise.all(
        items.map(async (r): Promise<OptionItem | null> => {
          try {
            const ref = await getRoleRefByCode(r.code);
            if (ref) return { value: ref.id, label: `${r.name}（${r.code}）` };
          } catch {
            /* ignore */
          }
          return null;
        }),
      );
      mergeRoleOptions(resolved.filter((o): o is OptionItem => o !== null));
    } catch {
      // 无 system:role:read 等：提示但允许继续查看/保存已授权名单
      setRolesDenied(true);
    }
  }, [mergeRoleOptions]);

  /** 已授权用户 id 的名称回显 + 首屏候选 */
  const loadUserOptions = useCallback(
    async (ids: number[]) => {
      try {
        if (ids.length > 0) {
          const resolved = await resolveUserDisplay({ user_ids: ids });
          mergeUserOptions(
            resolved.map((u) => ({
              value: u.id,
              label: u.label || u.full_name || u.username || `#${u.id}`,
            })),
          );
        }
        const res = await searchUserDisplay({ page: 1, page_size: 50 });
        mergeUserOptions(
          (res.items ?? []).map((u) => ({
            value: u.id,
            label: u.label || u.full_name || u.username || `#${u.id}`,
          })),
        );
      } catch {
        /* 候选加载失败不阻塞已授权名单 */
      }
    },
    [mergeUserOptions],
  );

  useEffect(() => {
    if (!open || !agent) return;
    setTargetIds([]);
    setRoleOptions([]);
    setUserOptions([]);
    setRolesDenied(false);
    setLoading(true);
    void (async () => {
      try {
        const grants = await getAgentGrants(agent.id);
        const mode = (grants.grant_mode || agent.grant_mode || 'ROLE').toUpperCase();
        const ids = grants.target_ids ?? [];
        setGrantMode(mode === 'USER' ? 'USER' : 'ROLE');
        setTargetIds(ids);
        if (mode === 'USER') {
          await loadUserOptions(ids);
        } else {
          await Promise.all([resolveGrantedRoles(ids), loadRoleOptions()]);
        }
      } catch (e: any) {
        message.error(
          e?.message ||
            t('app.kuaiai.agents.grantsLoadFailed', { defaultValue: '授权信息加载失败' }),
        );
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, agent?.id]);

  // 卸载/关闭时清理用户搜索防抖，避免关闭后回写已卸载组件
  useEffect(
    () => () => {
      if (userSearchTimer.current) clearTimeout(userSearchTimer.current);
    },
    [],
  );

  const handleUserSearch = (keyword: string) => {
    if (userSearchTimer.current) clearTimeout(userSearchTimer.current);
    const kw = keyword.trim();
    userSearchTimer.current = setTimeout(async () => {
      setUserSearching(true);
      try {
        const res = await searchUserDisplay({
          page: 1,
          page_size: 50,
          keyword: kw || undefined,
        });
        mergeUserOptions(
          (res.items ?? []).map((u) => ({
            value: u.id,
            label: u.label || u.full_name || u.username || `#${u.id}`,
          })),
        );
      } catch {
        /* 搜索失败保留现有候选 */
      } finally {
        setUserSearching(false);
      }
    }, 300);
  };

  const handleOk = async () => {
    if (!agent) return;
    if (agent.status === '启用' && targetIds.length === 0) {
      message.warning(
        t('app.kuaiai.agents.grantsEmptyNotAllowed', {
          defaultValue: '启用档案的授权名单不得为空，请先停用档案',
        }),
      );
      return;
    }
    setSaving(true);
    try {
      await putAgentGrants(agent.id, targetIds);
      message.success(
        t('app.kuaiai.agents.grantsSaved', { defaultValue: '授权名单已保存' }),
      );
      onClose();
    } catch (e: any) {
      message.error(
        e?.message ||
          t('app.kuaiai.agents.grantsSaveFailed', { defaultValue: '授权保存失败' }),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      title={
        agent
          ? t('app.kuaiai.agents.grantsTitle', {
              defaultValue: '授权：{{name}}',
              name: agent.name,
            })
          : t('app.kuaiai.agents.grantsTitleShort', { defaultValue: '授权' })
      }
      confirmLoading={saving}
      // 名单未加载完禁止确定：否则 targetIds 仍为初始空数组，会把已有授权静默清空
      okButtonProps={{ disabled: loading }}
      onCancel={onClose}
      onOk={() => void handleOk()}
      destroyOnHidden
    >
      <Spin spinning={loading}>
        <div style={{ marginBottom: 12 }}>
          <span style={{ marginRight: 8 }}>
            {t('app.kuaiai.agents.fieldGrantMode', { defaultValue: '授权模式' })}:
          </span>
          <Tag color={grantMode === 'ROLE' ? 'blue' : 'purple'}>
            {grantMode === 'ROLE'
              ? t('app.kuaiai.agents.grantModeRole', { defaultValue: '按角色' })
              : t('app.kuaiai.agents.grantModeUser', { defaultValue: '按人员' })}
          </Tag>
          <span style={{ color: 'rgba(0,0,0,0.45)', fontSize: 12 }}>
            {t('app.kuaiai.agents.grantsModeHint', {
              defaultValue: '授权模式在档案编辑中切换',
            })}
          </span>
        </div>
        {grantMode === 'ROLE' ? (
          <>
            {rolesDenied && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 8 }}
                message={t('app.kuaiai.agents.rolesDenied', {
                  defaultValue:
                    '无角色读取权限（system:role:read），无法加载角色候选列表；已授权角色仍会显示并可保存调整',
                })}
              />
            )}
            <Select
              mode="multiple"
              style={{ width: '100%' }}
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaiai.agents.selectRoles', {
                defaultValue: '选择可使用该档案的角色',
              })}
              value={targetIds}
              onChange={(v) => setTargetIds(v)}
              options={roleOptions}
            />
          </>
        ) : (
          <Select
            mode="multiple"
            style={{ width: '100%' }}
            showSearch
            filterOption={false}
            onSearch={handleUserSearch}
            loading={userSearching}
            placeholder={t('app.kuaiai.agents.selectUsers', {
              defaultValue: '搜索并选择可使用该档案的人员',
            })}
            value={targetIds}
            onChange={(v) => setTargetIds(v)}
            options={userOptions}
          />
        )}
      </Spin>
    </Modal>
  );
}
