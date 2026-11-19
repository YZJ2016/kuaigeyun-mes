/**
 * 通用同步弹窗：数据接口 / 数据集 + 字段映射
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App,
  Button,
  Checkbox,
  Empty,
  Modal,
  Progress,
  Select,
  Space,
  Steps,
  Switch,
  Table,
  Tabs,
  TimePicker,
  Tooltip,
  Typography,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { SyncRunHistoryPanel } from '../sync-push-hub/SyncRunHistoryPanel';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { loadAllActiveApis } from '../../utils/activeApiSelectOptions';
import { getCustomFieldsByTable } from '../../services/customField';
import { getDatasetList } from '../../services/dataset';
import { formatDateTimeBySiteSetting } from '../../utils/format';
import {
  formatSyncErrorMessage,
  isInactiveSyncSourceError,
} from './syncSourceUtils';
import { SyncSourceSettingModal } from './SyncSourceSettingModal';
import { createDefaultSyncRunHistoryLoader } from './syncRunHistory';
import type {
  SyncBinding,
  SyncFromSourceConfig,
  SyncFromSourceResult,
  SyncProgressItem,
  SyncSourceType,
  SyncTargetField,
} from './types';
import { syncCustomFieldTargetKey } from './types';
import {
  bindingToSourceDrafts,
  draftsToPayloadSources,
  newSyncSourceDraft,
  type SyncSourceDraft,
} from './syncSourcesDraft';

export type { SyncFromSourceConfig, SyncFromSourceResult, SyncSourceType } from './types';

function resolveDraftDisplayName(
  draft: SyncSourceDraft,
  apiOptions: { label: string; value: string }[],
  datasetOptions: { label: string; value: string }[],
  t: (key: string) => string,
): string {
  if (draft.kind === 'api' && draft.api_uuid) {
    return apiOptions.find((item) => item.value === draft.api_uuid)?.label ?? draft.api_uuid;
  }
  if (draft.kind === 'dataset' && draft.dataset_uuid) {
    return datasetOptions.find((item) => item.value === draft.dataset_uuid)?.label ?? draft.dataset_uuid;
  }
  return t('components.syncFromSource.sourceNotConfigured');
}

function countMappedFields(draft: SyncSourceDraft): number {
  return Object.values(draft.targetToSource).filter(Boolean).length;
}

function buildScheduleWindowFields(window: [Dayjs, Dayjs] | null): {
  schedule_window_start: string | null;
  schedule_window_end: string | null;
} {
  if (!window) {
    return { schedule_window_start: null, schedule_window_end: null };
  }
  return {
    schedule_window_start: window[0].format('HH:mm'),
    schedule_window_end: window[1].format('HH:mm'),
  };
}

function mappingPairLines(
  draft: SyncSourceDraft,
  fieldByValue: Map<string, SyncTargetField>,
  t: (key: string) => string,
): string[] {
  return Object.entries(draft.targetToSource)
    .filter(([, source]) => Boolean(source))
    .map(([target, source]) => {
      const field = fieldByValue.get(target);
      const label = field?.label?.trim() || (field?.labelKey ? t(field.labelKey) : target);
      return `${label} ← ${source}`;
    });
}

function apiCodeMatchesPreferredSuffix(code: string, suffix: string): boolean {
  const normalized = String(code || '').trim().toLowerCase();
  const preferred = String(suffix || '').trim().toLowerCase();
  return (
    Boolean(normalized) &&
    Boolean(preferred) &&
    (normalized === preferred || normalized.endsWith(`_${preferred}`))
  );
}

function preferredTokenRank(haystack: string, tokens: string[]): number {
  const hay = String(haystack || '').trim().toLowerCase().replace(/\\/g, '/');
  if (!tokens.length) return 0;
  const index = tokens.findIndex((token) => token && hay.includes(token));
  return index >= 0 ? index : tokens.length;
}

function preferredApiCodeSuffixRank(code: string, preferredSuffixes: string[]): number {
  if (!preferredSuffixes.length) return 0;
  const index = preferredSuffixes.findIndex((suffix) =>
    apiCodeMatchesPreferredSuffix(code, suffix),
  );
  return index >= 0 ? index : preferredSuffixes.length;
}

/** 连接器 type → path 族 → code 后缀；任一层未配置则该层不计分 */
function preferredApiSortKey(
  api: { code: string; path?: string | null; connection_type?: string | null },
  preferredSuffixes: string[],
  preferredPathTokens: string[],
  preferredConnectorTypes: string[],
): [number, number, number] {
  return [
    preferredTokenRank(String(api.connection_type || ''), preferredConnectorTypes),
    preferredTokenRank(String(api.path || ''), preferredPathTokens),
    preferredApiCodeSuffixRank(api.code, preferredSuffixes),
  ];
}

function isPreferredApiHit(
  api: { code: string; path?: string | null; connection_type?: string | null },
  preferredSuffixes: string[],
  preferredPathTokens: string[],
  preferredConnectorTypes: string[],
): boolean {
  const [connRank, pathRank, suffixRank] = preferredApiSortKey(
    api,
    preferredSuffixes,
    preferredPathTokens,
    preferredConnectorTypes,
  );
  const anyConfigured =
    preferredConnectorTypes.length > 0 ||
    preferredPathTokens.length > 0 ||
    preferredSuffixes.length > 0;
  if (!anyConfigured) return false;
  // 后缀 / path 已配置则必须命中；连接器 type 仅在接口已带回 type 时强制（无 type 仍可靠 path）
  if (preferredSuffixes.length && suffixRank >= preferredSuffixes.length) return false;
  if (preferredPathTokens.length && pathRank >= preferredPathTokens.length) return false;
  if (
    preferredConnectorTypes.length &&
    String(api.connection_type || '').trim() &&
    connRank >= preferredConnectorTypes.length
  ) {
    return false;
  }
  return true;
}

/**
 * 多行表单项共用一列标签宽：按本块最长标签自动撑开（4 字/5 字都齐），禁止换行。
 * 勿再写死像素宽——字数变化会挤换行或对不齐。
 */
const SYNC_FIELD_GRID_STYLE: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'max-content minmax(0, 1fr)',
  columnGap: 12,
  rowGap: 12,
  alignItems: 'center',
  width: '100%',
};

const SYNC_FIELD_LABEL_STYLE: React.CSSProperties = {
  whiteSpace: 'nowrap',
  lineHeight: '32px',
};

const SYNC_FIELD_CONTROL_STYLE: React.CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 12,
  alignItems: 'center',
  minWidth: 0,
};

export interface SyncFromSourceModalProps {
  open: boolean;
  onClose: () => void;
  config: SyncFromSourceConfig;
  onComplete?: (result: SyncFromSourceResult) => void;
  zIndex?: number;
  /** 仅渲染内容区，供同步中心内嵌；拉取请求与独立弹窗相同。 */
  contentOnly?: boolean;
}

export const SyncFromSourceModal: React.FC<SyncFromSourceModalProps> = ({
  open,
  onClose,
  config,
  onComplete,
  zIndex,
  contentOnly = false,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();

  const [apiOptions, setApiOptions] = useState<{ label: string; value: string }[]>([]);
  const [defaultPreferredApiUuid, setDefaultPreferredApiUuid] = useState<string | undefined>();
  const [datasetOptions, setDatasetOptions] = useState<{ label: string; value: string }[]>([]);
  const [sourceDrafts, setSourceDrafts] = useState<SyncSourceDraft[]>(() => []);
  const [settingSourceId, setSettingSourceId] = useState<string | null>(null);
  /** 添加来源：保存前仅存在于设置弹窗，不入列表 */
  const [pendingNewSourceDraft, setPendingNewSourceDraft] = useState<SyncSourceDraft | null>(null);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncElapsedSec, setSyncElapsedSec] = useState(0);
  const [saveBinding, setSaveBinding] = useState(true);
  const [activeOnly, setActiveOnly] = useState(true);
  const [inferParentByCode, setInferParentByCode] = useState(false);
  const [syncMode, setSyncMode] = useState<string>('manual_full');
  const [scheduleIntervalMinutes, setScheduleIntervalMinutes] = useState<number>(15);
  const [scheduleWindow, setScheduleWindow] = useState<[Dayjs, Dayjs] | null>(null);
  const [bindingMeta, setBindingMeta] = useState<Pick<
    SyncBinding,
    'last_success_at' | 'last_attempt_at' | 'last_error'
  > | null>(null);
  const [syncProgress, setSyncProgress] = useState<SyncProgressItem[]>([]);
  /** 异步加载的可选字段（含自定义字段） */
  const [loadedAvailableFields, setLoadedAvailableFields] = useState<SyncTargetField[]>([]);
  const historySource = String(config.historySourceType || '').trim();
  const resolvedListSyncRunHistory = useMemo(
    () =>
      config.listSyncRunHistory ??
      (historySource ? createDefaultSyncRunHistoryLoader(historySource) : undefined),
    [config.listSyncRunHistory, historySource],
  );
  const showHistoryTab = Boolean(historySource && resolvedListSyncRunHistory);
  type SyncFromSourceTabKey = 'sync' | 'history';
  const [activeTab, setActiveTab] = useState<SyncFromSourceTabKey>('sync');
  const [lastOpen, setLastOpen] = useState(false);
  const openingEdge = open && !lastOpen;

  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setActiveTab('sync');
    }
  }

  const panelTab: SyncFromSourceTabKey = openingEdge ? 'sync' : activeTab;
  const syncTabActive = open && panelTab === 'sync';
  const historyTabActive = open && panelTab === 'history';
  const [historyRefreshNonce, setHistoryRefreshNonce] = useState(0);

  useEffect(() => {
    if (!syncing) {
      setSyncElapsedSec(0);
      return;
    }
    const startedAt = Date.now();
    setSyncElapsedSec(0);
    const timer = window.setInterval(() => {
      setSyncElapsedSec(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [syncing]);

  const syncProgressPercent = useMemo(() => {
    if (syncProgress.length === 0) return 0;
    const settled = syncProgress.filter((step) =>
      step.status === 'finish' || step.status === 'error' || step.status === 'skip',
    ).length;
    const inProcess = syncProgress.some((step) => step.status === 'process');
    const units = settled + (inProcess ? 0.5 : 0);
    return Math.min(100, Math.round((units / syncProgress.length) * 100));
  }, [syncProgress]);

  const syncProgressStatus = useMemo(() => {
    if (syncProgress.some((step) => step.status === 'error')) return 'exception' as const;
    if (syncing) return 'active' as const;
    // 停用等软中断：进度条保持普通态，不用成功绿/危险红
    if (syncProgress.some((step) => step.status === 'skip')) return 'normal' as const;
    if (
      syncProgress.length > 0 &&
      syncProgress.every((step) => step.status === 'finish')
    ) {
      return 'success' as const;
    }
    return 'normal' as const;
  }, [syncProgress, syncing]);

  const syncCurrentStepTitle = useMemo(() => {
    const current = syncProgress.find((step) => step.status === 'process');
    return current ? t(current.titleKey) : null;
  }, [syncProgress, t]);

  const syncProgressHeaderHint = useMemo(() => {
    if (syncing) {
      if (syncCurrentStepTitle) {
        return `${t('components.syncFromSource.syncProgressCurrent', {
          step: syncCurrentStepTitle,
        })} · ${t('components.syncFromSource.syncProgressElapsed', {
          seconds: syncElapsedSec,
        })}`;
      }
      return `${t('components.syncFromSource.syncingInProgress')} · ${t(
        'components.syncFromSource.syncProgressElapsed',
        { seconds: syncElapsedSec },
      )}`;
    }
    if (syncProgress.some((step) => step.status === 'error')) {
      return t(config.failedKey);
    }
    if (syncProgress.some((step) => step.status === 'skip')) {
      return t('components.syncFromSource.inactiveSourceHint');
    }
    if (
      syncProgress.length > 0 &&
      syncProgress.every((step) => step.status === 'finish')
    ) {
      return t('components.syncFromSource.syncProgressDone');
    }
    return null;
  }, [config.failedKey, syncCurrentStepTitle, syncElapsedSec, syncProgress, syncing, t]);

  const formatStepResult = useCallback(
    (result: SyncFromSourceResult) => {
      const modeLabel =
        result.mode === 'incremental'
          ? t('components.syncFromSource.stepModeIncremental')
          : result.mode === 'full'
            ? t('components.syncFromSource.stepModeFull')
            : null;
      const fetched =
        typeof result.fetched === 'number'
          ? t('components.syncFromSource.stepFetched', { count: result.fetched })
          : null;
      const counts = t('components.syncFromSource.prerequisiteStepResult', {
        created: result.created,
        updated: result.updated,
        skipped: result.skipped,
        failed: result.failed,
      });
      const head = [modeLabel, fetched].filter(Boolean).join(' · ');
      let text = head ? `${head} · ${counts}` : counts;
      if (
        typeof result.fetched === 'number' &&
        result.fetched === 0 &&
        result.mode === 'incremental' &&
        result.created + result.updated + result.failed === 0
      ) {
        text = `${text}；${t('components.syncFromSource.stepIncrementalEmpty')}`;
      }
      if (result.failed > 0 && result.errors?.length) {
        const sample = result.errors.slice(0, 2).join('；');
        text = `${text}；${sample}`;
      }
      return text;
    },
    [t],
  );

  const hasAnySavedMapping = useMemo(
    () => sourceDrafts.some((draft) => Object.keys(draft.targetToSource).length > 0),
    [sourceDrafts],
  );

  const fieldByValue = useMemo(() => {
    const map = new Map<string, SyncTargetField>();
    for (const field of [
      ...config.targetFields,
      ...(config.availableTargetFields ?? []),
      ...loadedAvailableFields,
    ]) {
      if (!map.has(field.value)) map.set(field.value, field);
    }
    return map;
  }, [config.availableTargetFields, config.targetFields, loadedAvailableFields]);

  const editingDraft = useMemo(() => {
    if (!settingSourceId) return null;
    const fromList = sourceDrafts.find((row) => row.id === settingSourceId);
    if (fromList) return fromList;
    if (pendingNewSourceDraft?.id === settingSourceId) return pendingNewSourceDraft;
    return null;
  }, [pendingNewSourceDraft, sourceDrafts, settingSourceId]);

  const closeSourceSetting = useCallback(() => {
    setSettingSourceId(null);
    setPendingNewSourceDraft(null);
  }, []);

  const loadOptions = useCallback(async () => {
    setLoadingOptions(true);
    try {
      const preferredSuffixes = (config.preferredApiCodeSuffixes || [])
        .map((item) => String(item || '').trim().toLowerCase())
        .filter(Boolean);
      const preferredPathTokens = (config.preferredApiPathTokens || [])
        .map((item) => String(item || '').trim().toLowerCase().replace(/\\/g, '/'))
        .filter(Boolean);
      const preferredConnectorTypes = (config.preferredConnectorTypes || [])
        .map((item) => String(item || '').trim().toLowerCase())
        .filter(Boolean);
      const apiOpts: {
        label: string;
        value: string;
        code: string;
        path: string;
        connection_type: string;
      }[] = (await loadAllActiveApis()).map((item) => ({
        label: `${item.name} (${item.code})`,
        value: item.uuid,
        code: String(item.code || ''),
        path: String(item.path || ''),
        connection_type: String(item.connection_type || ''),
      }));
      // 单位/物料等：连接器 type → path 族 → code 后缀，默认选中首个命中项
      let preferredUuid: string | undefined;
      const hasPreference =
        preferredSuffixes.length > 0 ||
        preferredPathTokens.length > 0 ||
        preferredConnectorTypes.length > 0;
      if (hasPreference) {
        apiOpts.sort((a, b) => {
          const aKey = preferredApiSortKey(
            a,
            preferredSuffixes,
            preferredPathTokens,
            preferredConnectorTypes,
          );
          const bKey = preferredApiSortKey(
            b,
            preferredSuffixes,
            preferredPathTokens,
            preferredConnectorTypes,
          );
          for (let i = 0; i < aKey.length; i += 1) {
            if (aKey[i] !== bKey[i]) return aKey[i] - bKey[i];
          }
          return a.label.localeCompare(b.label, 'zh-CN');
        });
        preferredUuid = apiOpts.find((item) =>
          isPreferredApiHit(
            item,
            preferredSuffixes,
            preferredPathTokens,
            preferredConnectorTypes,
          ),
        )?.value;
      }
      setDefaultPreferredApiUuid(preferredUuid);
      setApiOptions(apiOpts.map(({ label, value }) => ({ label, value })));

      const dsOpts: { label: string; value: string }[] = [];
      let dsPage = 1;
      while (dsPage <= 50) {
        const res = await getDatasetList({ page: dsPage, page_size: 100, is_active: true });
        dsOpts.push(
          ...res.items.map((item) => ({
            label: `${item.name} (${item.code})`,
            value: item.uuid,
          })),
        );
        if (res.items.length < 100 || dsOpts.length >= res.total) break;
        dsPage += 1;
      }
      setDatasetOptions(dsOpts);
    } catch (error: unknown) {
      messageApi.error(
        error instanceof Error ? error.message : t('components.syncFromSource.loadOptionsFailed'),
      );
    } finally {
      setLoadingOptions(false);
    }
  }, [
    config.preferredApiCodeSuffixes,
    config.preferredApiPathTokens,
    config.preferredConnectorTypes,
    messageApi,
    t,
  ]);

  useEffect(() => {
    if (!open) return;
    setSaveBinding(true);
    setSyncProgress([]);
    setSyncMode('manual_full');
    setScheduleIntervalMinutes(15);
    setBindingMeta(null);
    setSettingSourceId(null);
    setPendingNewSourceDraft(null);
    setSourceDrafts([]);
    setDefaultPreferredApiUuid(undefined);
    setLoadedAvailableFields([]);
    void loadOptions();

    let cancelled = false;
    const loadExtraFields = async () => {
      const extras: SyncTargetField[] = [];
      if (config.loadAvailableTargetFields) {
        try {
          extras.push(...(await config.loadAvailableTargetFields()));
        } catch {
          // 自定义字段加载失败不阻断同步；可选字段列表可能不完整
        }
      } else if (config.customFieldTableName) {
        try {
          const customFields = await getCustomFieldsByTable(config.customFieldTableName, true);
          extras.push(
            ...customFields.map((field) => ({
              value: syncCustomFieldTargetKey(field.code),
              label: field.label || field.name,
              kind: 'custom' as const,
              required: field.is_required || undefined,
            })),
          );
        } catch {
          // ignore
        }
      }
      if (!cancelled) setLoadedAvailableFields(extras);
    };
    void loadExtraFields();

    void config
      .getBinding()
      .then((binding) => {
        if (cancelled) return;
        setSourceDrafts(bindingToSourceDrafts(binding, config.sanitizeMapping));
        if (binding.sync_mode) setSyncMode(binding.sync_mode);
        if (binding.schedule_interval_minutes) {
          setScheduleIntervalMinutes(binding.schedule_interval_minutes);
        }
        if (binding.schedule_window_start && binding.schedule_window_end) {
          setScheduleWindow([
            dayjs(binding.schedule_window_start, 'HH:mm'),
            dayjs(binding.schedule_window_end, 'HH:mm'),
          ]);
        } else {
          setScheduleWindow(null);
        }
        setBindingMeta({
          last_success_at: binding.last_success_at,
          last_attempt_at: binding.last_attempt_at,
          last_error: binding.last_error,
        });
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [open, loadOptions, config]);

  const handleSync = async () => {
    let drafts = sourceDrafts;
    if (drafts.every((draft) => Object.keys(draft.targetToSource).length === 0)) {
      const binding = await config.getBinding().catch(() => null);
      if (binding) {
        drafts = bindingToSourceDrafts(binding, config.sanitizeMapping);
        setSourceDrafts(drafts);
      }
    }

    if (drafts.length === 0) {
      messageApi.warning(t('components.syncFromSource.noSources'));
      return;
    }

    for (let index = 0; index < drafts.length; index += 1) {
      const draft = drafts[index];
      const sourceLabel = t('components.syncFromSource.sourceRowLabel', { index: index + 1 });
      if (draft.kind === 'api' && !draft.api_uuid) {
        messageApi.warning(
          t('components.syncFromSource.sourceConfigureFirst', { source: sourceLabel }),
        );
        return;
      }
      if (draft.kind === 'dataset' && !draft.dataset_uuid) {
        messageApi.warning(
          t('components.syncFromSource.sourceConfigureFirst', { source: sourceLabel }),
        );
        return;
      }
      const mappingError = config.validateMapping
        ? config.validateMapping(draft.targetToSource, t)
        : (() => {
            for (const required of config.requiredTargets) {
              if (!draft.targetToSource[required]) {
                const field = config.targetFields.find((item) => item.value === required);
                const fieldLabel = field
                  ? field.label?.trim() ||
                    (field.labelKey ? t(field.labelKey) : field.value)
                  : required;
                return t('components.syncFromSource.mappingRequiredForSource', {
                  source: sourceLabel,
                  field: fieldLabel,
                });
              }
            }
            return null;
          })();
      if (mappingError) {
        messageApi.warning(mappingError);
        return;
      }
    }

    setSyncing(true);
    const prerequisiteSteps = config.prerequisiteSteps ?? [];
    const mainStepId = 'main';
    const progressItems: SyncProgressItem[] = [
      ...prerequisiteSteps.map((step) => ({
        id: step.id,
        titleKey: step.titleKey,
        status: 'wait' as const,
      })),
      {
        id: mainStepId,
        titleKey: config.mainStepTitleKey ?? config.titleKey,
        status: 'wait' as const,
      },
    ];
    setSyncProgress(progressItems);

    let progressState = [...progressItems];
    const patchProgress = (id: string, patch: Partial<SyncProgressItem>) => {
      progressState = progressState.map((item) =>
        item.id === id ? { ...item, ...patch } : item,
      );
      setSyncProgress([...progressState]);
    };

    try {
      for (const step of prerequisiteSteps) {
          patchProgress(step.id, {
            status: 'process',
            description: t('components.syncFromSource.stepWorking'),
          });
          try {
            const binding = await step.getBinding();
            const hasBinding =
              Boolean(binding.source_type) &&
              Boolean(binding.field_mapping) &&
              Object.keys(binding.field_mapping).length > 0;
            if (!hasBinding) {
              patchProgress(step.id, {
                status: 'skip',
                description: t('components.syncFromSource.prerequisiteNotConfigured'),
              });
              continue;
            }
            // 关联同步：有成功水位则只拉增量；流式回报当前处理事务
            patchProgress(step.id, {
              status: 'process',
              description: t('components.syncFromSource.stepConnecting'),
            });
            const stepResult = await step.syncFromSource(
              {
                save_binding: false,
                incremental: true,
                active_only: activeOnly,
                ...(config.inferParentByCodeOption
                  ? { infer_parent_by_code: inferParentByCode }
                  : {}),
              },
              (message) => {
                patchProgress(step.id, {
                  status: 'process',
                  description: message,
                });
              },
            );
            const emptyContinue =
              String(stepResult.empty_reason || '').trim() === 'source_empty' &&
              stepResult.failed === 0;
            patchProgress(step.id, {
              status: stepResult.failed > 0 ? 'error' : 'finish',
              description: emptyContinue
                ? t('components.syncFromSource.stepSourceEmptyContinue')
                : formatStepResult(stepResult),
            });
          } catch (error: unknown) {
          const detail = formatSyncErrorMessage(error, t(config.failedKey));
          if (isInactiveSyncSourceError(error)) {
            patchProgress(step.id, {
              status: 'skip',
              description: detail,
            });
          } else {
            patchProgress(step.id, {
              status: 'error',
              description: detail,
            });
          }
        }
      }

      patchProgress(mainStepId, {
        status: 'process',
        description: t('components.syncFromSource.stepConnecting'),
      });

      const result = await config.syncFromSource(
        {
          sources: draftsToPayloadSources(drafts, config.sanitizeMapping),
          save_binding: saveBinding,
          skip_prerequisite_syncs: config.skipBackendPrerequisites ?? prerequisiteSteps.length > 0,
          sync_mode: syncMode,
          schedule_interval_minutes: scheduleIntervalMinutes,
          ...buildScheduleWindowFields(scheduleWindow),
          // 与「同步方式」一致：定时增量时按 last_success_at 水位拉变更，勿硬编码全量
          incremental: syncMode === 'scheduled_incremental',
          active_only: activeOnly,
          ...(config.inferParentByCodeOption
            ? { infer_parent_by_code: inferParentByCode }
            : {}),
        },
        (message) => {
          patchProgress(mainStepId, {
            status: 'process',
            description: message,
          });
        },
      );

      const wrote = result.created + result.updated;
      const incrementalNoop =
        result.mode === 'incremental' &&
        (result.fetched ?? 0) === 0 &&
        result.failed === 0;
      patchProgress(mainStepId, {
        status: result.failed > 0 || (wrote === 0 && !incrementalNoop) ? 'error' : 'finish',
        description: formatStepResult(result),
      });

      onComplete?.(result);
      setHistoryRefreshNonce((n) => n + 1);
      if (result.failed > 0) {
        messageApi.warning(
          t(config.completePartialKey, {
            created: result.created,
            updated: result.updated,
            skipped: result.skipped,
            failed: result.failed,
          }),
        );
      } else if (wrote === 0 && !incrementalNoop) {
        messageApi.warning(
          t('components.syncFromSource.completeEmpty', {
            created: result.created,
            updated: result.updated,
            skipped: result.skipped,
            fetched: result.fetched ?? 0,
          }),
        );
      } else {
        messageApi.success(
          t(config.completeSuccessKey, {
            created: result.created,
            updated: result.updated,
            skipped: result.skipped,
          }),
        );
      }
      onClose();
    } catch (error: unknown) {
      const detail = formatSyncErrorMessage(error, t(config.failedKey));
      if (isInactiveSyncSourceError(error)) {
        patchProgress(mainStepId, {
          status: 'skip',
          description: detail,
        });
        messageApi.info(t('components.syncFromSource.inactiveSourceHint'));
      } else {
        patchProgress(mainStepId, {
          status: 'error',
          description: detail,
        });
        messageApi.error(detail);
      }
    } finally {
      setSyncing(false);
    }
  };

  const footerButtons = [
    <Button key="cancel" disabled={syncing} onClick={onClose}>
      {t('common.cancel')}
    </Button>,
    <Button key="sync" type="primary" loading={syncing} onClick={() => void handleSync()}>
      {t('components.syncFromSource.confirmSync')}
    </Button>,
  ];

  const body = (
      <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
        {config.hintKey ? <Alert type="info" showIcon title={t(config.hintKey)} /> : null}

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <Space size={8} wrap align="center" style={{ flex: 1, minWidth: 200 }}>
            <Typography.Text strong>{t('components.syncFromSource.sourcesTableTitle')}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12, lineHeight: 1.5 }}>
              {t('components.syncFromSource.sourcesTableHint')}
            </Typography.Text>
          </Space>
          <Space wrap>
            <Button
              icon={<PlusOutlined />}
              onClick={() => {
                const draft = newSyncSourceDraft('api');
                if (defaultPreferredApiUuid) {
                  draft.api_uuid = defaultPreferredApiUuid;
                }
                setPendingNewSourceDraft(draft);
                setSettingSourceId(draft.id);
              }}
            >
              {t('components.syncFromSource.addSource')}
            </Button>
            <Checkbox checked={saveBinding} onChange={(event) => setSaveBinding(event.target.checked)}>
              {t('components.syncFromSource.saveBinding')}
            </Checkbox>
          </Space>
        </div>

        <Table
          size="small"
          pagination={false}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('components.syncFromSource.sourcesEmpty')}
              />
            ),
          }}
          dataSource={sourceDrafts.map((draft, index) => ({ ...draft, key: draft.id, index: index + 1 }))}
          columns={[
            {
              title: t('components.syncFromSource.sourceIndex'),
              dataIndex: 'index',
              width: 56,
            },
            {
              title: t('components.syncFromSource.sourceKind'),
              dataIndex: 'kind',
              width: 100,
              render: (kind: SyncSourceType) =>
                kind === 'api'
                  ? t('components.syncFromSource.sourceApi')
                  : t('components.syncFromSource.sourceDataset'),
            },
            {
              title: t('components.syncFromSource.sourceName'),
              dataIndex: 'id',
              ellipsis: true,
              render: (_id, record) => (
                <span>
                  {resolveDraftDisplayName(record, apiOptions, datasetOptions, t)}
                  {record.kind === 'api' &&
                  (record.request_body || record.request_params || record.batch_fill_values?.length) ? (
                    <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                      {record.persist_request_override
                        ? t('components.syncFromSource.callParamsRemembered')
                        : t('components.syncFromSource.callParamsSessionOnly')}
                    </Typography.Text>
                  ) : null}
                </span>
              ),
            },
            {
              title: (
                <Tooltip title={t('components.syncFromSource.mappingFieldCountHint')}>
                  <span>{t('components.syncFromSource.mappingFieldCount')}</span>
                </Tooltip>
              ),
              width: 120,
              render: (_value, record) => {
                const count = countMappedFields(record);
                const pairs = mappingPairLines(record, fieldByValue, t);
                return (
                  <Tooltip
                    title={
                      pairs.length > 0 ? (
                        <div>
                          {pairs.map((line) => (
                            <div key={line}>{line}</div>
                          ))}
                          <div style={{ marginTop: 6, opacity: 0.85 }}>
                            {t('components.syncFromSource.mappingFieldClickToEdit')}
                          </div>
                        </div>
                      ) : (
                        t('components.syncFromSource.mappingFieldEmpty')
                      )
                    }
                  >
                    <Button
                      type="link"
                      size="small"
                      disabled={syncing}
                      onClick={() => setSettingSourceId(record.id)}
                      style={{ padding: 0 }}
                    >
                      {count > 0
                        ? t('components.syncFromSource.mappingFieldCountValue', { count })
                        : t('components.syncFromSource.mappingFieldEmpty')}
                    </Button>
                  </Tooltip>
                );
              },
            },
            {
              title: t('common.actions'),
              key: 'actions',
              width: 140,
              render: (_value, record) => (
                <Space size="small">
                  <Button type="link" size="small" onClick={() => setSettingSourceId(record.id)}>
                    {t('components.syncFromSource.configureSource')}
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => {
                      setSourceDrafts((prev) => prev.filter((row) => row.id !== record.id));
                      if (settingSourceId === record.id) closeSourceSetting();
                    }}
                  />
                </Space>
              ),
            },
          ]}
        />

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
          }}
        >
          <Space size="medium" align="center">
            <Typography.Text>{t('components.syncFromSource.activeOnly')}</Typography.Text>
            <Switch
              checked={activeOnly}
              onChange={setActiveOnly}
              checkedChildren={t('components.syncFromSource.activeOnlyOn')}
              unCheckedChildren={t('components.syncFromSource.activeOnlyOff')}
            />
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 12, flex: 1, minWidth: 240 }}>
            {t(
              activeOnly
                ? 'components.syncFromSource.activeOnlyHintOn'
                : 'components.syncFromSource.activeOnlyHintOff',
            )}
          </Typography.Text>
        </div>

        {config.inferParentByCodeOption ? (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 12,
            }}
          >
            <Space size="medium" align="center">
              <Typography.Text>{t(config.inferParentByCodeOption.labelKey)}</Typography.Text>
              <Switch
                checked={inferParentByCode}
                onChange={setInferParentByCode}
                checkedChildren={t(config.inferParentByCodeOption.onKey)}
                unCheckedChildren={t(config.inferParentByCodeOption.offKey)}
              />
            </Space>
            <Typography.Text type="secondary" style={{ fontSize: 12, flex: 1, minWidth: 240 }}>
              {t(
                inferParentByCode
                  ? config.inferParentByCodeOption.hintOnKey
                  : config.inferParentByCodeOption.hintOffKey,
              )}
            </Typography.Text>
          </div>
        ) : null}

        <div style={SYNC_FIELD_GRID_STYLE}>
          <Typography.Text type="secondary" style={SYNC_FIELD_LABEL_STYLE}>
            {t('components.syncFromSource.syncMode')}
          </Typography.Text>
          <div style={SYNC_FIELD_CONTROL_STYLE}>
            <Select
              style={{ width: 220 }}
              value={syncMode}
              onChange={setSyncMode}
              options={[
                {
                  value: 'manual_full',
                  label: t('components.syncFromSource.syncMode.manualFull'),
                },
                {
                  value: 'manual_force',
                  label: t('components.syncFromSource.syncMode.manualForce'),
                },
                {
                  value: 'scheduled_incremental',
                  label: t('components.syncFromSource.syncMode.scheduledIncremental'),
                },
                {
                  value: 'scheduled_full',
                  label: t('components.syncFromSource.syncMode.scheduledFull'),
                },
              ]}
            />
            {syncMode === 'scheduled_incremental' || syncMode === 'scheduled_full' ? (
              <>
                <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
                  {t('components.syncFromSource.scheduleInterval')}
                </Typography.Text>
                <Select
                  style={{ width: 140 }}
                  value={scheduleIntervalMinutes}
                  onChange={setScheduleIntervalMinutes}
                  options={[
                    { value: 5, label: t('components.syncFromSource.intervalMinutes', { n: 5 }) },
                    { value: 15, label: t('components.syncFromSource.intervalMinutes', { n: 15 }) },
                    { value: 60, label: t('components.syncFromSource.intervalMinutes', { n: 60 }) },
                    { value: 360, label: t('components.syncFromSource.intervalMinutes', { n: 360 }) },
                  ]}
                />
              </>
            ) : null}
          </div>

          {syncMode === 'scheduled_incremental' || syncMode === 'scheduled_full' ? (
            <>
              <Typography.Text type="secondary" style={SYNC_FIELD_LABEL_STYLE}>
                {t('components.syncFromSource.scheduleWindow')}
              </Typography.Text>
              <div style={SYNC_FIELD_CONTROL_STYLE}>
                <TimePicker.RangePicker
                  format="HH:mm"
                  order={false}
                  allowClear
                  value={scheduleWindow}
                  onChange={(values) => {
                    if (!values || !values[0] || !values[1]) {
                      setScheduleWindow(null);
                      return;
                    }
                    setScheduleWindow([values[0], values[1]]);
                  }}
                />
              </div>
            </>
          ) : null}

          <span />
          <Typography.Text type="secondary" style={{ fontSize: 12, lineHeight: 1.5 }}>
            {t(
              syncMode === 'scheduled_incremental'
                ? 'components.syncFromSource.syncMode.incrementalHint'
                : syncMode === 'manual_force'
                  ? 'components.syncFromSource.syncMode.manualForceHint'
                  : 'components.syncFromSource.syncMode.fullHint',
            )}
            {syncMode === 'scheduled_incremental' || syncMode === 'scheduled_full'
              ? ` ${t('components.syncFromSource.scheduleWindowHint')}`
              : ''}
          </Typography.Text>
        </div>

        {!syncing && (bindingMeta?.last_success_at || bindingMeta?.last_error) ? (
          <Alert
            type={bindingMeta.last_error ? 'warning' : 'success'}
            showIcon
            title={
              bindingMeta.last_error
                ? t('components.syncFromSource.lastError', { error: bindingMeta.last_error })
                : t('components.syncFromSource.lastSuccess', {
                    time: formatDateTimeBySiteSetting(bindingMeta.last_success_at),
                  })
            }
          />
        ) : null}

        {hasAnySavedMapping && !syncing ? (
          <Alert
            type="info"
            showIcon
            title={t('components.syncFromSource.savedMappingReady')}
          />
        ) : null}

        {syncing || syncProgress.length > 0 ? (
          <div
            style={{
              padding: 12,
              borderRadius: 8,
              background: 'var(--ant-color-fill-quaternary, rgba(0,0,0,0.02))',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 12,
                marginBottom: 8,
                flexWrap: 'wrap',
              }}
            >
              <Typography.Text strong>
                {t('components.syncFromSource.syncProgressTitle')}
              </Typography.Text>
              <Typography.Text type="secondary">
                {syncProgressHeaderHint}
              </Typography.Text>
            </div>
            <Progress
              percent={syncProgressPercent}
              status={syncProgressStatus}
              showInfo
            />
            {syncProgress.length > 0 ? (
              <Steps
                orientation="vertical"
                size="small"
                style={{ marginTop: 12 }}
                items={syncProgress.map((step) => ({
                  title: t(step.titleKey),
                  status:
                    step.status === 'skip'
                      ? 'wait'
                      : step.status === 'process'
                        ? 'process'
                        : step.status,
                  description:
                    step.status === 'skip' ? (
                      <Typography.Text type="secondary">{step.description}</Typography.Text>
                    ) : (
                      step.description
                    ),
                }))}
              />
            ) : null}
          </div>
        ) : null}

      </Space>
  );

  const settingModal =
    editingDraft && settingSourceId ? (
      <SyncSourceSettingModal
        open
        onClose={closeSourceSetting}
        onSave={(updated) => {
          const isNewPending = pendingNewSourceDraft?.id === updated.id;
          if (isNewPending) {
            setSourceDrafts((prev) => [...prev, updated]);
            setPendingNewSourceDraft(null);
            setSettingSourceId(null);
            return;
          }
          setSourceDrafts((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
          setSettingSourceId(null);
        }}
        draft={editingDraft}
        config={config}
        apiOptions={apiOptions}
        datasetOptions={datasetOptions}
        loadingOptions={loadingOptions}
        loadedAvailableFields={loadedAvailableFields}
        zIndex={(zIndex ?? 1000) + 10}
      />
    ) : null;

  const modalBody = showHistoryTab ? (
    <>
      <Tabs
        activeKey={panelTab}
        onChange={(key) => setActiveTab(key as SyncFromSourceTabKey)}
        items={[
          { key: 'sync', label: t('components.syncFromSource.tabSync') },
          { key: 'history', label: t('components.syncPushHub.tabHistory') },
        ]}
      />
      <div style={{ marginTop: 4 }}>
        {syncTabActive ? body : null}
        {historyTabActive ? (
          <SyncRunHistoryPanel
            active={historyTabActive}
            sourceType={historySource}
            listHistory={resolvedListSyncRunHistory}
            refreshNonce={historyRefreshNonce}
          />
        ) : null}
      </div>
    </>
  ) : (
    body
  );

  if (contentOnly) {
    if (!open) return null;
    return (
      <div>
        {modalBody}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
            marginTop: 16,
            flexWrap: 'wrap',
          }}
        >
          {footerButtons}
        </div>
        {settingModal}
      </div>
    );
  }

  return (
    <>
      <Modal
        title={t(config.titleKey)}
        open={open}
        onCancel={() => {
          if (syncing) return;
          onClose();
        }}
        zIndex={zIndex}
        width={showHistoryTab ? 1100 : 960}
        destroyOnHidden
        footer={syncTabActive || !showHistoryTab ? footerButtons : null}
      >
        {modalBody}
      </Modal>
      {settingModal}
    </>
  );
};

export default SyncFromSourceModal;
