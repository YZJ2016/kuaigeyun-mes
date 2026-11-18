/**
 * 统一外推批次面板（标准形态以工单推送为准）：
 * UniPullQueryModal 多选候选 → profile 多选 →（金蝶）连接器/Save 接口 → 预览 dry-run → /document-push。
 * SyncPushHub 内嵌时设 embedded。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, App, Button, Checkbox, Empty, Flex, Modal, Select, Space, Table, Typography } from 'antd';
import {
  DeleteOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  UniPullQueryModal,
  useUniPullQuery,
} from '../../../components/uni-pull-query';
import {
  getApplicationConnectionListAll,
  type ApplicationConnection,
} from '../../../services/applicationConnection';
import type { API } from '../../../services/apiManagement';
import { loadAllActiveApis, sortApisByPreferredHints } from '../../../utils/activeApiSelectOptions';
import { ThemedSegmented } from '../../../components/themed-segmented/ThemedSegmented';
import { getDataSourceListAllMatching, type DataSource } from '../../../services/dataSource';
import { getDatasetList, type Dataset } from '../../../services/dataset';
import {
  filterProfilesForSource,
  listDocumentPushProfiles,
  pushDocumentExternal,
} from '../services/document-push';
import { getApiErrorMessage } from '../../../utils/errorHandler';

export const DOCUMENT_PUSH_PROFILE_LABEL_KEYS: Record<string, string> = {
  kingdee_prd_mo: 'app.kuaizhizao.documentPush.profile.kingdee_prd_mo',
  oa_http_webhook: 'app.kuaizhizao.documentPush.profile.oa_http_webhook',
  feishu_im_notify: 'app.kuaizhizao.documentPush.profile.feishu_im_notify',
  kingdee_prd_morpt: 'app.kuaizhizao.documentPush.profile.kingdee_prd_morpt',
  kingdee_sal_saleorder: 'app.kuaizhizao.documentPush.profile.kingdee_sal_saleorder',
  kingdee_pur_purchaseorder: 'app.kuaizhizao.documentPush.profile.kingdee_pur_purchaseorder',
  kingdee_im_purinbill: 'app.kuaizhizao.documentPush.profile.kingdee_im_purinbill',
  kingdee_im_saloutbill: 'app.kuaizhizao.documentPush.profile.kingdee_im_saloutbill',
  kingdee_im_otheroutbill: 'app.kuaizhizao.documentPush.profile.kingdee_im_otheroutbill',
  kingdee_im_otherinbill: 'app.kuaizhizao.documentPush.profile.kingdee_im_otherinbill',
  kingdee_im_surplusbill: 'app.kuaizhizao.documentPush.profile.kingdee_im_surplusbill',
  kingdee_im_deficitbill: 'app.kuaizhizao.documentPush.profile.kingdee_im_deficitbill',
  kingdee_stk_miscellaneous: 'app.kuaizhizao.documentPush.profile.kingdee_stk_miscellaneous',
  kingdee_bd_material: 'app.kuaizhizao.documentPush.profile.kingdee_bd_material',
  kingdee_eng_bom: 'app.kuaizhizao.documentPush.profile.kingdee_eng_bom',
  kingdee_eng_process: 'app.kuaizhizao.documentPush.profile.kingdee_eng_process',
};

export interface DocumentPushBindActionOption {
  label: string;
  value: string;
  /** action_apis 槽位；默认 [value]。撤回入库须 withdraw + unsubmit */
  apiKeys?: string[];
}

export interface DocumentPushTargetBinding {
  connection_code?: string;
  save_api_uuid?: string;
  target_profile: string;
  push_mode?: 'auto' | 'manual';
  trigger_actions?: string[];
  action_apis?: Record<string, string>;
  destination_kind?: 'api' | 'data_source';
  data_source_uuid?: string;
  dataset_uuid?: string;
  /** 仅点过确认保存的目标。缺省的历史行不展示。 */
  user_saved?: boolean;
  /** 是否推送；关闭后自动外推/列表推送按钮/详情外推记录均关闭。缺省 true。 */
  push_enabled?: boolean;
}

export interface DocumentPushBindingState {
  targets?: DocumentPushTargetBinding[];
  /** 已保存过出站目标（含空列表）。未点确认的目标不展示。 */
  targets_configured?: boolean;
  trigger_actions?: string[];
  connection_code?: string;
  save_api_uuid?: string;
  sync_mode?: string;
  schedule_interval_minutes?: number;
}

export interface DocumentPushBatchPanelProps<T extends { id: number }> {
  open: boolean;
  onClose: () => void;
  onComplete?: () => void;
  embedded?: boolean;
  preferIds?: number[];
  sourceType: string;
  /**
   * 偏好勾选（与 GET /document-push/profiles ∩ source 求交）。
   * 空数组 = 该 source 接口返回的全部已知 profile 作为默认；禁止写死「仅金蝶」。
   */
  defaultProfiles?: string[];
  /** 勾选后需要金蝶连接器 + Save 接口的 profile */
  kingdeeProfiles?: string[];
  title: string;
  hint: string;
  pipelineDesc: string;
  searchPlaceholder: string;
  needSelectMessage: string;
  confirmText?: string;
  columns: TableColumnsType<T>;
  getRowLabel: (row: T) => string;
  loadCandidates: (params: {
    keyword: string;
    page: number;
    pageSize: number;
    preferIds: number[];
  }) => Promise<{ data: T[]; total: number }>;
  /** @deprecated 不再用于过滤下拉；写入接口列表与 sync-from-source 相同（全部启用接口，saveApiSearchHints 仅排序）。 */
  matchSaveApi?: (api: API, connection: ApplicationConnection) => boolean;
  /** multiApiTargetRows 时按「接口用途」过滤下拉（如 withdraw 仅 batchUnaudit） */
  matchBindingApi?: (
    slot: string,
    api: API,
    connection: ApplicationConnection | undefined,
  ) => boolean;
  preferSaveApi?: (items: API[]) => string | undefined;
  /** 多金蝶目标时按 profile 解析各自写入接口；缺省回落 preferSaveApi / 当前选中 */
  resolveSaveApiForProfile?: (profile: string, items: API[]) => string | undefined;
  saveApiSearchHints?: string[];
  loadBinding?: () => Promise<DocumentPushBindingState | null | undefined>;
  saveBinding?: (payload: DocumentPushBindingState) => Promise<unknown>;
  /** 自动推送时可选的触发动作；缺省为提交/审核 */
  bindActionOptions?: DocumentPushBindActionOption[];
  /** 为 true 时每个绑定按钮单独选接口（写入 action_apis） */
  perActionApiBinding?: boolean;
  /**
   * 列表每行一条数据接口（原交互）；可重复添加同一 target_profile。
   * 落库时每行一条 target，action_apis 仅含该行接口用途单键。
   */
  multiApiTargetRows?: boolean;
  /** multiApiTargetRows 时「接口用途」下拉选项（如 confirm / withdraw） */
  apiBindingSlotOptions?: Array<{ label: string; value: string }>;
  resolveActionApiUuid?: (slot: string, items: API[]) => string | undefined;
  showScheduleControls?: boolean;
  successCountKey?: string;
  partialCountKey?: string;
  failedTitleKey?: string;
  skippedHintKey?: string;
}

function defaultPreferSaveApi(items: API[]): string | undefined {
  return items[0]?.uuid;
}

const EMPTY_STRING_ARRAY: string[] = [];

function createBindingRowKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `bind-row-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

function triggerActionsForBindingSlot(slot: string): string[] {
  const key = String(slot || '').trim();
  if (key === 'confirm') return ['confirm'];
  if (key === 'update') return ['update'];
  if (key === 'delete') return ['delete'];
  if (key === 'withdraw' || key === 'unsubmit') return ['withdraw'];
  return [];
}

function expandBindingTargetsToRowDrafts(targets: DocumentPushTargetBinding[]): Array<{
  rowKey: string;
  profile: string;
  apiSlot: string;
  target: DocumentPushTargetBinding;
}> {
  const out: Array<{
    rowKey: string;
    profile: string;
    apiSlot: string;
    target: DocumentPushTargetBinding;
  }> = [];
  for (const target of targets) {
    const profile = String(target.target_profile || '').trim();
    if (!profile) continue;
    const actionApis = target.action_apis;
    if (actionApis && Object.keys(actionApis).length > 0) {
      for (const [slot, uuid] of Object.entries(actionApis)) {
        const apiSlot = String(slot || '').trim();
        const apiUuid = String(uuid || '').trim();
        if (!apiSlot || !apiUuid) continue;
        out.push({
          rowKey: createBindingRowKey(),
          profile,
          apiSlot,
          target: { ...target, save_api_uuid: apiUuid },
        });
      }
    } else if (target.save_api_uuid) {
      out.push({
        rowKey: createBindingRowKey(),
        profile,
        apiSlot: 'confirm',
        target,
      });
    }
  }
  return out;
}

export function DocumentPushBatchPanel<T extends { id: number }>({
  open,
  onClose,
  onComplete,
  embedded = false,
  preferIds,
  sourceType,
  defaultProfiles = EMPTY_STRING_ARRAY,
  kingdeeProfiles = EMPTY_STRING_ARRAY,
  title,
  hint,
  searchPlaceholder,
  needSelectMessage,
  confirmText,
  columns,
  getRowLabel,
  loadCandidates,
  matchBindingApi,
  preferSaveApi = defaultPreferSaveApi,
  resolveSaveApiForProfile,
  saveApiSearchHints = EMPTY_STRING_ARRAY,
  loadBinding,
  saveBinding,
  bindActionOptions,
  perActionApiBinding = false,
  multiApiTargetRows = false,
  apiBindingSlotOptions,
  resolveActionApiUuid,
  successCountKey = 'app.kuaizhizao.documentPush.batch.success',
  partialCountKey = 'app.kuaizhizao.documentPush.batch.partial',
  failedTitleKey = 'app.kuaizhizao.documentPush.pushFailed',
  skippedHintKey = 'app.kuaizhizao.documentPush.batch.skippedHint',
}: DocumentPushBatchPanelProps<T>): React.ReactElement | null {
  // 关闭态直接不渲染：hooks 仍执行，但下方网络 effect 均以 open 门控
  // （embedded Hub 在 push Tab 未激活时由上层不挂载本组件）
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const resolvedBindActionOptions = useMemo(
    () =>
      bindActionOptions?.length
        ? bindActionOptions
        : [
            { label: t('permission.action.submit'), value: 'submit' },
            { label: t('permission.action.approve'), value: 'approve' },
          ],
    [bindActionOptions, t],
  );
  /** 自动推送默认勾选全部绑定按钮（如确认入库），避免空 trigger_actions 导致无感外推永不触发 */
  const defaultAutoBindActions = useMemo(
    () => resolvedBindActionOptions.map((option) => String(option.value)).filter(Boolean),
    [resolvedBindActionOptions],
  );
  const confirmSlotLabel = useMemo(() => {
    // multiApi 行展示/下拉默认「确认*」须跟单据方向走，禁止出库页回落到入库文案
    if (sourceType === 'production_picking') {
      return t('app.kuaizhizao.warehouseOutbound.action.confirmPicking');
    }
    if (
      sourceType === 'sales_delivery' ||
      sourceType === 'other_outbound' ||
      sourceType === 'material_borrow'
    ) {
      return t('app.kuaizhizao.warehouseOutbound.action.confirmOutbound');
    }
    return t('app.kuaizhizao.documentPush.batch.bindBehavior.confirm');
  }, [sourceType, t]);

  const resolvedApiBindingSlotOptions = useMemo(
    () => {
      if (apiBindingSlotOptions?.length) return apiBindingSlotOptions;
      if (bindActionOptions?.length) {
        const mapped = bindActionOptions.map((option) => ({
          // confirm 文案一律跟 sourceType，避免页面误传「确认入库」到出库单
          label: option.value === 'confirm' ? confirmSlotLabel : option.label,
          value: option.value,
        }));
        // 落库 action_apis 可能拆出 unsubmit 行；选项里没有时补上，避免回落成错误通用文案
        if (!mapped.some((option) => option.value === 'unsubmit')) {
          mapped.push({
            label: t('app.kuaizhizao.documentPush.batch.bindBehavior.unsubmit'),
            value: 'unsubmit',
          });
        }
        return mapped;
      }
      return [
        { label: confirmSlotLabel, value: 'confirm' },
        { label: t('app.kuaizhizao.documentPush.batch.actionApi.update'), value: 'update' },
        { label: t('app.kuaizhizao.documentPush.batch.actionApi.withdraw'), value: 'withdraw' },
        { label: t('app.kuaizhizao.documentPush.batch.actionApi.unsubmit'), value: 'unsubmit' },
        { label: t('app.kuaizhizao.documentPush.batch.actionApi.delete'), value: 'delete' },
      ];
    },
    [apiBindingSlotOptions, bindActionOptions, confirmSlotLabel, t],
  );

  const bindingSlotLabel = useCallback(
    (slot: string) => {
      const key = String(slot || '').trim();
      const fromOptions = resolvedApiBindingSlotOptions.find((option) => option.value === key)?.label;
      if (fromOptions) return fromOptions;
      if (key === 'confirm') return confirmSlotLabel;
      const i18nKey = `app.kuaizhizao.documentPush.batch.bindBehavior.${key}`;
      const translated = t(i18nKey);
      if (translated !== i18nKey) return translated;
      return key || '—';
    },
    [confirmSlotLabel, resolvedApiBindingSlotOptions, t],
  );
  const [connectors, setConnectors] = useState<ApplicationConnection[]>([]);
  const [connectionCode, setConnectionCode] = useState<string | undefined>();
  const [saveApis, setSaveApis] = useState<API[]>([]);
  const [saveApiUuid, setSaveApiUuid] = useState<string | undefined>();
  /** 按目标记住写入接口；列表名称与落库均优先用它，避免只显示 profile 文案或被 prefer 冲掉 */
  const [saveApiUuids, setSaveApiUuids] = useState<Record<string, string | undefined>>({});
  const [syncMode, setSyncMode] = useState<string>('manual_full');
  const [targetModes, setTargetModes] = useState<Record<string, 'auto' | 'manual'>>({});
  const [targetPushEnabled, setTargetPushEnabled] = useState<Record<string, boolean>>({});
  const [targetActionMap, setTargetActionMap] = useState<Record<string, string[]>>({});
  const [targetActionApiMap, setTargetActionApiMap] = useState<
    Record<string, Record<string, string | undefined>>
  >({});
  const [destinationKinds, setDestinationKinds] = useState<Record<string, 'api' | 'data_source'>>({});
  const [dataSourceUuids, setDataSourceUuids] = useState<Record<string, string | undefined>>({});
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(false);
  const [datasetUuids, setDatasetUuids] = useState<Record<string, string | undefined>>({});
  const [writeDatasets, setWriteDatasets] = useState<Dataset[]>([]);
  const [rememberBinding, setRememberBinding] = useState(true);
  /** 暂停自动无感外推（push_enabled=false）；手动勾选推送仍可用 */
  const [autoPushPaused, setAutoPushPaused] = useState(false);
  const [autoPushPauseLoading, setAutoPushPauseLoading] = useState(false);
  const [settingProfile, setSettingProfile] = useState<string | null>(null);
  const [scheduleIntervalMinutes, setScheduleIntervalMinutes] = useState<number>(15);
  const [connectorsLoading, setConnectorsLoading] = useState(false);
  const [apisLoading, setApisLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [profilesLoaded, setProfilesLoaded] = useState(false);
  const [targetProfiles, setTargetProfiles] = useState<string[]>([]);
  const [targetRowKeys, setTargetRowKeys] = useState<string[]>([]);
  const [rowBindingMeta, setRowBindingMeta] = useState<
    Record<string, { profile: string; apiSlot: string }>
  >({});
  const [profileOptions, setProfileOptions] = useState<Array<{ label: string; value: string }>>([]);
  const preferIdsRef = useRef<number[]>([]);
  const prefilledRef = useRef(false);
  /** 添加目标：保存前只在设置弹窗，不进列表（对齐入站 pendingNewSourceDraft） */
  const [pendingNewProfile, setPendingNewProfile] = useState<string | null>(null);
  const connectionCodeRef = useRef<string | undefined>();
  const saveApiUuidRef = useRef<string | undefined>();
  const saveApiUuidsRef = useRef<Record<string, string | undefined>>({});
  const syncModeRef = useRef('manual_full');
  const settingSnapshotRef = useRef<{
    connection?: string;
    api?: string;
    mode: 'auto' | 'manual';
    actions: string[];
    destination: 'api' | 'data_source';
    dataSourceUuid?: string;
  } | null>(null);
  const scheduleIntervalRef = useRef(15);
  const rememberBindingRef = useRef(true);
  const targetModesRef = useRef<Record<string, 'auto' | 'manual'>>({});
  const destinationKindsRef = useRef<Record<string, 'api' | 'data_source'>>({});
  const dataSourceUuidsRef = useRef<Record<string, string | undefined>>({});
  const datasetUuidsRef = useRef<Record<string, string | undefined>>({});
  const targetActionMapRef = useRef<Record<string, string[]>>({});
  const targetPushEnabledRef = useRef<Record<string, boolean>>({});
  const targetActionApiMapRef = useRef<Record<string, Record<string, string | undefined>>>({});
  const perActionApiBindingRef = useRef(perActionApiBinding);
  const multiApiTargetRowsRef = useRef(multiApiTargetRows);
  const rowBindingMetaRef = useRef(rowBindingMeta);
  const resolveActionApiUuidRef = useRef(resolveActionApiUuid);
  const pushOnlyProfileRef = useRef<string | null>(null);
  const settingProfileRef = useRef<string | null>(null);
  const targetProfilesRef = useRef<string[]>([]);
  const profileOptionsRef = useRef<Array<{ label: string; value: string }>>([]);
  const saveApisRef = useRef<API[]>([]);
  const resolveSaveApiForProfileRef = useRef(resolveSaveApiForProfile);
  connectionCodeRef.current = connectionCode;
  saveApiUuidRef.current = saveApiUuid;
  saveApiUuidsRef.current = saveApiUuids;
  syncModeRef.current = syncMode;
  scheduleIntervalRef.current = scheduleIntervalMinutes;
  rememberBindingRef.current = rememberBinding;
  targetModesRef.current = targetModes;
  destinationKindsRef.current = destinationKinds;
  dataSourceUuidsRef.current = dataSourceUuids;
  datasetUuidsRef.current = datasetUuids;
  targetActionMapRef.current = targetActionMap;
  targetPushEnabledRef.current = targetPushEnabled;
  targetActionApiMapRef.current = targetActionApiMap;
  perActionApiBindingRef.current = perActionApiBinding;
  multiApiTargetRowsRef.current = multiApiTargetRows;
  rowBindingMetaRef.current = rowBindingMeta;
  resolveActionApiUuidRef.current = resolveActionApiUuid;
  targetProfilesRef.current = multiApiTargetRows ? targetRowKeys : targetProfiles;
  profileOptionsRef.current = profileOptions;
  saveApisRef.current = saveApis;
  resolveSaveApiForProfileRef.current = resolveSaveApiForProfile;

  const listBindingKeys = multiApiTargetRows ? targetRowKeys : targetProfiles;
  const profileForBindingKey = useCallback(
    (key: string) => {
      if (multiApiTargetRowsRef.current) {
        return String(rowBindingMetaRef.current[key]?.profile || '').trim();
      }
      return key;
    },
    [],
  );
  const apiSlotForBindingKey = useCallback((key: string) => {
    if (!multiApiTargetRowsRef.current) return 'confirm';
    return String(rowBindingMetaRef.current[key]?.apiSlot || 'confirm').trim() || 'confirm';
  }, []);

  const apiKeysForBindAction = useCallback(
    (actionValue: string) => {
      const opt = resolvedBindActionOptions.find((row) => row.value === actionValue);
      const keys = opt?.apiKeys?.length ? opt.apiKeys : [actionValue];
      return keys.map((key) => String(key).trim()).filter(Boolean);
    },
    [resolvedBindActionOptions],
  );
  const requiredApiSlotsForProfile = useCallback(
    (profile: string, actions?: string[]) => {
      const selected =
        actions ??
        targetActionMapRef.current[profile] ??
        (perActionApiBindingRef.current ? defaultAutoBindActions : []);
      const slots = new Set<string>();
      for (const action of selected) {
        for (const key of apiKeysForBindAction(action)) {
          slots.add(key);
        }
      }
      return [...slots];
    },
    [apiKeysForBindAction, defaultAutoBindActions],
  );
  const buildActionApisForProfile = useCallback(
    (profile: string, actions: string[]) => {
      const map = targetActionApiMapRef.current[profile] || {};
      const out: Record<string, string> = {};
      for (const slot of requiredApiSlotsForProfile(profile, actions)) {
        const uuid = String(map[slot] || '').trim();
        if (uuid) out[slot] = uuid;
      }
      return Object.keys(out).length ? out : undefined;
    },
    [requiredApiSlotsForProfile],
  );

  const effectiveBindActionsForProfile = useCallback(
    (profile: string) => {
      if (Object.prototype.hasOwnProperty.call(targetActionMapRef.current, profile)) {
        return targetActionMapRef.current[profile] ?? [];
      }
      if (perActionApiBindingRef.current && (targetModesRef.current[profile] ?? 'auto') === 'auto') {
        return defaultAutoBindActions;
      }
      return [];
    },
    [defaultAutoBindActions],
  );

  const seedActionApisForProfile = useCallback(
    (profile: string, actions: string[]) => {
      if (!perActionApiBindingRef.current) return;
      setTargetActionApiMap((prev) => {
        const row = { ...(prev[profile] || {}) };
        let changed = false;
        for (const slot of requiredApiSlotsForProfile(profile, actions)) {
          if (String(row[slot] || '').trim()) continue;
          const picked = resolveActionApiUuidRef.current?.(slot, saveApisRef.current);
          if (picked) {
            row[slot] = picked;
            changed = true;
          }
        }
        return changed ? { ...prev, [profile]: row } : prev;
      });
    },
    [requiredApiSlotsForProfile],
  );

  const pickSaveApiUuidForProfile = useCallback(
    (profile: string, fallback?: string) => {
      if (perActionApiBindingRef.current) {
        const confirmUuid = String(
          targetActionApiMapRef.current[profile]?.confirm || '',
        ).trim();
        if (confirmUuid) return confirmUuid;
      }
      const bound = String(saveApiUuidsRef.current[profile] || '').trim();
      if (bound) return bound;
      const resolve = resolveSaveApiForProfileRef.current;
      if (resolve) {
        const picked = resolve(profile, saveApisRef.current);
        if (picked) return picked;
      }
      return fallback || saveApiUuidRef.current;
    },
    [],
  );

  const openTargetSetting = useCallback(
    (key: string) => {
      if (multiApiTargetRowsRef.current) {
        const slot = apiSlotForBindingKey(key);
        let apiForRow = saveApiUuidsRef.current[key];
        if (!apiForRow) {
          apiForRow = resolveActionApiUuidRef.current?.(slot, saveApisRef.current);
          if (apiForRow) {
            setSaveApiUuids((prev) => ({ ...prev, [key]: apiForRow }));
          }
        }
        settingSnapshotRef.current = {
          connection: connectionCodeRef.current,
          api: apiForRow,
          mode: targetModesRef.current[key] ?? 'auto',
          actions: triggerActionsForBindingSlot(slot),
          destination: destinationKindsRef.current[key] ?? 'api',
          dataSourceUuid: dataSourceUuidsRef.current[key],
        };
        if (apiForRow) setSaveApiUuid(apiForRow);
        setSettingProfile(key);
        return;
      }
      const actions = effectiveBindActionsForProfile(key);
      if (!targetActionMapRef.current[key]?.length && actions.length) {
        setTargetActionMap((prev) => ({ ...prev, [key]: actions }));
      }
      seedActionApisForProfile(key, actions);
      const apiForProfile =
        targetActionApiMapRef.current[key]?.confirm ||
        saveApiUuidsRef.current[key] ||
        pickSaveApiUuidForProfile(key, saveApiUuidRef.current);
      settingSnapshotRef.current = {
        connection: connectionCodeRef.current,
        api: apiForProfile,
        mode: targetModesRef.current[key] ?? 'auto',
        actions: targetActionMapRef.current[key]?.length
          ? targetActionMapRef.current[key]
          : actions,
        destination: destinationKindsRef.current[key] ?? 'api',
        dataSourceUuid: dataSourceUuidsRef.current[key],
      };
      if (apiForProfile) setSaveApiUuid(apiForProfile);
      setSettingProfile(key);
    },
    [apiSlotForBindingKey, effectiveBindActionsForProfile, pickSaveApiUuidForProfile, seedActionApisForProfile],
  );

  const bindingKeysForReady = useMemo(() => {
    const keys = new Set(listBindingKeys);
    if (settingProfile) keys.add(settingProfile);
    if (pendingNewProfile) keys.add(pendingNewProfile);
    return [...keys];
  }, [listBindingKeys, pendingNewProfile, settingProfile]);

  /** 含设置弹窗中的待添加目标；就绪判定与预览/推送不得只看已落列表的 targetProfiles */
  const readinessProfiles = useMemo(() => {
    if (multiApiTargetRows) {
      const profiles = new Set<string>();
      for (const key of bindingKeysForReady) {
        const profile = rowBindingMeta[key]?.profile;
        if (profile) profiles.add(profile);
      }
      return [...profiles];
    }
    const profiles = new Set(targetProfiles);
    if (settingProfile) profiles.add(settingProfile);
    if (pendingNewProfile) profiles.add(pendingNewProfile);
    return [...profiles];
  }, [bindingKeysForReady, multiApiTargetRows, pendingNewProfile, rowBindingMeta, settingProfile, targetProfiles]);

  const needsKingdeeConnector = useMemo(
    () => readinessProfiles.some((p) => kingdeeProfiles.includes(p)),
    [kingdeeProfiles, readinessProfiles],
  );

  const selectedConnector = useMemo(
    () => connectors.find((row) => row.code === connectionCode),
    [connectionCode, connectors],
  );

  const profileLabel = useCallback(
    (profile: string) => {
      const key = DOCUMENT_PUSH_PROFILE_LABEL_KEYS[profile];
      if (key) return t(key);
      return profile;
    },
    [t],
  );

  const loadConnectors = useCallback(async () => {
    setConnectorsLoading(true);
    try {
      const rows = await getApplicationConnectionListAll({
        is_active: true,
      });
      setConnectors(rows);
      setConnectionCode((prev) => {
        if (prev && rows.some((row) => row.code === prev)) return prev;
        return rows.length === 1 ? rows[0]?.code : undefined;
      });
    } catch {
      setConnectors([]);
      setConnectionCode(undefined);
    } finally {
      setConnectorsLoading(false);
    }
  }, []);

  // 内容稳定的字符串 key：父页常传内联数组，引用变化不得触发重复请求
  const defaultProfilesKey = defaultProfiles.join('|');
  const saveApiHintsKey = saveApiSearchHints.join('|');
  const saveApiSearchHintsRef = useRef(saveApiSearchHints);
  saveApiSearchHintsRef.current = saveApiSearchHints;
  const defaultProfilesRef = useRef(defaultProfiles);
  defaultProfilesRef.current = defaultProfiles;
  const profileLabelRef = useRef(profileLabel);
  profileLabelRef.current = profileLabel;

  const loadSaveApis = useCallback(
    async (connection: ApplicationConnection | undefined) => {
      if (!connection) {
        setSaveApis([]);
        setSaveApiUuid(undefined);
        return;
      }
      setApisLoading(true);
      try {
        let items = await loadAllActiveApis();
        items = sortApisByPreferredHints(items, saveApiSearchHintsRef.current);
        setSaveApis(items);
        setSaveApiUuid((prev) => {
          if (prev && items.some((api) => api.uuid === prev)) return prev;
          const bound = Object.values(saveApiUuidsRef.current).find(
            (uuid) => uuid && items.some((api) => api.uuid === uuid),
          );
          if (bound) return bound;
          return preferSaveApi(items);
        });
      } catch {
        setSaveApis([]);
        setSaveApiUuid(undefined);
      } finally {
        setApisLoading(false);
      }
    },
    // saveApiHintsKey：内容变才重建；避免内联 ['生产汇报',…] 每帧换引用
    // eslint-disable-next-line react-hooks/exhaustive-deps -- hints via ref + key
    [preferSaveApi, saveApiHintsKey],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const labelOf = profileLabelRef.current;
    setProfilesLoading(true);
    setProfilesLoaded(false);
    void (async () => {
      try {
        const rows = await listDocumentPushProfiles();
        if (cancelled) return;
        const available = filterProfilesForSource(rows, sourceType);
        setProfileOptions(
          available.map((value) => ({
            value,
            label: labelOf(value),
          })),
        );
      } catch {
        if (cancelled) return;
        setProfileOptions([]);
      } finally {
        if (!cancelled) {
          setProfilesLoading(false);
          setProfilesLoaded(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional stable keys
  }, [defaultProfilesKey, open, sourceType]);

  useEffect(() => {
    // 关闭态 / 非金蝶目标不拉 /core/apis，避免列表页或 sync Tab 误打
    if (!open || !needsKingdeeConnector) return;
    void loadSaveApis(selectedConnector);
  }, [loadSaveApis, needsKingdeeConnector, open, selectedConnector]);

  useEffect(() => {
    if (!open) return;
    // 对齐入站：打开先空表，只回填接口里已经保存的目标，绝不填默认 profile
    setTargetProfiles([]);
    setTargetRowKeys([]);
    setRowBindingMeta({});
    setPendingNewProfile(null);
    setSettingProfile(null);
    if (!loadBinding) return;
    let cancelled = false;
    void (async () => {
      try {
        const binding = await loadBinding();
        if (cancelled) return;
        if (!binding) {
          setTargetProfiles([]);
          setTargetRowKeys([]);
          setSaveApiUuids({});
          setAutoPushPaused(false);
          return;
        }
        const rows = (binding.targets || []).filter((row) =>
          sourceType === 'purchase_order' ? row.user_saved === true : Boolean(row.target_profile),
        );
        setAutoPushPaused(
          rows.length > 0 && rows.every((row) => row.push_enabled === false),
        );
        const modes: Record<string, 'auto' | 'manual'> = {};
        const actions: Record<string, string[]> = {};
        const kinds: Record<string, 'api' | 'data_source'> = {};
        const sources: Record<string, string | undefined> = {};
        const datasets: Record<string, string | undefined> = {};
        const apis: Record<string, string | undefined> = {};
        const actionApis: Record<string, Record<string, string | undefined>> = {};
        const meta: Record<string, { profile: string; apiSlot: string }> = {};
        const rowKeys: string[] = [];

        if (multiApiTargetRows) {
          const expanded = expandBindingTargetsToRowDrafts(rows);
          for (const item of expanded) {
            rowKeys.push(item.rowKey);
            meta[item.rowKey] = { profile: item.profile, apiSlot: item.apiSlot };
            const row = item.target;
            modes[item.rowKey] = row.push_mode === 'manual' ? 'manual' : 'auto';
            actions[item.rowKey] = row.trigger_actions?.length
              ? row.trigger_actions
              : triggerActionsForBindingSlot(item.apiSlot);
            kinds[item.rowKey] =
              row.destination_kind === 'data_source' ? 'data_source' : 'api';
            sources[item.rowKey] = row.data_source_uuid;
            datasets[item.rowKey] = row.dataset_uuid;
            apis[item.rowKey] = row.save_api_uuid;
          }
          setTargetRowKeys(rowKeys);
          setRowBindingMeta(meta);
        } else {
          setTargetProfiles(rows.map((row) => row.target_profile).filter(Boolean));
          for (const row of rows) {
            modes[row.target_profile] = row.push_mode === 'manual' ? 'manual' : 'auto';
            actions[row.target_profile] = row.trigger_actions?.length
              ? row.trigger_actions
              : perActionApiBinding
                ? defaultAutoBindActions
                : binding.trigger_actions || [];
            kinds[row.target_profile] =
              row.destination_kind === 'data_source' ? 'data_source' : 'api';
            sources[row.target_profile] = row.data_source_uuid;
            datasets[row.target_profile] = row.dataset_uuid;
            const rowActionApis = row.action_apis || {};
            if (rowActionApis.confirm) {
              apis[row.target_profile] = rowActionApis.confirm;
            } else if (row.save_api_uuid) {
              apis[row.target_profile] = row.save_api_uuid;
            }
            if (row.action_apis && Object.keys(row.action_apis).length) {
              actionApis[row.target_profile] = { ...row.action_apis };
            }
          }
        }
        setTargetModes(modes);
        setTargetActionMap(actions);
        setDestinationKinds(kinds);
        setDataSourceUuids(sources);
        setDatasetUuids(datasets);
        setSaveApiUuids(apis);
        setTargetActionApiMap(actionApis);
        const kd = rows.find((row) => row.connection_code || row.save_api_uuid);
        if (kd?.connection_code) setConnectionCode(kd.connection_code);
        else if (binding.connection_code) setConnectionCode(binding.connection_code);
        if (kd?.save_api_uuid) setSaveApiUuid(kd.save_api_uuid);
        else if (binding.save_api_uuid) setSaveApiUuid(binding.save_api_uuid);
        if (binding.sync_mode) setSyncMode(binding.sync_mode);
        if (binding.schedule_interval_minutes) {
          setScheduleIntervalMinutes(binding.schedule_interval_minutes);
        }
      } catch {
        if (cancelled) return;
        setTargetProfiles([]);
        setTargetRowKeys([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [defaultAutoBindActions, loadBinding, multiApiTargetRows, open, perActionApiBinding, sourceType]);

  const allowedProfileSet = useMemo(
    () => new Set(profileOptions.map((o) => o.value)),
    [profileOptions],
  );

  const profilesReady = useMemo(() => {
    if (!profilesLoaded || profilesLoading) return false;
    if (!profileOptions.length) return false;
    if (multiApiTargetRows) {
      if (!bindingKeysForReady.length) return false;
      return bindingKeysForReady.every((key) => {
        const profile = rowBindingMeta[key]?.profile;
        return profile && allowedProfileSet.has(profile);
      });
    }
    if (!readinessProfiles.length) return false;
    return readinessProfiles.every((p) => allowedProfileSet.has(p));
  }, [
    allowedProfileSet,
    bindingKeysForReady,
    multiApiTargetRows,
    profileOptions.length,
    profilesLoaded,
    profilesLoading,
    readinessProfiles,
    rowBindingMeta,
  ]);

  const connectorReady = useMemo(() => {
    const needsApiConnector = bindingKeysForReady.some((key) => {
      const profile = profileForBindingKey(key);
      return kingdeeProfiles.includes(profile) && (destinationKinds[key] ?? 'api') === 'api';
    });
    if (!needsApiConnector) return true;
    if (connectorsLoading) return false;
    if (!connectionCode) return false;
    if (apisLoading) return false;
    const kdKeys = bindingKeysForReady.filter((key) => {
      const profile = profileForBindingKey(key);
      return kingdeeProfiles.includes(profile) && (destinationKinds[key] ?? 'api') === 'api';
    });
    if (
      kdKeys.some((key) => {
        if (multiApiTargetRows) {
          return !String(saveApiUuids[key] || '').trim();
        }
        if (perActionApiBinding) {
          const actions =
            targetActionMap[key]?.length ? targetActionMap[key] : defaultAutoBindActions;
          return requiredApiSlotsForProfile(key, actions).some(
            (slot) => !String(targetActionApiMap[key]?.[slot] || '').trim(),
          );
        }
        return !pickSaveApiUuidForProfile(key, saveApiUuid);
      })
    ) {
      return false;
    }
    return true;
  }, [
    apisLoading,
    bindingKeysForReady,
    connectionCode,
    connectorsLoading,
    defaultAutoBindActions,
    destinationKinds,
    kingdeeProfiles,
    multiApiTargetRows,
    perActionApiBinding,
    pickSaveApiUuidForProfile,
    profileForBindingKey,
    requiredApiSlotsForProfile,
    saveApiUuid,
    saveApiUuids,
    targetActionApiMap,
    targetActionMap,
  ]);

  const pushReady = profilesReady && connectorReady;
  const pushReadyRef = useRef(pushReady);
  pushReadyRef.current = pushReady;

  const notReadyReason = useMemo(() => {
    if (!profilesLoaded || profilesLoading) {
      return t('app.kuaizhizao.documentPush.batch.profilesLoading');
    }
    if (!profileOptions.length) {
      return t('app.kuaizhizao.documentPush.batch.noProfiles');
    }
    if (multiApiTargetRows) {
      if (!bindingKeysForReady.length) {
        return t('app.kuaizhizao.documentPush.batch.needTargetProfile');
      }
      if (
        !bindingKeysForReady.every((key) => {
          const profile = rowBindingMeta[key]?.profile;
          return profile && allowedProfileSet.has(profile);
        })
      ) {
        return t('app.kuaizhizao.documentPush.batch.needTargetProfile');
      }
    } else if (
      !readinessProfiles.length ||
      !readinessProfiles.every((p) => allowedProfileSet.has(p))
    ) {
      return t('app.kuaizhizao.documentPush.batch.needTargetProfile');
    }
    if (needsKingdeeConnector && !connectionCode) {
      return t('app.kuaizhizao.documentPush.batch.needConnector');
    }
    if (needsKingdeeConnector) {
      for (const key of bindingKeysForReady) {
        const profile = profileForBindingKey(key);
        if (!kingdeeProfiles.includes(profile)) continue;
        if ((destinationKinds[key] ?? 'api') !== 'api') continue;
        if (multiApiTargetRows) {
          if (!String(saveApiUuids[key] || '').trim()) {
            return t('app.kuaizhizao.documentPush.batch.needApi');
          }
        } else if (perActionApiBinding) {
          const actions = effectiveBindActionsForProfile(key);
          for (const slot of requiredApiSlotsForProfile(key, actions)) {
            if (!String(targetActionApiMap[key]?.[slot] || '').trim()) {
              return t('app.kuaizhizao.documentPush.batch.needActionApi');
            }
          }
        } else if (!pickSaveApiUuidForProfile(key, saveApiUuid)) {
          return t('app.kuaizhizao.documentPush.batch.needApi');
        }
      }
    }
    return null;
  }, [
    allowedProfileSet,
    bindingKeysForReady,
    connectionCode,
    destinationKinds,
    effectiveBindActionsForProfile,
    kingdeeProfiles,
    multiApiTargetRows,
    needsKingdeeConnector,
    perActionApiBinding,
    pickSaveApiUuidForProfile,
    profileForBindingKey,
    readinessProfiles,
    profileOptions.length,
    profilesLoaded,
    profilesLoading,
    requiredApiSlotsForProfile,
    rowBindingMeta,
    saveApiUuid,
    saveApiUuids,
    targetActionApiMap,
    t,
  ]);

  const pull = useUniPullQuery<T>({
    rowKey: 'id',
    selectionType: 'checkbox',
    loadData: async ({ keyword, page, pageSize }) => {
      const res = await loadCandidates({
        keyword,
        page,
        pageSize,
        preferIds: preferIdsRef.current,
      });
      return { data: res.data || [], total: res.total || 0 };
    },
    onConfirm: async (_keys, rows) => {
      // 未就绪禁止推送与成功 toast
      if (!pushReadyRef.current) {
        Modal.warning({
          title,
          content: notReadyReason || t('components.syncPushHub.pushNotReady'),
        });
        return;
      }
      const ids = rows.map((row) => Number(row.id)).filter((id) => Number.isFinite(id) && id > 0);
      if (!ids.length) {
        Modal.warning({ title, content: needSelectMessage });
        return;
      }
      const conn = connectionCodeRef.current;
      const apiUuid = saveApiUuidRef.current;
      const allowed = new Set(profileOptionsRef.current.map((o) => o.value));
      const onlyBindingKey = pushOnlyProfileRef.current;
      // multiApiTargetRows：设置弹窗 key 是绑定行 id，须映射到 target_profile 再校验白名单
      const profileOfBindingKey = (key: string) => {
        if (multiApiTargetRowsRef.current) {
          return String(rowBindingMetaRef.current[key]?.profile || '').trim();
        }
        return key;
      };
      // 设置弹窗内推送：onlyBindingKey 可能仍是 pending，尚未写入列表
      const bindingKeys = onlyBindingKey
        ? (() => {
            const profile = profileOfBindingKey(onlyBindingKey);
            return profile && allowed.has(profile) ? [onlyBindingKey] : [];
          })()
        : targetProfilesRef.current.filter((key) => {
            if (!key) return false;
            const profile = profileOfBindingKey(key);
            if (!profile || !allowed.has(profile)) return false;
            return (targetModesRef.current[key] ?? 'auto') === 'manual';
          });
      if (!bindingKeys.length) {
        Modal.warning({
          title,
          content: t('app.kuaizhizao.documentPush.batch.needTargetProfile'),
        });
        return;
      }
      const dataSourceKeys = bindingKeys.filter(
        (key) => (destinationKindsRef.current[key] ?? 'api') === 'data_source',
      );
      if (dataSourceKeys.some((key) => !datasetUuidsRef.current[key])) {
        Modal.warning({
          title,
          content: t('app.kuaizhizao.documentPush.batch.needWriteDataset'),
        });
        return;
      }
      const apiKeys = bindingKeys.filter(
        (key) => (destinationKindsRef.current[key] ?? 'api') !== 'data_source',
      );
      const needKd = apiKeys.some((key) =>
        kingdeeProfiles.includes(profileOfBindingKey(key)),
      );
      if (needKd && !conn) {
        Modal.warning({
          title,
          content: t('app.kuaizhizao.documentPush.batch.needConnector'),
        });
        return;
      }
      if (
        needKd &&
        apiKeys.some((key) => {
          const profile = profileOfBindingKey(key);
          return (
            kingdeeProfiles.includes(profile) && !pickSaveApiUuidForProfile(key, apiUuid)
          );
        })
      ) {
        Modal.warning({
          title,
          content: t('app.kuaizhizao.documentPush.batch.needApi'),
        });
        return;
      }
      try {
        if (saveBinding && rememberBindingRef.current) {
          const listed = targetProfilesRef.current.filter((key) => {
            const profile = profileOfBindingKey(key);
            return Boolean(key && profile && allowed.has(profile));
          });
          const allBindingKeys =
            onlyBindingKey &&
            profileOfBindingKey(onlyBindingKey) &&
            allowed.has(profileOfBindingKey(onlyBindingKey)) &&
            !listed.includes(onlyBindingKey)
              ? [...listed, onlyBindingKey]
              : listed;
          const bound = allBindingKeys.map((key) => {
            const profile = profileOfBindingKey(key);
            const mode = targetModesRef.current[key] ?? 'auto';
            const actions =
              mode === 'auto'
                ? targetActionMapRef.current[key]?.length
                  ? targetActionMapRef.current[key]
                  : defaultAutoBindActions
                : [];
            const actionApis = perActionApiBindingRef.current
              ? buildActionApisForProfile(key, actions)
              : undefined;
            const saveUuid =
              actionApis?.confirm ||
              (kingdeeProfiles.includes(profile) &&
              (destinationKindsRef.current[key] ?? 'api') === 'api'
                ? pickSaveApiUuidForProfile(key, apiUuid)
                : undefined);
            return {
              target_profile: profile,
              push_mode: mode,
              destination_kind: destinationKindsRef.current[key] ?? 'api',
              data_source_uuid:
                (destinationKindsRef.current[key] ?? 'api') === 'data_source'
                  ? dataSourceUuidsRef.current[key]
                  : undefined,
              dataset_uuid:
                (destinationKindsRef.current[key] ?? 'api') === 'data_source'
                  ? datasetUuidsRef.current[key]
                  : undefined,
              trigger_actions: actions,
              action_apis: actionApis,
              connection_code:
                kingdeeProfiles.includes(profile) &&
                (destinationKindsRef.current[key] ?? 'api') === 'api'
                  ? conn
                  : undefined,
              save_api_uuid: saveUuid,
              user_saved: true,
              push_enabled: !autoPushPaused,
            };
          });
          const autoActions = [
            ...new Set(bound.flatMap((row) => row.trigger_actions)),
          ];
          await saveBinding({
            targets: bound,
            trigger_actions: autoActions,
            connection_code: conn,
            save_api_uuid: apiUuid,
            sync_mode: syncModeRef.current,
            schedule_interval_minutes: scheduleIntervalRef.current,
          });
        }

        let created = 0;
        const alreadyPushedIds: number[] = [];
        let skipped = 0;
        let failed = 0;
        const errors: string[] = [];

        for (const id of ids) {
          try {
            const targets = bindingKeys.map((key) => {
              const profile = profileOfBindingKey(key);
              return {
                target_profile: profile,
                destination_kind: destinationKindsRef.current[key] ?? 'api',
                data_source_uuid:
                  (destinationKindsRef.current[key] ?? 'api') === 'data_source'
                    ? dataSourceUuidsRef.current[key]
                    : undefined,
                dataset_uuid:
                  (destinationKindsRef.current[key] ?? 'api') === 'data_source'
                    ? datasetUuidsRef.current[key]
                    : undefined,
                connection_code:
                  kingdeeProfiles.includes(profile) &&
                  (destinationKindsRef.current[key] ?? 'api') === 'api'
                    ? conn
                    : undefined,
                save_api_uuid:
                  kingdeeProfiles.includes(profile) &&
                  (destinationKindsRef.current[key] ?? 'api') === 'api'
                    ? pickSaveApiUuidForProfile(key, apiUuid)
                    : undefined,
              };
            });
            const result = await pushDocumentExternal({
              source_type: sourceType,
              source_id: id,
              targets,
              dry_run: false,
            });
            if (result.multi) {
              created += Number(result.created || 0);
              skipped += Number(result.skipped || 0);
              failed += Number(result.failed || 0);
              for (const one of result.results || []) {
                if (one.success === false) {
                  errors.push(
                    `${id}/${one.target_profile}: ${one.message || t(failedTitleKey)}`,
                  );
                }
              }
            } else if (result.success === false) {
              failed += 1;
              errors.push(`${id}: ${result.message || t(failedTitleKey)}`);
            } else if (result.skipped) {
              skipped += 1;
              alreadyPushedIds.push(id);
            } else {
              created += 1;
            }
          } catch (err: unknown) {
            failed += 1;
            const msg = err instanceof Error ? err.message : String(err || '');
            errors.push(`${id}: ${msg || t(failedTitleKey)}`);
          }
        }

        const notify = embedded ? messageApi : null;
        const uniqueAlreadyPushed = [...new Set(alreadyPushedIds)];
        if (
          sourceType === 'purchase_receipt' &&
          uniqueAlreadyPushed.length > 0 &&
          created === 0 &&
          failed === 0
        ) {
          const confirmed = await new Promise<boolean>((resolve) => {
            Modal.confirm({
              title: t('app.kuaizhizao.warehouseInbound.msg.externalPushRepushTitle'),
              content: t('app.kuaizhizao.warehouseInbound.msg.externalPushRepushConfirm', {
                reason: t(skippedHintKey, { skipped: uniqueAlreadyPushed.length }),
              }),
              okText: t('app.kuaizhizao.warehouseInbound.action.repush'),
              onOk: () => resolve(true),
              onCancel: () => resolve(false),
            });
          });
          if (confirmed) {
            let forceCreated = 0;
            let forceFailed = 0;
            const forceErrors: string[] = [];
            const forceTargets = bindingKeys.map((key) => {
              const profile = profileOfBindingKey(key);
              return {
                target_profile: profile,
                destination_kind: destinationKindsRef.current[key] ?? 'api',
                data_source_uuid:
                  (destinationKindsRef.current[key] ?? 'api') === 'data_source'
                    ? dataSourceUuidsRef.current[key]
                    : undefined,
                dataset_uuid:
                  (destinationKindsRef.current[key] ?? 'api') === 'data_source'
                    ? datasetUuidsRef.current[key]
                    : undefined,
                connection_code:
                  kingdeeProfiles.includes(profile) &&
                  (destinationKindsRef.current[key] ?? 'api') === 'api'
                    ? conn
                    : undefined,
                save_api_uuid:
                  kingdeeProfiles.includes(profile) &&
                  (destinationKindsRef.current[key] ?? 'api') === 'api'
                    ? pickSaveApiUuidForProfile(key, apiUuid)
                    : undefined,
              };
            });
            for (const id of uniqueAlreadyPushed) {
              try {
                const result = await pushDocumentExternal({
                  source_type: sourceType,
                  source_id: id,
                  targets: forceTargets,
                  dry_run: false,
                  force: true,
                });
                if (result.multi) {
                  forceCreated += Number(result.created || 0);
                  forceFailed += Number(result.failed || 0);
                  for (const one of result.results || []) {
                    if (one.success === false) {
                      forceErrors.push(
                        `${id}/${one.target_profile}: ${one.message || t(failedTitleKey)}`,
                      );
                    }
                  }
                } else if (result.success === false) {
                  forceFailed += 1;
                  forceErrors.push(`${id}: ${result.message || t(failedTitleKey)}`);
                } else if (!result.skipped) {
                  forceCreated += 1;
                }
              } catch (err: unknown) {
                forceFailed += 1;
                const msg = err instanceof Error ? err.message : String(err || '');
                forceErrors.push(`${id}: ${msg || t(failedTitleKey)}`);
              }
            }
            if (forceFailed > 0 && forceCreated === 0) {
              const detail = forceErrors.slice(0, 5).join('\n') || t(failedTitleKey);
              if (notify) notify.error(detail);
              else Modal.error({ title: t(failedTitleKey), content: detail });
              return;
            }
            const title = t('app.kuaizhizao.warehouseInbound.msg.externalPushRepushSuccess');
            if (notify) notify.success(title);
            else Modal.success({ title });
            onComplete?.();
            onClose();
            return;
          }
        }

        if (failed > 0 && created === 0) {
          const detail = errors.slice(0, 5).join('\n') || t(failedTitleKey);
          if (notify) notify.error(detail);
          else
            Modal.error({
              title: t(failedTitleKey),
              content: (
                <div>
                  {errors.slice(0, 5).map((err) => (
                    <Typography.Paragraph key={err} type="danger" style={{ marginBottom: 4 }}>
                      {err}
                    </Typography.Paragraph>
                  ))}
                </div>
              ),
            });
          return;
        }
        if (failed > 0) {
          const title = t(partialCountKey, { created, skipped, failed });
          if (notify) notify.warning(title);
          else Modal.warning({ title, content: errors.slice(0, 5).join('\n') || undefined });
        } else {
          const title = t(successCountKey, { count: created });
          if (notify) notify.success(title);
          else
            Modal.success({
              title,
              content: skipped > 0 ? t(skippedHintKey, { skipped }) : undefined,
            });
        }
        onComplete?.();
        onClose();
      } catch (error: unknown) {
        const msg = error instanceof Error ? error.message : String(error || '');
        Modal.error({
          title: t(failedTitleKey),
          content: msg || t(failedTitleKey),
        });
      }
    },
    onClose,
  });

  useEffect(() => {
    if (open) {
      preferIdsRef.current = (preferIds || []).filter((id) => Number.isFinite(id));
      prefilledRef.current = false;
      setPendingNewProfile(null);
      setSettingProfile(null);
      void loadConnectors();
      setDataSourcesLoading(true);
      void getDataSourceListAllMatching({ is_active: true })
        .then((rows) => setDataSources(rows))
        .catch(() => setDataSources([]))
        .finally(() => setDataSourcesLoading(false));
      void getDatasetList({ query_type: 'sql_write', is_active: true, page: 1, page_size: 200 })
        .then((res) => setWriteDatasets(res.items || []))
        .catch(() => setWriteDatasets([]));
      pull.openModal();
      return;
    }
    if (pull.open) {
      pull.resetModal();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只跟随外部 open
  }, [open]);

  useEffect(() => {
    if (!open || prefilledRef.current || !preferIdsRef.current.length || !pull.dataSource.length) {
      return;
    }
    const preferSet = new Set(preferIdsRef.current);
    const rows = pull.dataSource.filter((row) => preferSet.has(row.id));
    if (!rows.length) return;
    pull.handleSelectedRowKeysChange(
      rows.map((row) => row.id),
      rows,
    );
    prefilledRef.current = true;
  }, [open, pull.dataSource, pull.handleSelectedRowKeysChange]);

  const handlePreviewPayload = useCallback(async () => {
    if (!pushReadyRef.current) {
      Modal.warning({
        title: t('app.kuaizhizao.documentPush.previewTitle'),
        content: notReadyReason || t('components.syncPushHub.pushNotReady'),
      });
      return;
    }
    const rows = pull.selectedRows || [];
    const first = rows[0];
    if (!first?.id) {
      Modal.warning({
        title: t('app.kuaizhizao.documentPush.previewTitle'),
        content: t('app.kuaizhizao.documentPush.batch.previewNeedOne'),
      });
      return;
    }
    const conn = connectionCodeRef.current;
    const apiUuid = saveApiUuidRef.current;
    const allowed = new Set(profileOptionsRef.current.map((o) => o.value));
    const onlyBindingKey = settingProfileRef.current;
    const profileOfBindingKey = (key: string) => {
      if (multiApiTargetRowsRef.current) {
        return String(rowBindingMetaRef.current[key]?.profile || '').trim();
      }
      return key;
    };
    // 设置弹窗内预览：当前目标可能尚未落列表；multiApi 行 key ≠ profile
    const bindingKeys = onlyBindingKey
      ? (() => {
          const profile = profileOfBindingKey(onlyBindingKey);
          return profile && allowed.has(profile) ? [onlyBindingKey] : [];
        })()
      : targetProfilesRef.current.filter((key) => {
          if (!key) return false;
          const profile = profileOfBindingKey(key);
          return Boolean(profile && allowed.has(profile));
        });
    if (!bindingKeys.length) {
      Modal.warning({
        title: t('app.kuaizhizao.documentPush.previewTitle'),
        content: t('app.kuaizhizao.documentPush.batch.needTargetProfile'),
      });
      return;
    }
    const apiKeys = bindingKeys.filter(
      (key) => (destinationKindsRef.current[key] ?? 'api') !== 'data_source',
    );
    if (!apiKeys.length) {
      Modal.info({
        title: t('app.kuaizhizao.documentPush.previewTitle'),
        content: t('app.kuaizhizao.documentPush.batch.dataSourceNoted'),
      });
      return;
    }
    const needKd = apiKeys.some((key) =>
      kingdeeProfiles.includes(profileOfBindingKey(key)),
    );
    if (needKd && !conn) {
      Modal.warning({
        title: t('app.kuaizhizao.documentPush.previewTitle'),
        content: t('app.kuaizhizao.documentPush.batch.needConnector'),
      });
      return;
    }
    if (
      needKd &&
      apiKeys.some((key) => {
        const profile = profileOfBindingKey(key);
        return (
          kingdeeProfiles.includes(profile) && !pickSaveApiUuidForProfile(key, apiUuid)
        );
      })
    ) {
      Modal.warning({
        title: t('app.kuaizhizao.documentPush.previewTitle'),
        content: t('app.kuaizhizao.documentPush.batch.needApi'),
      });
      return;
    }
    const previewProfiles = apiKeys.map((key) => profileOfBindingKey(key));
    setPreviewLoading(true);
    try {
      const result = await pushDocumentExternal({
        source_type: sourceType,
        source_id: Number(first.id),
        targets: apiKeys.map((key) => {
          const profile = profileOfBindingKey(key);
          return {
            target_profile: profile,
            connection_code: needKd && kingdeeProfiles.includes(profile) ? conn : undefined,
            save_api_uuid:
              needKd && kingdeeProfiles.includes(profile)
                ? pickSaveApiUuidForProfile(key, apiUuid)
                : undefined,
          };
        }),
        dry_run: true,
      });
      const model = (result.model || {}) as Record<string, unknown>;
      const profileLabelText = result.multi
        ? (result.target_profiles || previewProfiles).map(profileLabel).join(', ')
        : profileLabel(String(result.target_profile || previewProfiles[0]));
      Modal.info({
        title: t('app.kuaizhizao.documentPush.previewTitle'),
        width: 720,
        content: (
          <div>
            <Typography.Paragraph>
              profile=<Typography.Text code>{profileLabelText}</Typography.Text>
              {' · '}
              form_id=<Typography.Text code>{String(result.form_id || '—')}</Typography.Text>
            </Typography.Paragraph>
            <Typography.Paragraph type="warning" style={{ marginBottom: 8 }}>
              {t('app.kuaizhizao.documentPush.previewSourceNote')}
            </Typography.Paragraph>
            <Typography.Paragraph>
              <pre style={{ maxHeight: 360, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(result.multi ? result.results : model, null, 2)}
              </pre>
            </Typography.Paragraph>
          </div>
        ),
      });
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error || '');
      Modal.error({
        title: t('app.kuaizhizao.documentPush.previewTitle'),
        content: msg || t(failedTitleKey),
      });
    } finally {
      setPreviewLoading(false);
    }
  }, [
    failedTitleKey,
    kingdeeProfiles,
    notReadyReason,
    profileLabel,
    pull.selectedRows,
    sourceType,
    t,
  ]);

  const connectorOptions = useMemo(
    () =>
      connectors.map((row) => ({
        value: row.code,
        label: row.name ? `${row.name}（${row.code}）` : row.code,
      })),
    [connectors],
  );

  const apiOptions = useMemo(() => {
    const conn = selectedConnector;
    const settingKey = settingProfile;
    let items = saveApis;
    if (multiApiTargetRows && settingKey && matchBindingApi) {
      const slot = String(rowBindingMeta[settingKey]?.apiSlot || 'confirm').trim() || 'confirm';
      items = saveApis.filter((api) => matchBindingApi(slot, api, conn));
    }
    return items.map((api) => ({
      value: api.uuid,
      label: api.name ? `${api.name}（${api.code}）` : api.code,
    }));
  }, [
    matchBindingApi,
    multiApiTargetRows,
    rowBindingMeta,
    saveApis,
    selectedConnector,
    settingProfile,
  ]);

  settingProfileRef.current = settingProfile;

  const profileConfigNotReadyReason = useCallback(
    (key: string): string | null => {
      const bindingKey = String(key || '').trim();
      if (!bindingKey) {
        return t('app.kuaizhizao.documentPush.batch.needTargetProfile');
      }
      const profile = profileForBindingKey(bindingKey);
      if (!profile || !allowedProfileSet.has(profile)) {
        return t('app.kuaizhizao.documentPush.batch.needTargetProfile');
      }
      const kind = destinationKinds[bindingKey] ?? 'api';
      if (kind === 'data_source') {
        if (!dataSourceUuids[bindingKey]) {
          return t('app.kuaizhizao.documentPush.batch.needDataSource');
        }
        if (!datasetUuids[bindingKey]) {
          return t('app.kuaizhizao.documentPush.batch.needWriteDataset');
        }
        return null;
      }
      if (kingdeeProfiles.includes(profile)) {
        if (!connectionCode) {
          return t('app.kuaizhizao.documentPush.batch.needConnector');
        }
        if (multiApiTargetRows) {
          if (!pickSaveApiUuidForProfile(bindingKey, saveApiUuid)) {
            return t('app.kuaizhizao.documentPush.batch.needApi');
          }
        } else if (perActionApiBinding) {
          const actions = effectiveBindActionsForProfile(bindingKey);
          for (const slot of requiredApiSlotsForProfile(bindingKey, actions)) {
            if (!String(targetActionApiMap[bindingKey]?.[slot] || '').trim()) {
              return t('app.kuaizhizao.documentPush.batch.needActionApi');
            }
          }
        } else if (!pickSaveApiUuidForProfile(bindingKey, saveApiUuid)) {
          return t('app.kuaizhizao.documentPush.batch.needApi');
        }
      }
      return null;
    },
    [
      allowedProfileSet,
      connectionCode,
      dataSourceUuids,
      datasetUuids,
      destinationKinds,
      effectiveBindActionsForProfile,
      kingdeeProfiles,
      multiApiTargetRows,
      perActionApiBinding,
      pickSaveApiUuidForProfile,
      profileForBindingKey,
      requiredApiSlotsForProfile,
      saveApiUuid,
      t,
      targetActionApiMap,
    ],
  );

  const closeTargetSetting = (apply: boolean) => {
    if (!apply && settingSnapshotRef.current && settingProfile) {
      const snap = settingSnapshotRef.current;
      setConnectionCode(snap.connection);
      setSaveApiUuid(snap.api);
      setSaveApiUuids((prev) => ({ ...prev, [settingProfile]: snap.api }));
      setTargetModes((prev) => ({ ...prev, [settingProfile]: snap.mode }));
      setTargetActionMap((prev) => ({ ...prev, [settingProfile]: snap.actions }));
      setDestinationKinds((prev) => ({ ...prev, [settingProfile]: snap.destination }));
      setDataSourceUuids((prev) => ({ ...prev, [settingProfile]: snap.dataSourceUuid }));
    }
    if (apply && settingProfile) {
      const blockReason = profileConfigNotReadyReason(settingProfile);
      if (blockReason) {
        Modal.warning({
          title: t('app.kuaizhizao.documentPush.batch.targetSettingTitle'),
          content: blockReason,
        });
        return;
      }
      const appliedActions = effectiveBindActionsForProfile(settingProfile);
      if (appliedActions.length) {
        setTargetActionMap((prev) => ({ ...prev, [settingProfile]: appliedActions }));
      }
      const confirmUuid = targetActionApiMap[settingProfile]?.confirm || saveApiUuid;
      if (confirmUuid) {
        setSaveApiUuids((prev) => ({ ...prev, [settingProfile]: confirmUuid }));
      }
      if (pendingNewProfile) {
        if (multiApiTargetRows) {
          setTargetRowKeys((prev) =>
            prev.includes(settingProfile) ? prev : [...prev, settingProfile],
          );
        } else {
          setTargetProfiles((prev) =>
            prev.includes(settingProfile) ? prev : [...prev, settingProfile],
          );
        }
      }
      if (multiApiTargetRows) {
        const slot = apiSlotForBindingKey(settingProfile);
        setTargetActionMap((prev) => ({
          ...prev,
          [settingProfile]: triggerActionsForBindingSlot(slot),
        }));
        const rowApi = saveApiUuids[settingProfile] || saveApiUuid;
        if (rowApi) {
          setSaveApiUuids((prev) => ({ ...prev, [settingProfile]: rowApi }));
        }
      }
    }
    setPendingNewProfile(null);
    setSettingProfile(null);
  };

  const settingModal = settingProfile ? (
    <Modal
      title={t('app.kuaizhizao.documentPush.batch.targetSettingTitle')}
      open
      onCancel={() => closeTargetSetting(false)}
      width={1100}
      zIndex={1100}
      destroyOnHidden
      footer={[
        <Button key="cancel" onClick={() => closeTargetSetting(false)}>
          {t('common.cancel')}
        </Button>,
        (targetModes[settingProfile] ?? 'auto') === 'manual' &&
        (destinationKinds[settingProfile] ?? 'api') === 'api' ? (
          <Button
            key="preview"
            loading={previewLoading}
            disabled={!pushReady}
            onClick={() => void handlePreviewPayload()}
          >
            {t('app.kuaizhizao.documentPush.preview')}
          </Button>
        ) : null,
        (targetModes[settingProfile] ?? 'auto') === 'manual' ? (
          <Button
            key="push"
            type="primary"
            loading={pull.confirmLoading}
            disabled={!pushReady || pull.confirmLoading}
            onClick={() => {
              pushOnlyProfileRef.current = settingProfile;
              void pull.handleConfirm().finally(() => {
                pushOnlyProfileRef.current = null;
              });
            }}
          >
            {confirmText || t('app.kuaizhizao.documentPush.batch.confirm')}
          </Button>
        ) : (
          <Button key="save" type="primary" onClick={() => closeTargetSetting(true)}>
            {t('common.save')}
          </Button>
        ),
      ]}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'max-content minmax(0, 1fr)',
          columnGap: 12,
          rowGap: 12,
          alignItems: 'center',
        }}
      >
        <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}>
          {t('app.kuaizhizao.documentPush.batch.destinationKind')}
        </Typography.Text>
        <div style={{ display: 'flex', alignItems: 'center', minWidth: 0 }}>
          <ThemedSegmented
            block
            style={{ width: 200, maxWidth: '100%' }}
            value={destinationKinds[settingProfile] ?? 'api'}
            onChange={(value) => {
              const kind = value === 'data_source' ? 'data_source' : 'api';
              setDestinationKinds((prev) => ({ ...prev, [settingProfile]: kind }));
              if (kind === 'data_source' && dataSources.length === 1 && !dataSourceUuids[settingProfile]) {
                setDataSourceUuids((prev) => ({ ...prev, [settingProfile]: dataSources[0]?.uuid }));
              }
            }}
            options={[
              { label: t('app.kuaizhizao.documentPush.batch.apiPlaceholder'), value: 'api' },
              { label: t('app.kuaizhizao.documentPush.batch.destinationDataset'), value: 'data_source' },
            ]}
          />
        </div>
        <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}>
          {t('app.kuaizhizao.documentPush.batch.modeLabel')}
        </Typography.Text>
        <Select
          style={{ width: 220 }}
          value={targetModes[settingProfile] ?? 'auto'}
          onChange={(value: 'auto' | 'manual') =>
            setTargetModes((prev) => ({ ...prev, [settingProfile]: value }))
          }
          options={[
            { value: 'auto', label: t('app.kuaizhizao.documentPush.batch.modeAuto') },
            { value: 'manual', label: t('app.kuaizhizao.documentPush.batch.modeManual') },
          ]}
        />
        {multiApiTargetRows && (destinationKinds[settingProfile] ?? 'api') === 'api' ? (
          <>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}>
              {t('app.kuaizhizao.documentPush.batch.apiBindingSlot')}
            </Typography.Text>
            <Select
              style={{ width: '100%', maxWidth: 520 }}
              value={rowBindingMeta[settingProfile]?.apiSlot || 'confirm'}
              options={resolvedApiBindingSlotOptions}
              onChange={(slot) => {
                const profile = profileForBindingKey(settingProfile);
                setRowBindingMeta((prev) => ({
                  ...prev,
                  [settingProfile]: {
                    profile: prev[settingProfile]?.profile || profile,
                    apiSlot: slot,
                  },
                }));
                setTargetActionMap((prev) => ({
                  ...prev,
                  [settingProfile]: triggerActionsForBindingSlot(slot),
                }));
                const picked = resolveActionApiUuidRef.current?.(slot, saveApis);
                if (picked) {
                  setSaveApiUuid(picked);
                  setSaveApiUuids((prev) => ({ ...prev, [settingProfile]: picked }));
                }
              }}
            />
          </>
        ) : null}
        {(targetModes[settingProfile] ?? 'auto') === 'auto' && !multiApiTargetRows ? (
          <>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}>
              {t('app.kuaizhizao.documentPush.batch.bindActions')}
            </Typography.Text>
            <div style={{ minWidth: 0 }}>
              <Checkbox.Group
                options={resolvedBindActionOptions}
                value={effectiveBindActionsForProfile(settingProfile)}
                onChange={(vals) => {
                  const next = vals.map(String);
                  setTargetActionMap((prev) => ({ ...prev, [settingProfile]: next }));
                  if (perActionApiBinding && settingProfile) {
                    setTargetActionApiMap((prev) => {
                      const row = { ...(prev[settingProfile] || {}) };
                      for (const action of next) {
                        for (const slot of apiKeysForBindAction(action)) {
                          if (row[slot]) continue;
                          const picked = resolveActionApiUuidRef.current?.(slot, saveApis);
                          if (picked) row[slot] = picked;
                        }
                      }
                      return { ...prev, [settingProfile]: row };
                    });
                  }
                }}
              />
              {perActionApiBinding ? (
                <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
                  {t('app.kuaizhizao.documentPush.batch.bindActionsPerApiHint')}
                </Typography.Text>
              ) : null}
            </div>
            {perActionApiBinding &&
            !multiApiTargetRows &&
            effectiveBindActionsForProfile(settingProfile).length > 0 &&
            (destinationKinds[settingProfile] ?? 'api') === 'api' &&
            kingdeeProfiles.includes(profileForBindingKey(settingProfile))
              ? effectiveBindActionsForProfile(settingProfile).flatMap((action) =>
                  apiKeysForBindAction(action).map((slot) => (
                    <React.Fragment key={`${action}-${slot}`}>
                      <Typography.Text
                        type="secondary"
                        style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}
                      >
                        {t(`app.kuaizhizao.documentPush.batch.actionApi.${slot}`, slot)}
                      </Typography.Text>
                      <Select
                        style={{ width: '100%', maxWidth: 520 }}
                        loading={apisLoading}
                        placeholder={t('app.kuaizhizao.documentPush.batch.apiPlaceholder')}
                        options={apiOptions}
                        value={targetActionApiMap[settingProfile]?.[slot]}
                        onChange={(value) => {
                          setTargetActionApiMap((prev) => ({
                            ...prev,
                            [settingProfile]: { ...(prev[settingProfile] || {}), [slot]: value },
                          }));
                          if (slot === 'confirm') {
                            setSaveApiUuid(value);
                            setSaveApiUuids((prev) => ({ ...prev, [settingProfile]: value }));
                          }
                        }}
                        allowClear={false}
                        showSearch
                        optionFilterProp="label"
                        notFoundContent={t('app.kuaizhizao.documentPush.batch.apiEmpty')}
                      />
                    </React.Fragment>
                  )),
                )
              : null}
          </>
        ) : null}
        {(destinationKinds[settingProfile] ?? 'api') === 'data_source' ? (
          <>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}>
              {t('app.kuaizhizao.documentPush.batch.destinationDataSource')}
            </Typography.Text>
            <Select
              style={{ width: '100%', maxWidth: 520 }}
              loading={dataSourcesLoading}
              placeholder={t('app.kuaizhizao.documentPush.batch.dataSourcePlaceholder')}
              options={dataSources.map((row) => ({
                value: row.uuid,
                label: row.name ? `${row.name}（${row.code}）` : row.code,
              }))}
              value={dataSourceUuids[settingProfile]}
              onChange={(value) =>
                setDataSourceUuids((prev) => ({ ...prev, [settingProfile]: value }))
              }
              allowClear={false}
              showSearch
              optionFilterProp="label"
              notFoundContent={t('app.kuaizhizao.documentPush.batch.dataSourceEmpty')}
            />
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}>
              {t('app.kuaizhizao.documentPush.batch.writeDatasetPlaceholder')}
            </Typography.Text>
            <Select
              style={{ width: '100%', maxWidth: 520 }}
              placeholder={t('app.kuaizhizao.documentPush.batch.writeDatasetPlaceholder')}
              options={writeDatasets
                .filter((row) => !dataSourceUuids[settingProfile] || row.data_source_uuid === dataSourceUuids[settingProfile])
                .map((row) => ({
                  value: row.uuid,
                  label: row.name ? `${row.name}（${row.code}）` : row.code,
                }))}
              value={datasetUuids[settingProfile]}
              onChange={(value) =>
                setDatasetUuids((prev) => ({ ...prev, [settingProfile]: value }))
              }
              allowClear={false}
              showSearch
              optionFilterProp="label"
              notFoundContent={t('app.kuaizhizao.documentPush.batch.writeDatasetEmpty')}
            />
          </>
        ) : null}
        {(destinationKinds[settingProfile] ?? 'api') === 'api' &&
        kingdeeProfiles.includes(profileForBindingKey(settingProfile)) ? (
          <>
        <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}>
          {t('app.kuaizhizao.documentPush.batch.connectorPlaceholder')}
        </Typography.Text>
        <Select
          style={{ width: '100%', maxWidth: 520 }}
          loading={connectorsLoading}
          placeholder={t('app.kuaizhizao.documentPush.batch.connectorPlaceholder')}
          options={connectorOptions}
          value={connectionCode}
          onChange={(value) => setConnectionCode(value)}
          allowClear={false}
          showSearch
          optionFilterProp="label"
          notFoundContent={t('app.kuaizhizao.documentPush.batch.connectorEmpty')}
        />
        {!perActionApiBinding || multiApiTargetRows ? (
          <>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap', lineHeight: '32px' }}>
              {t('app.kuaizhizao.documentPush.batch.apiPlaceholder')}
            </Typography.Text>
            <Select
              style={{ width: '100%', maxWidth: 520 }}
              loading={apisLoading}
              placeholder={t('app.kuaizhizao.documentPush.batch.apiPlaceholder')}
              options={apiOptions}
              value={saveApiUuid}
              onChange={(value) => {
                setSaveApiUuid(value);
                if (settingProfile) {
                  setSaveApiUuids((prev) => ({ ...prev, [settingProfile]: value }));
                }
              }}
              allowClear={false}
              showSearch
              optionFilterProp="label"
              notFoundContent={t('app.kuaizhizao.documentPush.batch.apiEmpty')}
            />
          </>
        ) : null}
          </>
        ) : null}
      </div>
      {(destinationKinds[settingProfile] ?? 'api') === 'api' &&
      kingdeeProfiles.includes(profileForBindingKey(settingProfile)) &&
      !connectionCode ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 12 }}
          title={t('app.kuaizhizao.documentPush.batch.needConnector')}
        />
      ) : null}
      {(destinationKinds[settingProfile] ?? 'api') === 'data_source' &&
      !dataSourceUuids[settingProfile] ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 12 }}
          title={t('app.kuaizhizao.documentPush.batch.needDataSource')}
        />
      ) : null}
      {(destinationKinds[settingProfile] ?? 'api') === 'data_source' &&
      dataSourceUuids[settingProfile] &&
      !datasetUuids[settingProfile] ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 12 }}
          title={t('app.kuaizhizao.documentPush.batch.needWriteDataset')}
        />
      ) : null}
      {(destinationKinds[settingProfile] ?? 'api') === 'data_source' &&
      datasetUuids[settingProfile] ? (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 12 }}
          title={t('app.kuaizhizao.documentPush.batch.writeDatasetNoted')}
        />
      ) : null}
      {(targetModes[settingProfile] ?? 'auto') === 'manual' ? (
        <div style={{ marginTop: 16 }}>
          <UniPullQueryModal<T>
            open
            embedded
            hideFooter
            title={title}
            onCancel={() => closeTargetSetting(false)}
            onOk={pull.handleConfirm}
            confirmLoading={pull.confirmLoading}
            rowKey="id"
            columns={columns}
            dataSource={pull.dataSource}
            loading={pull.loading}
            selectionType="checkbox"
            selectedRowKeys={pull.selectedRowKeys}
            onSelectedRowKeysChange={pull.handleSelectedRowKeysChange}
            selectedRows={pull.selectedRows}
            getRowLabel={getRowLabel}
            searchDraft={pull.searchDraft}
            onSearchDraftChange={pull.setSearchDraft}
            onSearchApply={pull.handleSearchApply}
            onSearchClear={pull.handleSearchClear}
            appliedKeyword={pull.appliedKeyword}
            searchPlaceholder={searchPlaceholder}
            page={pull.page}
            pageSize={pull.pageSize}
            total={pull.total}
            onPageChange={pull.handlePageChange}
          />
        </div>
      ) : null}
    </Modal>
  ) : null;

  if (!open) return null;

  const targetRows = listBindingKeys.map((bindingKey, index) => {
    const profile = profileForBindingKey(bindingKey);
    const kind = destinationKinds[bindingKey] ?? 'api';
    let name = profileLabel(profile);
    if (kind === 'api' && kingdeeProfiles.includes(profile)) {
      const apiUuid = pickSaveApiUuidForProfile(bindingKey, saveApiUuid);
      const api = saveApis.find((row) => row.uuid === apiUuid);
      if (api?.name) name = api.name;
      else if (api?.code) name = api.code;
    } else if (kind === 'data_source') {
      const dataset = writeDatasets.find((row) => row.uuid === datasetUuids[bindingKey]);
      const dataSource = dataSources.find((row) => row.uuid === dataSourceUuids[bindingKey]);
      if (dataset?.name) name = dataset.name;
      else if (dataset?.code) name = dataset.code;
      else if (dataSource?.name) name = dataSource.name;
      else if (dataSource?.code) name = dataSource.code;
    }
    let bindBehavior = '—';
    if (multiApiTargetRows) {
      const slot = apiSlotForBindingKey(bindingKey);
      bindBehavior = bindingSlotLabel(slot);
    } else {
      const mode = targetModes[bindingKey] ?? 'auto';
      const actions =
        mode === 'auto'
          ? targetActionMap[bindingKey]?.length
            ? targetActionMap[bindingKey]
            : defaultAutoBindActions
          : targetActionMap[bindingKey] || [];
      const labels = actions
        .map(
          (action) =>
            resolvedBindActionOptions.find((option) => option.value === action)?.label || action,
        )
        .filter(Boolean);
      if (labels.length) bindBehavior = labels.join('、');
    }
    return {
      key: bindingKey,
      index: index + 1,
      profile: bindingKey,
      name,
      bindBehavior,
    };
  });

  const addTarget = () => {
    if (multiApiTargetRows) {
      const profile =
        kingdeeProfiles.find((p) => allowedProfileSet.has(p)) ||
        profileOptions.find((option) => allowedProfileSet.has(option.value))?.value;
      if (!profile) {
        messageApi.info(t('app.kuaizhizao.documentPush.batch.noProfiles'));
        return;
      }
      const rowKey = createBindingRowKey();
      const usedSlots = new Set(
        targetRowKeys.map((k) => rowBindingMeta[k]?.apiSlot).filter(Boolean),
      );
      const nextSlot =
        resolvedApiBindingSlotOptions.find((option) => !usedSlots.has(option.value))?.value ||
        'confirm';
      setRowBindingMeta((prev) => ({ ...prev, [rowKey]: { profile, apiSlot: nextSlot } }));
      setPendingNewProfile(rowKey);
      setTargetModes((prev) => ({ ...prev, [rowKey]: 'auto' }));
      setDestinationKinds((prev) => ({ ...prev, [rowKey]: 'api' }));
      setTargetActionMap((prev) => ({
        ...prev,
        [rowKey]: triggerActionsForBindingSlot(nextSlot),
      }));
      openTargetSetting(rowKey);
      return;
    }
    const preferred = (defaultProfilesRef.current || []).filter(Boolean);
    const used = new Set([...targetProfiles, pendingNewProfile].filter(Boolean) as string[]);
    const next =
      preferred
        .map((value) => profileOptions.find((option) => option.value === value))
        .find((option) => option && !used.has(option.value)) ||
      profileOptions.find((option) => !used.has(option.value));
    if (!next) {
      if (perActionApiBinding && targetProfiles.length === 1) {
        messageApi.info(t('app.kuaizhizao.documentPush.batch.noMoreTargetsUseSettings'));
        openTargetSetting(targetProfiles[0]);
        return;
      }
      messageApi.info(t('app.kuaizhizao.documentPush.batch.noMoreTargets'));
      return;
    }
    setPendingNewProfile(next.value);
    setTargetModes((prev) => ({ ...prev, [next.value]: prev[next.value] ?? 'auto' }));
    setTargetActionMap((prev) => ({
      ...prev,
      [next.value]: prev[next.value]?.length ? prev[next.value] : defaultAutoBindActions,
    }));
    openTargetSetting(next.value);
  };

  const confirmAuto = async () => {
    const hasTargets = multiApiTargetRows ? targetRowKeys.length > 0 : targetProfiles.length > 0;
    if (hasTargets && !pushReady) {
      Modal.warning({
        title,
        content: notReadyReason || t('components.syncPushHub.pushNotReady'),
      });
      return;
    }
    if (!saveBinding) {
      messageApi.info(t('app.kuaizhizao.documentPush.batch.autoNeedBinding'));
      return;
    }
    if (!rememberBinding) {
      messageApi.warning(t('app.kuaizhizao.documentPush.batch.needRememberBinding'));
      return;
    }
    const bindingKeys = listBindingKeys.filter((key) =>
      allowedProfileSet.has(profileForBindingKey(key)),
    );
    if (!bindingKeys.length) {
      Modal.warning({
        title,
        content: t('app.kuaizhizao.documentPush.batch.targetsEmpty'),
      });
      return;
    }
    if (
      bindingKeys.some(
        (key) =>
          (destinationKinds[key] ?? 'api') === 'data_source' && !dataSourceUuids[key],
      )
    ) {
      Modal.warning({
        title,
        content: t('app.kuaizhizao.documentPush.batch.needDataSource'),
      });
      return;
    }
    if (
      bindingKeys.some(
        (key) => (destinationKinds[key] ?? 'api') === 'data_source' && !datasetUuids[key],
      )
    ) {
      Modal.warning({
        title,
        content: t('app.kuaizhizao.documentPush.batch.needWriteDataset'),
      });
      return;
    }
    const configBlock = bindingKeys.map((key) => profileConfigNotReadyReason(key)).find(Boolean);
    if (configBlock) {
      Modal.warning({
        title,
        content: configBlock,
      });
      return;
    }
    const bound = bindingKeys.map((key) => {
      const profile = profileForBindingKey(key);
      const mode = targetModes[key] ?? 'auto';
      if (multiApiTargetRows) {
        const slot = apiSlotForBindingKey(key);
        const saveUuid = pickSaveApiUuidForProfile(key, saveApiUuid);
        const actions =
          mode === 'auto' ? triggerActionsForBindingSlot(slot) : targetActionMap[key] || [];
        return {
          target_profile: profile,
          push_mode: mode,
          destination_kind: destinationKinds[key] ?? 'api',
          data_source_uuid:
            (destinationKinds[key] ?? 'api') === 'data_source' ? dataSourceUuids[key] : undefined,
          dataset_uuid:
            (destinationKinds[key] ?? 'api') === 'data_source' ? datasetUuids[key] : undefined,
          trigger_actions: actions,
          action_apis: saveUuid ? { [slot]: saveUuid } : undefined,
          connection_code:
            kingdeeProfiles.includes(profile) && (destinationKinds[key] ?? 'api') === 'api'
              ? connectionCode
              : undefined,
          save_api_uuid: saveUuid,
          user_saved: true,
          push_enabled: !autoPushPaused,
        };
      }
      const actions =
        mode === 'auto'
          ? targetActionMap[key]?.length
            ? targetActionMap[key]
            : defaultAutoBindActions
          : [];
      const actionApis = perActionApiBinding
        ? buildActionApisForProfile(key, actions)
        : undefined;
      const saveUuid =
        actionApis?.confirm ||
        (kingdeeProfiles.includes(profile) && (destinationKinds[key] ?? 'api') === 'api'
          ? pickSaveApiUuidForProfile(key, saveApiUuid)
          : undefined);
      return {
        target_profile: profile,
        push_mode: mode,
        destination_kind: destinationKinds[key] ?? 'api',
        data_source_uuid:
          (destinationKinds[key] ?? 'api') === 'data_source' ? dataSourceUuids[key] : undefined,
        dataset_uuid:
          (destinationKinds[key] ?? 'api') === 'data_source' ? datasetUuids[key] : undefined,
        trigger_actions: actions,
        action_apis: actionApis,
        connection_code:
          kingdeeProfiles.includes(profile) && (destinationKinds[key] ?? 'api') === 'api'
            ? connectionCode
            : undefined,
        save_api_uuid: saveUuid,
        user_saved: true,
        push_enabled: !autoPushPaused,
      };
    });
    try {
      await saveBinding({
        targets: bound,
        trigger_actions: [...new Set(bound.flatMap((row) => row.trigger_actions))],
        connection_code: connectionCode,
        save_api_uuid: saveApiUuid,
        sync_mode: syncMode,
        schedule_interval_minutes: scheduleIntervalMinutes,
      });
      messageApi.success(t('app.kuaizhizao.documentPush.batch.autoSaved'));
      onClose();
      onComplete?.();
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.documentPush.batch.autoSaveFailed')));
    }
  };

  const toggleAutoPushPause = async () => {
    if (!saveBinding) {
      messageApi.warning(t('app.kuaizhizao.documentPush.batch.autoNeedBinding'));
      return;
    }
    if (!rememberBinding) {
      messageApi.warning(t('app.kuaizhizao.documentPush.batch.needRememberBinding'));
      return;
    }
    const nextPaused = !autoPushPaused;
    setAutoPushPauseLoading(true);
    try {
      // 复用确认保存路径：先切本地状态再落库
      setAutoPushPaused(nextPaused);
      // 构造与 confirmAuto 相同的 bound 较重；此处直接改已加载目标再保存
      const binding = loadBinding ? await loadBinding() : null;
      const existing = (binding?.targets || []).filter(
        (row) => row && row.user_saved !== false && row.target_profile,
      );
      if (!existing.length && !targetRows.length) {
        setAutoPushPaused(!nextPaused);
        messageApi.warning(t('components.syncPushHub.autoPushPauseNeedTargets'));
        return;
      }
      if (existing.length) {
        await saveBinding({
          targets: existing.map((row) => ({
            ...row,
            user_saved: true,
            push_enabled: !nextPaused,
          })),
          trigger_actions: binding?.trigger_actions || [
            ...new Set(existing.flatMap((row) => row.trigger_actions || [])),
          ],
          connection_code: binding?.connection_code || connectionCode,
          save_api_uuid: binding?.save_api_uuid || saveApiUuid,
          sync_mode: binding?.sync_mode || syncMode,
          schedule_interval_minutes:
            binding?.schedule_interval_minutes || scheduleIntervalMinutes,
        });
      } else {
        // 面板有未确认行：只切本地，点确认时写入 push_enabled
        messageApi.info(
          nextPaused
            ? t('app.kuaizhizao.documentPush.batch.autoPushPausedLocalOnly')
            : t('app.kuaizhizao.documentPush.batch.autoPushResumedLocalOnly'),
        );
        return;
      }
      messageApi.success(
        nextPaused
          ? t('components.syncPushHub.autoPushPaused')
          : t('components.syncPushHub.autoPushResumed'),
      );
    } catch (error: unknown) {
      setAutoPushPaused(!nextPaused);
      messageApi.error(
        getApiErrorMessage(error, t('components.syncPushHub.autoPushPauseFailed')),
      );
    } finally {
      setAutoPushPauseLoading(false);
    }
  };

  const footer = (
    <Flex justify="flex-end" gap={8}>
      <Button onClick={onClose}>{t('common.cancel')}</Button>
      <Button
        type="primary"
        onClick={() => {
          void confirmAuto();
        }}
      >
        {t('app.kuaizhizao.documentPush.batch.confirmAuto')}
      </Button>
    </Flex>
  );

  const body = (
    <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
      {hint ? <Alert type="info" showIcon title={hint} /> : null}
      {autoPushPaused ? (
        <Alert type="warning" showIcon title={t('app.kuaizhizao.documentPush.batch.autoPushPausedBanner')} />
      ) : null}
      <Flex justify="space-between" align="center" gap={12} wrap="wrap">
        <Space size={8} wrap align="center" style={{ flex: 1, minWidth: 200 }}>
          <Typography.Text strong>{t('app.kuaizhizao.documentPush.batch.targetProfiles')}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12, lineHeight: 1.5 }}>
            {multiApiTargetRows
              ? t('app.kuaizhizao.documentPush.batch.targetsHintMultiApiRows')
              : perActionApiBinding
                ? t('app.kuaizhizao.documentPush.batch.targetsHintPerAction')
                : t('app.kuaizhizao.documentPush.batch.targetsHint')}
          </Typography.Text>
        </Space>
        <Space wrap>
          {saveBinding ? (
            <Button
              icon={autoPushPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
              danger={autoPushPaused}
              type={autoPushPaused ? 'primary' : 'default'}
              loading={autoPushPauseLoading}
              onClick={() => {
                void toggleAutoPushPause();
              }}
            >
              {autoPushPaused
                ? t('components.syncPushHub.autoPushResume')
                : t('components.syncPushHub.autoPushPause')}
            </Button>
          ) : null}
          <Button icon={<PlusOutlined />} onClick={addTarget} disabled={profilesLoading}>
            {t('app.kuaizhizao.documentPush.batch.addTarget')}
          </Button>
          <Checkbox checked={rememberBinding} onChange={(event) => setRememberBinding(event.target.checked)}>
            {t('app.kuaizhizao.documentPush.batch.rememberBinding')}
          </Checkbox>
        </Space>
      </Flex>
      <Table
        size="small"
        pagination={false}
        rowKey="key"
        dataSource={targetRows}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('app.kuaizhizao.documentPush.batch.targetsEmpty')}
            />
          ),
        }}
        columns={[
          {
            title: t('components.syncFromSource.sourceIndex'),
            dataIndex: 'index',
            width: 56,
          },
          {
            title: t('components.syncFromSource.sourceKind'),
            dataIndex: 'profile',
            width: 120,
            render: (profile: string) =>
              (destinationKinds[profile] ?? 'api') === 'data_source'
                ? t('app.kuaizhizao.documentPush.batch.destinationDataset')
                : t('app.kuaizhizao.documentPush.batch.apiPlaceholder'),
          },
          {
            title: t('components.syncFromSource.sourceName'),
            dataIndex: 'name',
            ellipsis: true,
          },
          {
            title: t('app.kuaizhizao.documentPush.batch.modeLabel'),
            dataIndex: 'profile',
            width: 96,
            render: (profile: string) =>
              (targetModes[profile] ?? 'auto') === 'manual'
                ? t('app.kuaizhizao.documentPush.batch.modeManual')
                : t('app.kuaizhizao.documentPush.batch.modeAuto'),
          },
          {
            title: t('app.kuaizhizao.documentPush.batch.bindBehaviorCol'),
            dataIndex: 'bindBehavior',
            width: 112,
            ellipsis: true,
          },
          {
            title: t('common.actions'),
            key: 'actions',
            width: 140,
            render: (_value, record: { profile: string }) => (
              <Space size="small">
                  <Button
                    type="link"
                    size="small"
                    onClick={() => openTargetSetting(record.profile)}
                  >
                    {t('components.syncFromSource.configureSource')}
                  </Button>
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => {
                    if (multiApiTargetRows) {
                      setTargetRowKeys((prev) => prev.filter((item) => item !== record.profile));
                      setRowBindingMeta((prev) => {
                        const next = { ...prev };
                        delete next[record.profile];
                        return next;
                      });
                    } else {
                      setTargetProfiles((prev) => prev.filter((item) => item !== record.profile));
                    }
                    if (settingProfile === record.profile) setSettingProfile(null);
                  }}
                />
              </Space>
            ),
          },
        ]}
      />
    </Space>
  );

  if (!embedded) {
    return (
      <Modal
        title={title}
        open={open}
        onCancel={onClose}
        width={1100}
        destroyOnHidden
        footer={footer}
      >
        {body}
        {settingModal}
      </Modal>
    );
  }

  return (
    <div>
      {body}
      <div style={{ marginTop: 16 }}>{footer}</div>
      {settingModal}
    </div>
  );
}

export default DocumentPushBatchPanel;
