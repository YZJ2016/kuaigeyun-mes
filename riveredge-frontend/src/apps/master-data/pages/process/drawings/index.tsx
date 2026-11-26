/**
 * 工程图纸管理页面（两栏：左导航树 + 右表/预览）
 */

import React, { lazy, startTransition, Suspense, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ActionType, ProColumns, ProDescriptionsItemProps } from '@ant-design/pro-components';
import { App, Button, Dropdown, Grid, Input, Modal, Popconfirm, Segmented, Space, Spin, Switch, Tooltip, theme } from 'antd';
import type { MenuProps } from 'antd';
import type { DataNode } from 'antd/es/tree';
import {
  AuditOutlined,
  BookOutlined,
  CheckOutlined,
  CloseCircleOutlined,
  CloudUploadOutlined,
  CompressOutlined,
  DeleteOutlined,
  DiffOutlined,
  DownloadOutlined,
  EditOutlined,
  ExpandOutlined,
  ExportOutlined,
  EyeOutlined,
  FilterOutlined,
  FolderOutlined,
  ImportOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoreOutlined,
  NodeIndexOutlined,
  PartitionOutlined,
  PlusOutlined,
  PrinterOutlined,
  RollbackOutlined,
  SendOutlined,
  SettingOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { UniTable, type UniTableRequestMeta} from '../../../../../components/uni-table';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import {
  normalizeActionTree,
  renderRowActionsOverflow,
  rowActionDownloadFirmware,
  rowActionDrawingCheckin,
  rowActionDrawingCheckout,
  rowActionDrawingDistribute,
  rowActionDrawingEngineeringChange,
  rowActionDrawingImportStepBom,
  rowActionDrawingLoan,
  rowActionDrawingNewRevision,
  rowActionDrawingUndoCheckout,
  rowActionDrawingWhereUsed,
  rowActionKind,
  rowActionLabelKeep,
} from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { fetchCoreFileBytesByUuid } from '../../../../../utils/fetchCoreFileBytes';
import { downloadFile } from '../../../../../utils/fileDownload';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import {
  TwoColumnLayout,
  LIST_PAGE_TABLE_SCROLL,
  TWO_COLUMN_LAYOUT,
} from '../../../../../components/layout-templates';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import {
  pickListSearchKeywordOrFields,
  pickSearchString,
} from '../../../../../utils/tableQueryKey';
import { ProcessMasterDetailDrawer } from '../shared/processMasterDetailDrawer';
import { DetailDrawerActions } from '../../../../../components/layout-templates/DetailDrawerActions';
import { MarkerTag, StatusTag } from '../../../../../constants/statusBadges';
import { DictionaryLabel } from '../../../../../components/dictionary-label';
import { formatProjectRefLabel } from '../../../utils/projectRefLabel';
import { getDictionaryOptions } from '../../../services/supply-chain';
import { DrawingFormModal } from '../../../components/DrawingFormModal';
import { DrawingBatchUploadModal } from '../../../components/DrawingBatchUploadModal';
import { UniBatchMenuButton } from '../../../../../components/uni-batch';
import { StepBomImportWizard } from '../../../components/StepBomImportWizard';
import FilePreviewModal from '../../../../../components/file-preview';
import { CadPreviewLoading } from '../../../../../components/cad-preview/CadPreviewLoading';
import { materialApi } from '../../../services/material';
import { processRouteApi, unwrapProcessPagedList } from '../../../services/process';
import {
  drawingApi,
  normalizeFileBrief,
  type DrawingListView,
  type DrawingSecurityLevel,
  type DrawingStatus,
  DRAWING_TYPE_DICTIONARY_CODE,
  type DrawingType,
  type EngineeringDrawing,
  type EngineeringDrawingRevisionBrief,
  type FileBrief,
} from '../../../services/drawing';
import {
  DRAWING_TREE_ALL_KEY,
  parseDrawingTreeKey,
  type DrawingPaneMode,
  type DrawingTreeFilter,
  type DrawingTreeNavItem,
} from './drawingTreeData';
import {
  DRAWING_NAV_MODES,
  buildDrawingNavTree,
  buildDrawingVaultTree,
  findDrawingFolderByUuid,
  folderUuidFromTreeKey,
  inferNavModeFromTreeKey,
  isVaultTreeKey,
  treeKeyBelongsToMode,
  withDrawingTreeCount,
  type DrawingNavMode,
  type DrawingTypeNavItem,
} from './drawingTreeNav';
import { drawingFolderApi, type DrawingFolder } from '../../../services/drawingFolder';
import {
  DrawingFolderFormModal,
  DrawingMoveFolderModal,
} from './drawingFolderModals';
import { DrawingWatermarkSettingsModal } from './DrawingWatermarkSettingsModal';
import { buildWatermarkInlineStyle } from './drawingWatermarkUtils';
import {
  DrawingDetailRecordTabs,
  DrawingDistributeFromDrawingModal,
  DrawingLoanFromDrawingModal,
  DrawingWhereUsedModal,
} from './DrawingIntegratedPanels';
import { drawingDistributionApi } from '../../../services/drawingDistribution';
import { isStepFile } from '../../../../../utils/filePreviewKind';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import { alignProColumns } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import {
  UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
  UNI_TABLE_SITE_DATETIME_COLUMN_DEFAULTS,
} from '../../../../../utils/uniTableLayoutColumns';
import { MASTER_DATA_LIST_FIELD_RANK } from '../../../utils/masterListCore';
import { masterCrudCreatedUpdatedColumns } from '../../../utils/masterListCore';
import { getAntdModal } from '../../../../../utils/antdAppApis';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import { buildDrawingChangeCreateUrl } from '../../../utils/plmDeepLinks';
import { buildListPageHelpViewConfig } from '../../../../../components/page-help-wiki';
const DRAWING_PERMISSION = 'master-data:process:drawing';

const STATUS_COLOR: Record<DrawingStatus, string> = {
  Draft: 'default',
  Editing: 'processing',
  Pending: 'warning',
  Released: 'success',
  Obsolete: 'error',
};

function canImportStepBom(record: EngineeringDrawing): boolean {
  // 导入只回写关联 BOM，不改 CAD 主文件；已发布装配体也应可用（仅作废不可）
  if (record.status === 'Obsolete') return false;
  if (record.drawingType !== 'assembly') return false;
  if (!record.file) return false;
  return isStepFile({
    fileName: record.file.originalName,
    fileExtension: record.file.fileExtension,
  });
}

function bomDesignerPath(materialId: number, version: string): string {
  return `/apps/master-data/process/engineering-bom/designer?materialId=${materialId}&version=${encodeURIComponent(version)}`;
}

const LazyDrawingInlinePreview = lazy(() =>
  import('../../../components/DrawingInlinePreview').then((m) => ({ default: m.DrawingInlinePreview })),
);

type InlinePreviewPaneProps = {
  file: FileBrief | null;
  activeDrawing: EngineeringDrawing | null;
  previewPending: boolean;
  canImportStepBomAction: boolean;
  onOpenLargePreview: () => void;
  onOpenStepBom: (drawing: EngineeringDrawing) => void;
};

const InlinePreviewPane = React.memo(function InlinePreviewPane({
  file,
  activeDrawing,
  previewPending,
  canImportStepBomAction,
  onOpenLargePreview,
  onOpenStepBom,
}: InlinePreviewPaneProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const showStepBom = canImportStepBomAction && activeDrawing && canImportStepBom(activeDrawing);
  const showLarge = !!activeDrawing?.file?.uuid;

  return (
    <div
      className="drawings-inline-preview-pane"
      style={{
        flex: '1 1 0',
        minWidth: 280,
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        borderLeft: `1px solid ${token.colorBorder}`,
        background: token.colorFillAlter,
        overflow: 'hidden',
      }}
    >
      <div
        className="drawings-inline-preview-header"
        style={{
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          height: TWO_COLUMN_LAYOUT.PANEL_HEADER_HEIGHT,
          padding: '8px 12px',
          boxSizing: 'border-box',
          borderBottom: `1px solid ${token.colorBorder}`,
          background: token.colorFillAlter,
        }}
      >
        {(showStepBom || showLarge) && (
          <Space.Compact style={{ flexShrink: 0 }}>
            {showStepBom && (
              <Button icon={<PartitionOutlined />} onClick={() => onOpenStepBom(activeDrawing!)}>
                {t('app.master-data.drawings.importStepBom')}
              </Button>
            )}
            {showLarge && (
              <Button icon={<ExpandOutlined />} onClick={onOpenLargePreview}>
                {t('app.master-data.drawings.openLargePreview')}
              </Button>
            )}
          </Space.Compact>
        )}
      </div>
      <div
        className="drawings-inline-preview-body"
        style={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
          contain: 'layout paint style',
          background: token.colorBgContainer,
        }}
      >
        {previewPending && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              zIndex: 2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'color-mix(in srgb, var(--ant-color-bg-container) 72%, transparent)',
              pointerEvents: 'none',
            }}
          >
            <CadPreviewLoading text={t('app.master-data.drawings.stepPreviewLoading')} />
          </div>
        )}
        <Suspense
          fallback={
            <CadPreviewLoading text={t('app.master-data.drawings.stepPreviewLoading')} minHeight="100%" />
          }
        >
          <LazyDrawingInlinePreview
            fileUuid={file?.uuid}
            fileName={file?.originalName}
            fileExtension={file?.fileExtension}
            height="100%"
            chromeless
          />
        </Suspense>
      </div>
    </div>
  );
});

function formatAssociationLabels(
  items: Array<{ code?: string; mainCode?: string; name: string }> | undefined,
): string {
  if (!items?.length) return '-';
  return items.map((item) => `${item.mainCode ?? item.code ?? ''} - ${item.name}`).join('; ');
}

const DrawingsPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { message: messageApi } = App.useApp();
  const currentUser = useCurrentUser();
  const { canCreate, canUpdate, canDelete, canPrint, canImport, canExport, canAction } =
    useResourcePermissions(DRAWING_PERMISSION);
  const changePerms = useResourcePermissions('kuaiplm:change');
  const whereUsedPerms = useResourcePermissions('master-data:process:drawing-where-used');
  const distPerms = useResourcePermissions('master-data:process:drawing-distribution');
  const loanPerms = useResourcePermissions('master-data:process:drawing-loan');
  const canSubmit = !!canAction?.('submit');
  const canApprove = !!canAction?.('approve');
  const canReject = !!canAction?.('reject');
  const canRevoke = !!canAction?.('revoke');
  const canObsolete = !!canAction?.('obsolete');
  const canDownload = canExport || canPrint || canUpdate || canCreate;

  const openDrawingPrint = useCallback(async (record: EngineeringDrawing) => {
    try {
      const data = await drawingApi.getPrintData(record.uuid);
      const escapeHtml = (value: string) =>
        value
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      const watermarkNode =
        data.watermark && data.watermarkStyle
          ? `<div class="watermark" style="${buildWatermarkInlineStyle(data.watermarkStyle)}">${escapeHtml(data.watermark)}</div>`
          : data.watermark
            ? `<div class="watermark">${escapeHtml(data.watermark)}</div>`
            : '';
      const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/><title>${escapeHtml(data.code)}</title>
<style>
body{font-family:sans-serif;padding:24px;}
.watermark{pointer-events:none;z-index:0;white-space:pre-wrap;max-width:80%;}
.content{position:relative;z-index:1;}
h1{font-size:20px;margin:0 0 8px;}
.meta{color:#666;font-size:13px;margin-bottom:16px;}
img{max-width:100%;}
</style></head><body>
${watermarkNode}
<div class="content">
<h1>${escapeHtml(data.name)}</h1>
<div class="meta">${escapeHtml(`${data.code}-${data.revision}`)} ${escapeHtml(t(`app.master-data.drawings.securityLevel.${data.securityLevel}`))}</div>
${data.previewUrl ? `<img src="${escapeHtml(data.previewUrl)}" alt="${escapeHtml(data.fileName || data.code)}"/>` : ''}
</div>
<script>window.onload=function(){window.print();}</script>
</body></html>`;
      const w = window.open('', '_blank');
      if (!w) return;
      w.document.write(html);
      w.document.close();
    } catch (e) {
      messageApi.error(getApiErrorMessage(e) || t('common.operationFailed'));
    }
  }, [messageApi, t]);
  const isCheckoutOwner = useCallback(
    (record: EngineeringDrawing) =>
      record.status === 'Editing' && record.checkedOutBy != null && record.checkedOutBy === currentUser?.id,
    [currentUser?.id],
  );
  const screens = Grid.useBreakpoint();
  const showInlinePreview = !!screens.lg;

  const actionRef = useRef<ActionType>(null);

  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [paneMode, setPaneMode] = useState<DrawingPaneMode>('vault');
  const [navMode, setNavMode] = useState<DrawingNavMode>('type');
  const [treeSearch, setTreeSearch] = useState('');
  const [selectedTreeKeys, setSelectedTreeKeys] = useState<React.Key[]>([DRAWING_TREE_ALL_KEY]);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [materialsNav, setMaterialsNav] = useState<DrawingTreeNavItem[]>([]);
  const [routesNav, setRoutesNav] = useState<DrawingTreeNavItem[]>([]);
  const [drawingTypeNav, setDrawingTypeNav] = useState<DrawingTypeNavItem[]>([]);
  const [materialsLoaded, setMaterialsLoaded] = useState(false);
  const [routesLoaded, setRoutesLoaded] = useState(false);
  const [folders, setFolders] = useState<DrawingFolder[]>([]);
  const [folderTreeSummary, setFolderTreeSummary] = useState({
    totalDrawingCount: 0,
    unclassifiedDrawingCount: 0,
  });
  const [treeFilter, setTreeFilter] = useState<DrawingTreeFilter>({});
  const [folderForm, setFolderForm] = useState<{
    open: boolean;
    mode: 'create' | 'rename';
    parentUuid?: string | null;
    folderUuid?: string | null;
    initialName?: string;
  }>({ open: false, mode: 'create' });
  const [moveFolder, setMoveFolder] = useState<{
    open: boolean;
    drawingUuids: string[];
    currentFolderUuid?: string | null;
  }>({ open: false, drawingUuids: [] });
  const [folderCtx, setFolderCtx] = useState<{
    x: number;
    y: number;
    uuid: string;
    name: string;
  } | null>(null);

  const [drawerVisible, setDrawerVisible] = useState(false);
  const [detail, setDetail] = useState<EngineeringDrawing | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRetryUuidRef = useRef<string | null>(null);

  const [modalVisible, setModalVisible] = useState(false);
  const [batchUploadOpen, setBatchUploadOpen] = useState(false);
  const [watermarkSettingsOpen, setWatermarkSettingsOpen] = useState(false);
  const [editUuid, setEditUuid] = useState<string | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const {
    customFields,
    generateCustomFieldColumns,
    enrichRecordsWithCustomFields,
    customFieldValues,
    loadFieldValuesForDetail,
    resetDetailFieldValues,
  } = useCustomFieldsForList<EngineeringDrawing>({ tableName: 'apps_master_data_engineering_drawings' });
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewFile, setPreviewFile] = useState<FileBrief | null>(null);
  const [largePreviewOpen, setLargePreviewOpen] = useState(false);

  const [selectedRowUuid, setSelectedRowUuid] = useState<string | null>(null);
  const [inlinePreviewFile, setInlinePreviewFile] = useState<FileBrief | null>(null);
  const [selectedDrawing, setSelectedDrawing] = useState<EngineeringDrawing | null>(null);
  const [stepBomOpen, setStepBomOpen] = useState(false);
  const [stepBomDrawing, setStepBomDrawing] = useState<EngineeringDrawing | null>(null);
  const [listView, setListView] = useState<DrawingListView>('current');
  /** 与 params.listView 双写：request 读 ref，避免 ProTable 入参尚未提交时闭包仍用旧 view */
  const listViewRef = useRef<DrawingListView>(listView);
  listViewRef.current = listView;
  const [requireChangeSummaryOnEdit, setRequireChangeSummaryOnEdit] = useState(false);
  const [revisions, setRevisions] = useState<EngineeringDrawingRevisionBrief[]>([]);
  const [revisionsLoading, setRevisionsLoading] = useState(false);
  const [whereUsedDrawing, setWhereUsedDrawing] = useState<EngineeringDrawing | null>(null);
  const [distributeDrawing, setDistributeDrawing] = useState<EngineeringDrawing | null>(null);
  const [loanDrawing, setLoanDrawing] = useState<EngineeringDrawing | null>(null);
  const [detailRecordsReloadToken, setDetailRecordsReloadToken] = useState(0);
  const [distPolicyEnabled, setDistPolicyEnabled] = useState(false);
  const [distPolicyLoading, setDistPolicyLoading] = useState(false);
  const showPreviewPane = showInlinePreview && !!inlinePreviewFile?.uuid;

  const typeLabel = (type: DrawingType) =>
    t(`app.master-data.drawings.type.${type}`, { defaultValue: type });
  const statusLabel = (status: DrawingStatus) => t(`app.master-data.drawings.status.${status}`);

  const loadMaterialsNav = useCallback(async () => {
    if (materialsLoaded) return;
    setTreeLoading(true);
    try {
      const materialsRes = await materialApi.list({ limit: 500 });
      setMaterialsNav(
        (materialsRes?.items ?? []).map((m) => ({
          uuid: m.uuid,
          code: m.mainCode || m.code || '',
          name: m.name,
        })),
      );
      setMaterialsLoaded(true);
    } catch {
      /* non-blocking */
    } finally {
      setTreeLoading(false);
    }
  }, [materialsLoaded]);

  const loadRoutesNav = useCallback(async () => {
    if (routesLoaded) return;
    setTreeLoading(true);
    try {
      const routesRes = await processRouteApi.list({ limit: 500 });
      setRoutesNav(
        unwrapProcessPagedList(routesRes).map((r) => ({
          uuid: r.uuid,
          code: r.code,
          name: r.name,
        })),
      );
      setRoutesLoaded(true);
    } catch {
      /* non-blocking */
    } finally {
      setTreeLoading(false);
    }
  }, [routesLoaded]);

  const loadFolders = useCallback(async () => {
    setTreeLoading(true);
    try {
      const result = await drawingFolderApi.tree({});
      setFolders(result.data);
      setFolderTreeSummary({
        totalDrawingCount: result.totalDrawingCount,
        unclassifiedDrawingCount: result.unclassifiedDrawingCount,
      });
    } catch {
      setFolders([]);
      setFolderTreeSummary({ totalDrawingCount: 0, unclassifiedDrawingCount: 0 });
    } finally {
      setTreeLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    if (paneMode === 'filter' && navMode === 'material') void loadMaterialsNav();
    if (paneMode === 'filter' && navMode === 'route') void loadRoutesNav();
  }, [paneMode, navMode, loadMaterialsNav, loadRoutesNav]);

  useEffect(() => {
    if (paneMode !== 'filter' || navMode !== 'type') return;
    let cancelled = false;
    void getDictionaryOptions(DRAWING_TYPE_DICTIONARY_CODE)
      .then((options) => {
        if (cancelled) return;
        setDrawingTypeNav(
          options.map((item) => ({ value: String(item.value), label: String(item.label) })),
        );
      })
      .catch(() => {
        if (!cancelled) setDrawingTypeNav([]);
      });
    return () => {
      cancelled = true;
    };
  }, [navMode, paneMode]);

  const treeData: DataNode[] = useMemo(
    () =>
      paneMode === 'vault'
        ? buildDrawingVaultTree(t, folders, treeSearch, folderTreeSummary)
        : buildDrawingNavTree(navMode, t, materialsNav, routesNav, treeSearch, drawingTypeNav),
    [paneMode, t, folders, treeSearch, navMode, materialsNav, routesNav, folderTreeSummary, drawingTypeNav],
  );

  const collectTreeExpandableKeys = useCallback((nodes: DataNode[]): React.Key[] => {
    const keys: React.Key[] = [];
    const walk = (data: DataNode[]) => {
      data.forEach((node) => {
        if (node.children?.length) {
          keys.push(node.key);
          walk(node.children);
        }
      });
    };
    walk(nodes);
    return keys;
  }, []);

  const vaultExpandableKeys = useMemo(
    () => (paneMode === 'vault' ? collectTreeExpandableKeys(treeData) : []),
    [collectTreeExpandableKeys, paneMode, treeData],
  );

  const handleToggleFolderExpand = useCallback(() => {
    setExpandedKeys((prev) => (prev.length > 0 ? [] : vaultExpandableKeys));
  }, [vaultExpandableKeys]);

  const handleTreeExpand = useCallback((keys: React.Key[]) => {
    setExpandedKeys(keys);
  }, []);

  const handlePaneModeChange = useCallback((mode: DrawingPaneMode) => {
    setPaneMode(mode);
    setTreeSearch('');
    const currentKey = String(selectedTreeKeys[0] ?? DRAWING_TREE_ALL_KEY);
    const keep = mode === 'vault' ? isVaultTreeKey(currentKey) : !isVaultTreeKey(currentKey) || currentKey === DRAWING_TREE_ALL_KEY;
    if (!keep) {
      setSelectedTreeKeys([DRAWING_TREE_ALL_KEY]);
      startTransition(() => {
        setTreeFilter({});
    actionRef.current?.reload();
      });
    }
  }, [selectedTreeKeys]);

  const handleNavModeChange = useCallback((mode: DrawingNavMode) => {
    setNavMode(mode);
    setTreeSearch('');
    const currentKey = String(selectedTreeKeys[0] ?? DRAWING_TREE_ALL_KEY);
    if (!treeKeyBelongsToMode(currentKey, mode)) {
      setSelectedTreeKeys([DRAWING_TREE_ALL_KEY]);
      startTransition(() => {
        setTreeFilter({});
    actionRef.current?.reload();
      });
    }
  }, [selectedTreeKeys]);

  const paneModeBar = useMemo(
    () => (
      <Segmented
        block
        value={paneMode}
        onChange={(value) => handlePaneModeChange(value as DrawingPaneMode)}
        options={[
          { label: t('app.master-data.drawings.tree.vault'), value: 'vault', icon: <FolderOutlined /> },
          { label: t('app.master-data.drawings.tree.filter'), value: 'filter', icon: <FilterOutlined /> },
        ]}
      />
    ),
    [paneMode, t, handlePaneModeChange],
  );

  const navModeBar = useMemo(
    () => (
      <div className="drawing-nav-mode-bar" role="tablist" aria-label={t('app.master-data.drawings.tree.navModes')}>
        {DRAWING_NAV_MODES.map(({ mode, icon: Icon, labelKey }) => {
          const active = navMode === mode;
          return (
            <Tooltip key={mode} title={t(labelKey)}>
              <button
                type="button"
                role="tab"
                aria-selected={active}
                className={`drawing-nav-mode-btn${active ? ' drawing-nav-mode-btn-active' : ''}`}
                onClick={() => handleNavModeChange(mode)}
              >
                <Icon />
              </button>
            </Tooltip>
          );
        })}
      </div>
    ),
    [navMode, t, handleNavModeChange],
  );

  const openCreateFolder = useCallback((parentUuid?: string | null) => {
    setFolderForm({ open: true, mode: 'create', parentUuid: parentUuid ?? null });
  }, []);

  const selectedVaultFolderUuid = useMemo(() => {
    if (paneMode !== 'vault') return null;
    return folderUuidFromTreeKey(String(selectedTreeKeys[0] ?? ''));
  }, [paneMode, selectedTreeKeys]);

  const openEditFolder = useCallback((folder: Pick<DrawingFolder, 'uuid' | 'name'>) => {
    setFolderForm({
      open: true,
      mode: 'rename',
      folderUuid: folder.uuid,
      initialName: folder.name,
    });
  }, []);

  const confirmDeleteFolder = useCallback(
    (folder: Pick<DrawingFolder, 'uuid' | 'name'>) => {
      getAntdModal().confirm({
        title: t('common.delete'),
        content: t('app.master-data.drawings.folder.deleteConfirm'),
        okButtonProps: { danger: true },
        onOk: async () => {
          await drawingFolderApi.delete(folder.uuid);
          messageApi.success(t('common.deleteSuccess'));
          if (treeFilter.folderUuid === folder.uuid) {
            setSelectedTreeKeys([DRAWING_TREE_ALL_KEY]);
            setTreeFilter({});
            actionRef.current?.reload();
          }
          await loadFolders();
        },
      });
    },
    [loadFolders, messageApi, t, treeFilter.folderUuid],
  );

  const stopVaultFolderTreeActionEvent = useCallback((event: React.MouseEvent | React.KeyboardEvent) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const renderVaultFolderTitle = useCallback(
    (node: DataNode) => {
      const folderUuid = folderUuidFromTreeKey(String(node.key));
      if (!folderUuid) {
        return node.title as React.ReactNode;
      }
      const folder = findDrawingFolderByUuid(folders, folderUuid);
      if (!folder) {
        return node.title as React.ReactNode;
      }
      const folderLabel = withDrawingTreeCount(folder.name, folder.drawingCount);
      if (!canUpdate && !canDelete) {
        return folderLabel;
      }
      return (
        <span className="drawing-vault-folder-tree-title">
          <span className="drawing-vault-folder-tree-title-text">{folderLabel}</span>
          <span
            className="drawing-vault-folder-tree-title-actions"
            onClick={stopVaultFolderTreeActionEvent}
            onMouseDown={stopVaultFolderTreeActionEvent}
          >
            <Space size={0} align="center">
              {canUpdate ? (
                <Tooltip title={t('common.edit')}>
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    aria-label={t('common.edit')}
                    onClick={(event) => {
                      stopVaultFolderTreeActionEvent(event);
                      openEditFolder(folder);
                    }}
                  />
                </Tooltip>
              ) : null}
              {canDelete ? (
                <Tooltip title={t('common.delete')}>
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    aria-label={t('common.delete')}
                    onClick={(event) => {
                      stopVaultFolderTreeActionEvent(event);
                      confirmDeleteFolder(folder);
                    }}
                  />
                </Tooltip>
              ) : null}
            </Space>
          </span>
        </span>
      );
    },
    [
      canDelete,
      canUpdate,
      confirmDeleteFolder,
      folders,
      openEditFolder,
      stopVaultFolderTreeActionEvent,
      t,
    ],
  );

  const folderTreeActions = useMemo(() => {
    if (paneMode !== 'vault') return null;
    if (!canCreate && vaultExpandableKeys.length === 0) return null;
    return (
      <div style={{ display: 'flex', gap: 8, width: '100%' }}>
        {canCreate ? (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            style={{ flex: 1 }}
            onClick={() => openCreateFolder(selectedVaultFolderUuid)}
          >
            {t('app.master-data.drawings.folder.create')}
          </Button>
        ) : null}
        {vaultExpandableKeys.length > 0 ? (
          <Button
            icon={expandedKeys.length > 0 ? <CompressOutlined /> : <ExpandOutlined />}
            onClick={handleToggleFolderExpand}
            title={
              expandedKeys.length > 0
                ? t('app.master-data.materials.collapseAll')
                : t('app.master-data.materials.expandAll')
            }
          />
        ) : null}
      </div>
    );
  }, [
    canCreate,
    expandedKeys.length,
    handleToggleFolderExpand,
    openCreateFolder,
    paneMode,
    selectedVaultFolderUuid,
    t,
    vaultExpandableKeys.length,
  ]);

  const handleTreeSelect = useCallback(
    (keys: React.Key[]) => {
      if (!keys.length) return;
      const key = String(keys[0]);
      if (key.endsWith(':empty')) return;

      setSelectedRowUuid(null);
      setInlinePreviewFile(null);
      setSelectedDrawing(null);

      const nextFilter = parseDrawingTreeKey(key);
      const inferredMode = inferNavModeFromTreeKey(key);

      // 优先更新树选中态，避免被右侧表格/预览重渲染阻塞
      setSelectedTreeKeys(keys);

      startTransition(() => {
        setTreeFilter(nextFilter);
        if (inferredMode && inferredMode !== navMode) {
          setNavMode(inferredMode);
        }
    actionRef.current?.reload();
      });
    },
    [navMode],
  );

  const openPreview = (file?: FileBrief | null) => {
    if (!file?.uuid) return;
    if (showInlinePreview) {
      setInlinePreviewFile(file);
      return;
    }
    setPreviewFile(file);
    setPreviewOpen(true);
  };

  const selectRowForPreview = useCallback((record: EngineeringDrawing) => {
    setSelectedRowUuid(record.uuid);
    startTransition(() => {
      setSelectedDrawing(record);
      if (showInlinePreview) {
        if (record.file?.uuid) {
          setInlinePreviewFile(normalizeFileBrief(record.file) ?? record.file);
        } else {
          setInlinePreviewFile(null);
        }
      }
    });
  }, [showInlinePreview]);

  const deferredPreviewFile = useDeferredValue(inlinePreviewFile);
  const previewPending = inlinePreviewFile?.uuid !== deferredPreviewFile?.uuid;

  const openStepBomWizard = useCallback((record: EngineeringDrawing) => {
    setStepBomDrawing(record);
    setStepBomOpen(true);
  }, []);

  const loadDetail = async (uuid: string) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      const data = await drawingApi.get(uuid);
      setDetail(data);
      if (data.id != null) {
        await loadFieldValuesForDetail(data.id);
      }
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('app.master-data.drawings.getDetailFailed')));
    } finally {
      setDetailLoading(false);
    }
  };

  const handleOpenDetail = (uuid: string) => {
    detailRetryUuidRef.current = uuid;
    setDrawerVisible(true);
    setDetail(null);
    setDetailError(null);
    void loadDetail(uuid);
  };

  useEffect(() => {
    if (!distPerms.canRead) return;
    void drawingDistributionApi
      .getPolicy()
      .then((p) => setDistPolicyEnabled(!!p.isEnabled))
      .catch(() => undefined);
  }, [distPerms.canRead]);

  const handleDownloadDrawing = useCallback(
    async (record: EngineeringDrawing) => {
      const file = record.file;
      if (!file?.uuid) {
        messageApi.warning(t('app.master-data.drawings.downloadNoFile'));
        return;
      }
      try {
        const bytes = await fetchCoreFileBytesByUuid(
          file.uuid,
          t('app.master-data.drawings.downloadFailed'),
        );
        downloadFile(new Blob([bytes]), file.originalName || `${record.code}.bin`);
        messageApi.success(t('app.master-data.drawings.downloadSuccess'));
      } catch (err: unknown) {
        messageApi.error(getApiErrorMessage(err) || t('app.master-data.drawings.downloadFailed'));
      }
    },
    [messageApi, t],
  );

  const handleCreate = useCallback(() => {
    setEditUuid(null);
    setRequireChangeSummaryOnEdit(false);
    setModalVisible(true);
  }, []);

  const defaultCreateFolderUuid = treeFilter.folderUuid ?? null;

  useNewShortcut(() => {
    if (canCreate) handleCreate();
  });

  const reloadAfterAction = (record: EngineeringDrawing) => {
    actionRef.current?.reload();
    if (detail?.uuid === record.uuid) void loadDetail(record.uuid);
  };

  const handleCheckout = async (record: EngineeringDrawing) => {
    try {
      await drawingApi.checkout(record.uuid);
      messageApi.success(t('app.master-data.drawings.checkoutSuccess'));
      reloadAfterAction(record);
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
    }
  };

  const handleCheckin = async (record: EngineeringDrawing) => {
    try {
      await drawingApi.checkin(record.uuid);
      messageApi.success(t('app.master-data.drawings.checkinSuccess'));
      reloadAfterAction(record);
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
    }
  };

  const executeUndoCheckout = async (record: EngineeringDrawing) => {
    await drawingApi.undoCheckout(record.uuid);
        messageApi.success(t('app.master-data.drawings.undoCheckoutSuccess'));
        reloadAfterAction(record);
  };

  const executeSubmit = async (record: EngineeringDrawing) => {
    await drawingApi.submit(record.uuid);
        messageApi.success(t('app.master-data.drawings.submitSuccess'));
        reloadAfterAction(record);
  };

  const executeApprove = async (record: EngineeringDrawing) => {
    await drawingApi.approve(record.uuid);
        messageApi.success(t('app.master-data.drawings.approveSuccess'));
        reloadAfterAction(record);
  };

  const handleReject = async (record: EngineeringDrawing) => {
    let reason = '';
    getAntdModal().confirm({
      title: t('app.master-data.drawings.reject'),
      content: (
        <Input.TextArea
          rows={3}
          placeholder={t('app.master-data.drawings.rejectReason')}
          onChange={(e) => {
            reason = e.target.value;
          }}
        />
      ),
      onOk: async () => {
        await drawingApi.reject(record.uuid, reason);
        messageApi.success(t('app.master-data.drawings.rejectSuccess'));
        reloadAfterAction(record);
      },
    });
  };

  const executeRevoke = async (record: EngineeringDrawing) => {
    await drawingApi.revoke(record.uuid);
        messageApi.success(t('app.master-data.drawings.revokeSuccess'));
        reloadAfterAction(record);
  };

  const handleObsolete = async (record: EngineeringDrawing) => {
    let reason = '';
    getAntdModal().confirm({
      title: t('app.master-data.drawings.obsolete'),
      content: (
        <Input.TextArea
          rows={3}
          placeholder={t('app.master-data.drawings.obsoleteReason')}
          onChange={(e) => {
            reason = e.target.value;
          }}
        />
      ),
      onOk: async () => {
        await drawingApi.obsolete(record.uuid, reason);
        messageApi.success(t('app.master-data.drawings.obsoleteSuccess'));
    actionRef.current?.reload();
        if (detail?.uuid === record.uuid) loadDetail(record.uuid);
      },
    });
  };

  const handleRevision = async (record: EngineeringDrawing) => {
    try {
      const created = await drawingApi.createRevision(record.uuid, {});
      messageApi.success(t('app.master-data.drawings.revisionSuccess'));
      actionRef.current?.reload();
      setRequireChangeSummaryOnEdit(true);
      setEditUuid(created.uuid);
      setModalVisible(true);
    } catch (err: any) {
      messageApi.error(err?.message || t('common.operationFailed'));
    }
  };

  const handleDeleteDrawing = useCallback(
    async (record: EngineeringDrawing) => {
      await drawingApi.delete(record.uuid);
      messageApi.success(t('common.deleteSuccess'));
      if (record.uuid === selectedRowUuid) {
        setSelectedRowUuid(null);
        setInlinePreviewFile(null);
        setSelectedDrawing(null);
      }
      if (detail?.uuid === record.uuid) {
        setDrawerVisible(false);
        setDetail(null);
      }
      actionRef.current?.reload();
    },
    [messageApi, t, selectedRowUuid, detail?.uuid],
  );

  const drawingRowsRef = useRef<EngineeringDrawing[]>([]);

  const handleBatchDeleteDrawings = useCallback(
    async (keys: React.Key[]) => {
      const rows = drawingRowsRef.current.filter((r) => keys.includes(r.uuid));
      if (!rows.length) return;
      for (const record of rows) {
        await drawingApi.delete(record.uuid);
        if (record.uuid === selectedRowUuid) {
          setSelectedRowUuid(null);
          setInlinePreviewFile(null);
          setSelectedDrawing(null);
        }
        if (detail?.uuid === record.uuid) {
          setDrawerVisible(false);
          setDetail(null);
        }
      }
      messageApi.success(t('common.batchDeleteSuccess', { count: rows.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    },
    [messageApi, t, selectedRowUuid, detail?.uuid],
  );

  const handleBatchSubmit = useCallback(
    async (keys: React.Key[]) => {
      const rows = drawingRowsRef.current.filter((r) => keys.includes(r.uuid));
      const eligible = rows.filter((r) => r.status === 'Draft');
      if (!eligible.length) {
        messageApi.warning(t('app.master-data.drawings.batchSubmitNotAllowed'));
        return;
      }
      let success = 0;
      let failed = 0;
      let lastError: unknown = null;
      for (const row of eligible) {
        try {
          await drawingApi.submit(row.uuid);
          success += 1;
        } catch (error) {
          failed += 1;
          lastError = error;
        }
      }
      if (success > 0) {
        messageApi.success(t('app.master-data.drawings.batchSubmitSuccess', { count: success }));
        setSelectedRowKeys([]);
        actionRef.current?.reload();
      }
      if (failed > 0) {
        messageApi.warning(
          getApiErrorMessage(
            lastError,
            t('app.master-data.drawings.batchSubmitPartial', { count: failed }),
          ),
        );
      }
    },
    [messageApi, t],
  );

  const handleBatchApprove = useCallback(
    async (keys: React.Key[]) => {
      const rows = drawingRowsRef.current.filter((r) => keys.includes(r.uuid));
      const eligible = rows.filter((r) => r.status === 'Pending');
      if (!eligible.length) {
        messageApi.warning(t('app.master-data.drawings.batchApproveNotAllowed'));
        return;
      }
      let success = 0;
      let failed = 0;
      let lastError: unknown = null;
      for (const row of eligible) {
        try {
          await drawingApi.approve(row.uuid);
          success += 1;
        } catch (error) {
          failed += 1;
          lastError = error;
        }
      }
      if (success > 0) {
        messageApi.success(t('app.master-data.drawings.batchApproveSuccess', { count: success }));
        setSelectedRowKeys([]);
        actionRef.current?.reload();
      }
      if (failed > 0) {
        messageApi.warning(
          getApiErrorMessage(
            lastError,
            t('app.master-data.drawings.batchApprovePartial', { count: failed }),
          ),
        );
      }
    },
    [messageApi, t],
  );

  const handleBatchMove = useCallback((keys: React.Key[]) => {
    const uuids = keys.map(String);
    if (!uuids.length) return;
    const rows = drawingRowsRef.current.filter((row) => uuids.includes(row.uuid));
    const folderIds = new Set(rows.map((row) => row.folderUuid ?? ''));
    setMoveFolder({
      open: true,
      drawingUuids: uuids,
      currentFolderUuid: folderIds.size === 1 ? rows[0]?.folderUuid ?? null : null,
    });
  }, []);

  const drawingBatchMenuItems = useMemo(() => {
    const items = [];
    if (canSubmit) {
      items.push({
        key: 'batchSubmit',
        label: t('app.master-data.drawings.batchSubmit'),
        icon: <SendOutlined />,
        requireConfirm: true,
        confirmTitle: t('common.submit'),
        confirmDescription: (count: number) =>
          t('app.master-data.drawings.batchSubmitConfirm', { count }),
        onClick: handleBatchSubmit,
      });
    }
    if (canApprove) {
      items.push({
        key: 'batchApprove',
        label: t('app.master-data.drawings.batchApprove'),
        icon: <CheckOutlined />,
        requireConfirm: true,
        confirmTitle: t('app.master-data.drawings.approve'),
        confirmDescription: (count: number) =>
          t('app.master-data.drawings.batchApproveConfirm', { count }),
        onClick: handleBatchApprove,
      });
    }
    if (canUpdate) {
      items.push({
        key: 'batchMove',
        label: t('app.master-data.drawings.folder.batchMove'),
        icon: <FolderOutlined />,
        onClick: handleBatchMove,
      });
    }
    return items;
  }, [canApprove, canSubmit, canUpdate, handleBatchApprove, handleBatchMove, handleBatchSubmit, t]);

  useEffect(() => {
    const deepLinkUuid = searchParams.get('uuid');
    if (!deepLinkUuid) return;

    void (async () => {
      try {
        const data = await drawingApi.get(deepLinkUuid);
        selectRowForPreview(data);
        handleOpenDetail(deepLinkUuid);
      } catch (err: any) {
        messageApi.error(err?.message || t('app.master-data.drawings.getDetailFailed'));
      } finally {
        setSearchParams({}, { replace: true });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅响应 URL 深链参数
  }, [searchParams.get('uuid')]);

  useEffect(() => {
    if (!detail?.uuid) {
      setRevisions([]);
      return;
    }
    let cancelled = false;
    setRevisionsLoading(true);
    void drawingApi
      .listRevisions(detail.uuid)
      .then((res) => {
        if (!cancelled) setRevisions(res.revisions ?? []);
      })
      .catch(() => {
        if (!cancelled) setRevisions([]);
      })
      .finally(() => {
        if (!cancelled) setRevisionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [detail?.uuid]);

  /** 列表「更多」：自管分组菜单（对齐 BOM 更多），图标齐全；确认类走 Modal */
  const buildDrawingMoreMenuItems = useCallback(
    (record: EngineeringDrawing, options?: { includePreview?: boolean }): MenuProps['items'] => {
      const includePreview = options?.includePreview === true;
      const editItems: NonNullable<MenuProps['items']> = [];
      const workflowItems: NonNullable<MenuProps['items']> = [];
      const versionItems: NonNullable<MenuProps['items']> = [];
      const collaborateItems: NonNullable<MenuProps['items']> = [];
      const fileItems: NonNullable<MenuProps['items']> = [];

      if (record.status === 'Draft') {
        if (canUpdate) {
          editItems.push({
            key: 'checkout',
            icon: <ExportOutlined />,
            label: t('app.master-data.drawings.checkout'),
            onClick: () => void handleCheckout(record),
          });
        }
        if (canSubmit) {
          workflowItems.push({
            key: 'submit',
            icon: <SendOutlined />,
            label: t('common.submit'),
            onClick: () => {
              getAntdModal().confirm({
                title: t('common.submit'),
                content: t('app.master-data.drawings.submitConfirm'),
                onOk: () => executeSubmit(record),
              });
            },
          });
        }
        if (canDelete) {
          editItems.push({
            key: 'delete',
            icon: <DeleteOutlined />,
            label: t('common.delete'),
            danger: true,
            onClick: () => {
              getAntdModal().confirm({
                title: t('common.confirmDelete'),
                okButtonProps: { danger: true },
                onOk: () => handleDeleteDrawing(record),
              });
            },
          });
        }
      }

      if (record.status === 'Editing' && isCheckoutOwner(record) && canUpdate) {
        editItems.push({
          key: 'edit',
          icon: <EditOutlined />,
          label: t('common.edit'),
          onClick: () => {
            setRequireChangeSummaryOnEdit(record.revision !== 'A');
            setEditUuid(record.uuid);
            setModalVisible(true);
          },
        });
        editItems.push({
          key: 'checkin',
          icon: <ImportOutlined />,
          label: t('app.master-data.drawings.checkin'),
          onClick: () => void handleCheckin(record),
        });
        editItems.push({
          key: 'undoCheckout',
          icon: <RollbackOutlined />,
          label: t('app.master-data.drawings.undoCheckout'),
          onClick: () => {
            getAntdModal().confirm({
              title: t('app.master-data.drawings.undoCheckout'),
              content: t('app.master-data.drawings.undoCheckoutConfirm'),
              onOk: () => executeUndoCheckout(record),
            });
          },
        });
      }

      if (record.status === 'Pending') {
        if (canApprove) {
          workflowItems.push({
            key: 'approve',
            icon: <AuditOutlined />,
            label: t('app.master-data.drawings.approve'),
            onClick: () => {
              getAntdModal().confirm({
                title: t('app.master-data.drawings.approve'),
                content: t('app.master-data.drawings.approveConfirm'),
                onOk: () => executeApprove(record),
              });
            },
          });
        }
        if (canReject) {
          workflowItems.push({
            key: 'reject',
            icon: <CloseCircleOutlined />,
            label: t('app.master-data.drawings.reject'),
            danger: true,
            onClick: () => handleReject(record),
          });
        }
        if (canRevoke) {
          workflowItems.push({
            key: 'revoke',
            icon: <RollbackOutlined />,
            label: t('app.master-data.drawings.revoke'),
            onClick: () => {
              getAntdModal().confirm({
                title: t('app.master-data.drawings.revoke'),
                content: t('app.master-data.drawings.revokeConfirm'),
                onOk: () => executeRevoke(record),
              });
            },
          });
        }
      }

      if (record.status === 'Released') {
        if (changePerms.canCreate) {
          versionItems.push({
            key: 'engineeringChange',
            icon: <DiffOutlined />,
            label: t('app.master-data.drawings.engineeringChange'),
            onClick: () => navigate(buildDrawingChangeCreateUrl(record.uuid)),
          });
        }
        if (canCreate) {
          versionItems.push({
            key: 'newRevision',
            icon: <CloudUploadOutlined />,
            label: t('app.master-data.drawings.newRevision'),
            onClick: () => void handleRevision(record),
          });
        }
        if (canObsolete) {
          versionItems.push({
            key: 'obsolete',
            icon: <DeleteOutlined />,
            label: t('app.master-data.drawings.obsolete'),
            danger: true,
            onClick: () => void handleObsolete(record),
          });
        }
      }

      if (whereUsedPerms.canRead) {
        collaborateItems.push({
          key: 'whereUsed',
          icon: <NodeIndexOutlined />,
          label: t('app.master-data.drawings.actionWhereUsed'),
          onClick: () => setWhereUsedDrawing(record),
        });
      }
      if (distPerms.canCreate && record.status === 'Released') {
        collaborateItems.push({
          key: 'distribute',
          icon: <SendOutlined />,
          label: t('app.master-data.drawings.actionDistribute'),
          onClick: () => setDistributeDrawing(record),
        });
      }
      if (loanPerms.canCreate && record.status === 'Released') {
        collaborateItems.push({
          key: 'loan',
          icon: <BookOutlined />,
          label: t('app.master-data.drawings.actionLoan'),
          onClick: () => setLoanDrawing(record),
        });
      }

      if (canDownload && record.file?.uuid) {
        fileItems.push({
          key: 'download',
          icon: <DownloadOutlined />,
          label: t('components.uniAction.downloadFirmware'),
          onClick: () => void handleDownloadDrawing(record),
        });
      }
      if (canPrint) {
        fileItems.push({
          key: 'print',
          icon: <PrinterOutlined />,
          label: t('common.print'),
          onClick: () => void openDrawingPrint(record),
        });
      }
      if (includePreview && record.file && !showInlinePreview) {
        fileItems.push({
          key: 'preview',
          icon: <EyeOutlined />,
          label: t('app.master-data.drawings.preview'),
          onClick: () => openPreview(record.file),
        });
      }
      if (canImport && canImportStepBom(record)) {
        fileItems.push({
          key: 'importStepBom',
          icon: <PartitionOutlined />,
          label: t('app.master-data.drawings.importStepBom'),
          onClick: () => openStepBomWizard(record),
        });
      }

      const items: NonNullable<MenuProps['items']> = [];
      const pushGroup = (key: string, label: string, children: NonNullable<MenuProps['items']>) => {
        if (!children.length) return;
        items.push({ type: 'group', key, label, children });
      };
      pushGroup('edit', t('app.master-data.drawings.actionGroup.edit'), editItems);
      pushGroup('workflow', t('app.master-data.drawings.actionGroup.workflow'), workflowItems);
      pushGroup('version', t('app.master-data.drawings.actionGroup.version'), versionItems);
      pushGroup('collaborate', t('app.master-data.drawings.actionGroup.collaborate'), collaborateItems);
      pushGroup('file', t('app.master-data.drawings.actionGroup.file'), fileItems);
      return items;
    },
    [
      t,
      showInlinePreview,
      canImport,
      canUpdate,
      canDelete,
      canSubmit,
      canApprove,
      canReject,
      canRevoke,
      canCreate,
      canObsolete,
      canPrint,
      canDownload,
      whereUsedPerms.canRead,
      distPerms.canCreate,
      loanPerms.canCreate,
      openDrawingPrint,
      openStepBomWizard,
      changePerms.canCreate,
      navigate,
      isCheckoutOwner,
      handleDeleteDrawing,
      handleObsolete,
      handleRevision,
      handleDownloadDrawing,
    ],
  );

  const renderDrawingRowActions = useCallback(
    (record: EngineeringDrawing): React.ReactNode[] => {
      const moreItems = buildDrawingMoreMenuItems(record);
      const nodes: React.ReactNode[] = [
        <Button key="view" {...rowActionKind('read')} onClick={() => handleOpenDetail(record.uuid)} />,
      ];
      if (moreItems && moreItems.length > 0) {
        nodes.push(
          <Dropdown key="more" {...rowActionKind('skip')} menu={{ items: moreItems }} trigger={['click']}>
            <Button
              type="text"
              size="small"
              className="ant-btn-row-action"
              icon={<MoreOutlined />}
              {...rowActionLabelKeep()}
            >
              {t('common.more')}
            </Button>
          </Dropdown>,
        );
      }
      return nodes;
    },
    [buildDrawingMoreMenuItems, t, handleOpenDetail],
  );

  /** 详情抽屉：仍直出按钮；图标走 uni-action 视觉配置 */
  const renderLifecycleActions = useCallback(
    (record: EngineeringDrawing, compact = false): React.ReactNode[] => {
      const nodes: React.ReactNode[] = [];
      if (canDownload && record.file?.uuid) {
        nodes.push(
          <Button
            key="download"
            {...rowActionDownloadFirmware(canExport ? 'export' : 'read')}
            onClick={() => void handleDownloadDrawing(record)}
          />,
        );
      }
      if (whereUsedPerms.canRead) {
        nodes.push(
          <Button key="whereUsed" {...rowActionDrawingWhereUsed('skip')} onClick={() => setWhereUsedDrawing(record)} />,
        );
      }
      if (distPerms.canCreate && record.status === 'Released') {
        nodes.push(
          <Button
            key="distribute"
            {...rowActionDrawingDistribute('skip')}
            onClick={() => setDistributeDrawing(record)}
          />,
        );
      }
      if (loanPerms.canCreate && record.status === 'Released') {
        nodes.push(
          <Button key="loan" {...rowActionDrawingLoan('skip')} onClick={() => setLoanDrawing(record)} />,
        );
      }
      if (canImport && canImportStepBom(record)) {
        // 抽屉 compact：走目录短文案「导入BOM」，勿 labelKeep 长句，避免标题区横向撑爆
        nodes.push(
          <Button
            key="importStepBom"
            {...rowActionDrawingImportStepBom(canImport ? 'import' : 'skip')}
            {...(compact ? {} : rowActionLabelKeep())}
            onClick={() => openStepBomWizard(record)}
          >
            {compact ? null : t('app.master-data.drawings.importStepBom')}
          </Button>,
        );
      }
      if (record.status === 'Draft') {
        if (canUpdate) {
          nodes.push(
            <Button
              key="checkout"
              {...rowActionDrawingCheckout('update')}
              onClick={() => handleCheckout(record)}
            />,
          );
        }
        if (canSubmit) {
          nodes.push(
            <ActionConfirmPopconfirm
              key="submit"
              title={t('common.submit')}
              description={t('app.master-data.drawings.submitConfirm')}
              onConfirm={() => executeSubmit(record)}
            >
              <Button {...rowActionKind('submit')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
          );
        }
        if (canDelete) {
          nodes.push(
            <Popconfirm
              key="delete"
              title={t('common.confirmDelete')}
              onConfirm={() => handleDeleteDrawing(record)}
            >
              <Button {...rowActionKind('delete')} onClick={(e) => e.stopPropagation()} />
            </Popconfirm>,
          );
        }
      }
      if (record.status === 'Editing' && isCheckoutOwner(record)) {
        if (canUpdate) {
          nodes.push(
            <Button
              key="edit"
              {...rowActionKind('update')}
              onClick={() => {
                setRequireChangeSummaryOnEdit(record.revision !== 'A');
                setEditUuid(record.uuid);
                setModalVisible(true);
              }}
            />,
          );
          nodes.push(
            <Button key="checkin" {...rowActionDrawingCheckin('update')} onClick={() => handleCheckin(record)} />,
          );
          nodes.push(
            <ActionConfirmPopconfirm
              key="undoCheckout"
              title={t('app.master-data.drawings.undoCheckout')}
              description={t('app.master-data.drawings.undoCheckoutConfirm')}
              onConfirm={() => executeUndoCheckout(record)}
            >
              <Button {...rowActionDrawingUndoCheckout('update')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
          );
        }
      }
      if (record.status === 'Pending') {
        if (canApprove) {
          nodes.push(
            <ActionConfirmPopconfirm
              key="approve"
              title={t('app.master-data.drawings.approve')}
              description={t('app.master-data.drawings.approveConfirm')}
              onConfirm={() => executeApprove(record)}
            >
              <Button {...rowActionKind('approve')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
          );
        }
        if (canReject) {
          nodes.push(
            <Button key="reject" {...rowActionKind('reject')} onClick={() => handleReject(record)} />,
          );
        }
        if (canRevoke) {
          nodes.push(
            <ActionConfirmPopconfirm
              key="revoke"
              title={t('app.master-data.drawings.revoke')}
              description={t('app.master-data.drawings.revokeConfirm')}
              onConfirm={() => executeRevoke(record)}
            >
              <Button {...rowActionKind('revoke')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
          );
        }
      }
      if (record.status === 'Released') {
        if (changePerms.canCreate) {
          nodes.push(
            <Button
              key="engineeringChange"
              {...rowActionDrawingEngineeringChange('skip')}
              onClick={() => navigate(buildDrawingChangeCreateUrl(record.uuid))}
            />,
          );
        }
        if (canCreate) {
          nodes.push(
            <Button
              key="create"
              {...rowActionDrawingNewRevision('create')}
              onClick={() => handleRevision(record)}
            />,
          );
        }
        if (canObsolete) {
          nodes.push(
            <Button
              key="obsolete"
              {...rowActionKind('obsolete')}
              onClick={() => handleObsolete(record)}
            />,
          );
        }
      }
      if (canPrint) {
        nodes.push(
          <Button key="print" {...rowActionKind('print')} onClick={() => void openDrawingPrint(record)} />,
        );
      }
      if (!compact && record.file && !showInlinePreview) {
        nodes.push(
          <Button
            key="preview"
            {...rowActionKind('read')}
            {...rowActionLabelKeep()}
            onClick={() => openPreview(record.file)}
          >
            {t('app.master-data.drawings.preview')}
          </Button>,
        );
      }
      // 抽屉 extra 不经操作列 normalize，须主动注入图标/文案，否则会渲染成空按钮框
      return nodes.map((node) =>
        normalizeActionTree(node, { suppressAuditSemanticActions: false }),
      );
    },
    [
      t,
      showInlinePreview,
      canImport,
      canUpdate,
      canDelete,
      canSubmit,
      canApprove,
      canReject,
      canRevoke,
      canCreate,
      canObsolete,
      canPrint,
      canDownload,
      canExport,
      whereUsedPerms.canRead,
      distPerms.canCreate,
      loanPerms.canCreate,
      openDrawingPrint,
      openStepBomWizard,
      changePerms.canCreate,
      navigate,
      isCheckoutOwner,
      handleDeleteDrawing,
      handleObsolete,
      handleRevision,
      handleDownloadDrawing,
    ],
  );

  const detailColumns: ProDescriptionsItemProps<EngineeringDrawing>[] = useMemo(
    () => [
      { title: t('app.master-data.drawings.code'), dataIndex: 'code' },
      { title: t('app.master-data.drawings.name'), dataIndex: 'name' },
      { title: t('app.master-data.drawings.revision'), dataIndex: 'revision' },
      {
        title: t('app.master-data.drawings.folder'),
        dataIndex: 'folderName',
        render: (_, r) => r.folderName || t('app.master-data.drawings.tree.unclassified'),
      },
      {
        title: t('app.master-data.drawings.type'),
        dataIndex: 'drawingType',
        render: (_, r) =>
          r.drawingType ? (
            <DictionaryLabel
              dictionaryCode={DRAWING_TYPE_DICTIONARY_CODE}
              value={r.drawingType}
              notFoundPlaceholder={typeLabel(r.drawingType)}
            />
          ) : (
            '-'
          ),
      },
      {
        title: t('app.master-data.drawings.securityLevel'),
        dataIndex: 'securityLevel',
        render: (_, r) =>
          r.securityLevel ? (
            <MarkerTag color="geekblue">{t(`app.master-data.drawings.securityLevel.${r.securityLevel}`)}</MarkerTag>
          ) : (
            '-'
          ),
      },
      {
        title: t('app.master-data.drawings.drawingFormat'),
        dataIndex: 'drawingFormat',
        render: (_, r) =>
          r.drawingFormat
            ? t(`app.master-data.drawings.drawingFormat.${r.drawingFormat}`)
            : '-',
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        render: (_, r) => <MarkerTag color={STATUS_COLOR[r.status]}>{statusLabel(r.status)}</MarkerTag>,
      },
      {
        title: t('app.master-data.drawings.file'),
        dataIndex: 'file',
        render: (_, r) =>
          r.file ? (
            <Space orientation="vertical" size={0}>
              <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openPreview(r.file)}>
                {r.file.originalName}
              </Button>
              {canImport && canImportStepBom(r) && (
                <Button
                  type="link"
                  size="small"
                  icon={<PartitionOutlined />}
                  onClick={() => openStepBomWizard(r)}
                >
                  {t('app.master-data.drawings.importStepBom')}
                </Button>
              )}
            </Space>
          ) : (
            '-'
          ),
      },
      {
        title: t('app.master-data.drawings.supplementaryFiles'),
        dataIndex: 'supplementaryFiles',
        render: (_, r) =>
          r.supplementaryFiles?.length ? (
            <Space orientation="vertical" size={0}>
              {r.supplementaryFiles.map((f) => (
                <Button key={f.uuid} type="link" size="small" onClick={() => openPreview(f)}>
                  {f.originalName}
                </Button>
              ))}
            </Space>
          ) : (
            '-'
          ),
      },
      {
        title: t('app.master-data.drawings.project'),
        dataIndex: 'projectCode',
        render: (_, r) => formatProjectRefLabel(r.projectCode, r.projectName) || '-',
      },
      {
        title: t('app.master-data.drawings.materials'),
        dataIndex: 'materials',
        render: (_, r) => formatAssociationLabels(r.materials),
      },
      {
        title: t('app.master-data.drawings.linkedBom'),
        dataIndex: 'linkedBom',
        render: (_, r) => {
          if (r.linkedBom) {
            return (
              <Button
                type="link"
                size="small"
                style={{ padding: 0 }}
                onClick={() =>
                  navigate(bomDesignerPath(r.linkedBom!.materialId, r.linkedBom!.version))
                }
              >
                {r.linkedBom.materialCode} v{r.linkedBom.version}
              </Button>
            );
          }
          if (!r.linkedBomMaterialId || !r.linkedBomVersion) return '-';
          return (
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={() => navigate(bomDesignerPath(r.linkedBomMaterialId!, r.linkedBomVersion!))}
            >
              v{r.linkedBomVersion}
            </Button>
          );
        },
      },
      {
        title: t('app.master-data.drawings.lastStepBomImportAt'),
        dataIndex: 'lastStepBomImportAt',
        valueType: 'dateTime',
      },
      {
        title: t('app.master-data.drawings.routes'),
        dataIndex: 'processRoutes',
        render: (_, r) => formatAssociationLabels(r.processRoutes),
      },
      {
        title: t('app.master-data.drawings.operations'),
        dataIndex: 'operations',
        render: (_, r) => formatAssociationLabels(r.operations),
      },
      { title: t('common.remark'), dataIndex: 'description' },
      {
        title: t('app.master-data.drawings.checkedOutBy'),
        dataIndex: 'checkedOutByName',
        render: (_, r) => r.checkedOutByName || '-',
      },
      { title: t('app.master-data.drawings.releasedAt'), dataIndex: 'releasedAt', valueType: 'dateTime' },
      { title: t('app.master-data.drawings.obsoleteReason'), dataIndex: 'obsoleteReason' },
      { title: t('common.createdAt'), dataIndex: 'createdAt', valueType: 'dateTime' },
      { title: t('common.updatedAt'), dataIndex: 'updatedAt', valueType: 'dateTime' },
    ],
    [t, showInlinePreview, navigate, openStepBomWizard, canImport],
  );

  const columns: ProColumns<EngineeringDrawing>[] = useMemo(
    () => {
      const customFieldColumns = generateCustomFieldColumns();
      return [
      {
        // 名称/图号叠列 = 唯一 RemainderFlex（长短不一；禁止再叠 primaryFlexMax）
        title: t('app.master-data.drawings.name'),
        dataIndex: 'name',
        minWidth: 200,
        uniTableRemainderFlex: true,
        uniTablePrimaryFlex: true,
        resizable: false,
        ellipsis: false,
        fixed: 'left' as const,
        render: (_, record) => (
          <UniTableStackedPrimaryCell
            primary={String(record.name ?? '')}
            secondary={String(record.code ?? '')}
          />
        ),
      },
      {
        title: t('app.master-data.drawings.code'),
        dataIndex: 'code',
        hideInTable: true,
      },
      {
        title: t('app.master-data.drawings.revision'),
        dataIndex: 'revision',
        width: 112,
        minWidth: 112,
        uniTableKeepWidth: true,
        resizable: false,
      },
      {
        title: t('app.master-data.drawings.folder'),
        dataIndex: 'folderName',
        search: false,
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        render: (_, record) => record.folderName || t('app.master-data.drawings.tree.unclassified'),
      },
      {
        title: t('app.master-data.drawings.type'),
        dataIndex: 'drawingType',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        valueType: 'select',
        valueEnum: {
          part: { text: t('app.master-data.drawings.type.part') },
          assembly: { text: t('app.master-data.drawings.type.assembly') },
          process: { text: t('app.master-data.drawings.type.process') },
          other: { text: t('app.master-data.drawings.type.other') },
        },
        render: (_, r) =>
          r.drawingType ? (
            <MarkerTag color="processing">
              <DictionaryLabel
                dictionaryCode={DRAWING_TYPE_DICTIONARY_CODE}
                value={r.drawingType}
                notFoundPlaceholder={typeLabel(r.drawingType)}
              />
            </MarkerTag>
          ) : (
            '-'
          ),
      },
      {
        title: t('app.master-data.drawings.securityLevel'),
        dataIndex: 'securityLevel',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        valueType: 'select',
        valueEnum: {
          public: { text: t('app.master-data.drawings.securityLevel.public') },
          internal: { text: t('app.master-data.drawings.securityLevel.internal') },
          secret: { text: t('app.master-data.drawings.securityLevel.secret') },
          confidential: { text: t('app.master-data.drawings.securityLevel.confidential') },
        },
        render: (_, r) =>
          r.securityLevel ? (
            <MarkerTag color="geekblue">{t(`app.master-data.drawings.securityLevel.${r.securityLevel}`)}</MarkerTag>
          ) : (
            '-'
          ),
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        hideInTable: true,
        valueType: 'select',
        valueEnum: {
          Draft: { text: t('app.master-data.drawings.status.Draft') },
          Editing: { text: t('app.master-data.drawings.status.Editing') },
          Pending: { text: t('app.master-data.drawings.status.Pending') },
          Released: { text: t('app.master-data.drawings.status.Released') },
          Obsolete: { text: t('app.master-data.drawings.status.Obsolete') },
        },
      },
      {
        title: t('app.master-data.drawings.checkedOutBy'),
        dataIndex: 'checkedOutByName',
        search: false,
        width: 120,
        minWidth: 120,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        render: (_, r) => r.checkedOutByName || '-',
      },
      {
        title: t('app.master-data.drawings.linkedBom'),
        key: 'drawing_linked_bom',
        dataIndex: 'linkedBom',
        search: false,
        width: 168,
        minWidth: 168,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        render: (_, r) => {
          if (r.linkedBom) {
            return (
              <Button
                type="link"
                size="small"
                style={{ padding: 0 }}
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(bomDesignerPath(r.linkedBom!.materialId, r.linkedBom!.version));
                }}
              >
                {r.linkedBom.materialCode} v{r.linkedBom.version}
              </Button>
            );
          }
          if (!r.linkedBomMaterialId || !r.linkedBomVersion) return '-';
          return (
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={(e) => {
                e.stopPropagation();
                navigate(bomDesignerPath(r.linkedBomMaterialId!, r.linkedBomVersion!));
              }}
            >
              v{r.linkedBomVersion}
            </Button>
          );
        },
      },
      {
        title: t('app.master-data.drawings.file'),
        key: 'drawing_file_name',
        dataIndex: ['file', 'originalName'],
        ellipsis: true,
        search: false,
        width: 200,
        minWidth: 200,
        uniTableKeepWidth: true,
        resizable: false,
      },
      {
        title: t('app.master-data.drawings.releasedAt'),
        dataIndex: 'releasedAt',
        search: false,
        ...UNI_TABLE_SITE_DATETIME_COLUMN_DEFAULTS,
      },
      ...masterCrudCreatedUpdatedColumns<EngineeringDrawing>(t),
      ...customFieldColumns,
      {
        title: t('common.status'),
        key: 'lifecycle',
        dataIndex: 'status',
        fixed: 'right' as const,
        hideInSearch: true,
        render: (_, r) => <StatusTag color={STATUS_COLOR[r.status]}>{statusLabel(r.status)}</StatusTag>,
      },
      {
        title: t('common.actions'),
        key: 'action',
        fixed: 'right' as const,
        hideInSearch: true,
        onCell: () => ({ style: { whiteSpace: 'nowrap' } }),
        render: (_, record) => renderDrawingRowActions(record),
      },
    ];
    },
    [t, customFields, generateCustomFieldColumns, renderDrawingRowActions, navigate, statusLabel],
  );

  const tableQueryKey = useMemo(
    () => [
      'apps.master-data.pages.process.drawings',
      paneMode,
      navMode,
      listView,
      treeFilter.drawingType ?? '',
      treeFilter.status ?? '',
      treeFilter.materialUuid ?? '',
      treeFilter.processRouteUuid ?? '',
      treeFilter.folderUuid ?? '',
      treeFilter.unclassified ? '1' : '',
    ],
    [paneMode, navMode, listView, treeFilter],
  );

  const tableScrollOffsetPx =
    LIST_PAGE_TABLE_SCROLL.BASE_OFFSET_PX + 2 * LIST_PAGE_TABLE_SCROLL.GAP_PX;

  const handleOpenLargePreview = useCallback(() => {
    if (inlinePreviewFile?.uuid) setLargePreviewOpen(true);
  }, [inlinePreviewFile?.uuid]);

  const tableBlock = useMemo(
    () => (
      <div
        className="drawings-table-pane"
        style={{
          flex: showPreviewPane ? '3 1 0' : 1,
          minWidth: 0,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          padding: showPreviewPane ? '0 0 8px 8px' : '0 8px 8px',
          boxSizing: 'border-box',
          ['--uni-table-scroll-offset' as string]: `${tableScrollOffsetPx}px`,
        }}
      >
        <UniTable<EngineeringDrawing>
        viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('masterData.drawings')}
          actionRef={actionRef}
          rowKey="uuid"
          columnPersistenceId="apps.master-data.pages.process.drawings.folder-v9"
          showAdvancedSearch
          permissionResource={DRAWING_PERMISSION}
          params={{ drawingTreeFilter: treeFilter, listView }}
          tanstackQuery={{ queryKeyPrefix: tableQueryKey }}
          columns={alignProColumns(columns, MASTER_DATA_LIST_FIELD_RANK)}
          headerTitle={t('app.master-data.menu.process.drawings')}
          beforeSearchButtons={
            <>
              <Tooltip title={leftPanelCollapsed ? t('app.master-data.drawings.expandNav') : t('app.master-data.drawings.collapseNav')}>
                <Button
                  icon={leftPanelCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                  onClick={() => setLeftPanelCollapsed((v) => !v)}
                />
              </Tooltip>
              <ThemedSegmented
                surfaceBackground
                size="medium"
                value={listView}
                options={[
                  { label: t('app.master-data.drawings.viewCurrent'), value: 'current' },
                  { label: t('app.master-data.drawings.viewAllRevisions'), value: 'all' },
                ]}
                onChange={(value) => {
                  const next = value as DrawingListView;
                  listViewRef.current = next;
                  setListView(next);
                }}
              />
            </>
          }
          showCreateButton
          createButtonText={t('app.master-data.drawings.createTitle')}
          onCreate={handleCreate}
          toolBarActionsAfterCreate={
            canCreate
              ? [
                  <Button
                    key="batch-upload"
                    icon={<UploadOutlined />}
                    onClick={() => setBatchUploadOpen(true)}
                  >
                    {t('app.master-data.drawings.batchUpload')}
                  </Button>,
                ]
              : []
          }
          enableRowSelection={canDelete || canSubmit || canApprove || canUpdate}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          showDeleteButton={canDelete}
          deleteConfirmTitle={t('common.batchDeleteTitle')}
          deleteConfirmDescription={(count) => t('common.batchDeleteContent', { count })}
          onDelete={handleBatchDeleteDrawings}
          toolBarActionsAfterDelete={[
            ...(drawingBatchMenuItems.length > 0
              ? [
                  <UniBatchMenuButton
                    key="drawing-batch-menu"
                    selectedRowKeys={selectedRowKeys}
                    menuItems={drawingBatchMenuItems}
                    buttonText={t('app.master-data.drawings.batchActions')}
                  />,
                ]
              : []),
            ...(canUpdate
              ? [
                  <Button
                    key="drawing-watermark-settings"
                    icon={<SettingOutlined />}
                    onClick={() => setWatermarkSettingsOpen(true)}
                  >
                    {t('app.master-data.drawings.watermark.settingsButton')}
                  </Button>,
                ]
              : []),
            ...(distPerms.canRead
              ? [
                  <Space key="drawing-dist-policy">
                    <span>{t('app.master-data.drawingDistributions.policyLabel')}</span>
                    <Switch
                      checked={distPolicyEnabled}
                      loading={distPolicyLoading}
                      disabled={!distPerms.canUpdate}
                      onChange={async (checked) => {
                        setDistPolicyLoading(true);
                        try {
                          const next = await drawingDistributionApi.updatePolicy(checked);
                          setDistPolicyEnabled(!!next.isEnabled);
                          messageApi.success(t('app.master-data.drawingDistributions.policyUpdated'));
                        } catch (e) {
                          messageApi.error(getApiErrorMessage(e) || t('common.saveFailed'));
                        } finally {
                          setDistPolicyLoading(false);
                        }
                      }}
                    />
                  </Space>,
                ]
              : []),
          ]}
          onTableDataChange={(rows) => {
            drawingRowsRef.current = rows;
          }}
          skipFuzzyPinyinClientFilter
          request={async (params, _sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
            try {
              const tf = (params.drawingTreeFilter ?? {}) as DrawingTreeFilter;
              const keyword = pickListSearchKeywordOrFields(searchFormValues, 'name', 'code');
              const advancedStatus = pickSearchString(searchFormValues, 'status') as
                | DrawingStatus
                | undefined;
              const advancedDrawingType = pickSearchString(searchFormValues, 'drawingType') as
                | DrawingType
                | undefined;
              const view =
                (params.listView as DrawingListView | undefined) ?? listViewRef.current;
              const res = await drawingApi.list({
                skip: ((params.current || 1) - 1) * (params.pageSize || 20),
                limit: params.pageSize || 20,
                keyword,
                status: advancedStatus ?? tf.status,
                drawingType: advancedDrawingType ?? tf.drawingType,
                securityLevel: pickSearchString(searchFormValues, 'securityLevel') as
                  | DrawingSecurityLevel
                  | undefined,
                materialUuid: tf.materialUuid,
                processRouteUuid: tf.processRouteUuid,
                folderUuid: tf.folderUuid,
                unclassified: tf.unclassified,
                view,
              });
              const enriched = meta?.purpose === 'prefetch'
                ? res.data ?? []
                : await enrichRecordsWithCustomFields(res.data ?? []);
              return { data: enriched, success: true, total: res.total ?? 0 };
            } catch (err: any) {
              messageApi.error(err?.message || t('app.master-data.drawings.listFailed'));
              return { data: [], success: false, total: 0 };
            }
          }}
          onRow={(record) => ({
            onClick: () => selectRowForPreview(record),
            style: { cursor: 'pointer' },
          })}
          rowClassName={(record) => (record.uuid === selectedRowUuid ? 'ant-table-row-selected' : '')}
        />
      </div>
    ),
    [
      showPreviewPane,
      tableScrollOffsetPx,
      tableQueryKey,
      columns,
      t,
      leftPanelCollapsed,
      handleCreate,
      canCreate,
      canDelete,
      canSubmit,
      canApprove,
      drawingBatchMenuItems,
      messageApi,
      selectedRowUuid,
      selectedRowKeys,
      selectRowForPreview,
      listView,
      treeFilter,
      enrichRecordsWithCustomFields,
    ],
  );

  return (
    <>
      <style>{`
        .drawings-table-pane .pro-table-button-container {
          height: ${TWO_COLUMN_LAYOUT.PANEL_HEADER_HEIGHT}px;
          box-sizing: border-box;
          padding: 8px;
          margin-top: 0;
          margin-bottom: 16px;
          border-bottom: 1px solid var(--ant-color-border);
          align-items: center;
          line-height: 32px;
          flex-wrap: nowrap;
        }
        .drawings-main-split .drawings-inline-preview-pane {
          align-self: stretch;
        }
      `}</style>
      <TwoColumnLayout
        layoutPersistenceId="apps.master-data.pages.process.drawings"
        leftPanel={{
          collapsed: leftPanelCollapsed,
          search: {
            placeholder: t('app.master-data.drawings.tree.searchPlaceholder'),
            value: treeSearch,
            onChange: setTreeSearch,
            allowClear: true,
          },
          actions: [paneModeBar, paneMode === 'filter' ? navModeBar : folderTreeActions].filter(Boolean),
          tree: {
            treeData,
            selectedKeys: selectedTreeKeys,
            expandedKeys,
            onExpand: handleTreeExpand,
            onSelect: handleTreeSelect,
            showIcon: true,
            blockNode: true,
            loading: treeLoading,
            loadingTip: t('app.master-data.drawings.tree.loadingNav'),
            className: 'drawing-nav-tree',
            titleRender: paneMode === 'vault' ? renderVaultFolderTitle : undefined,
            onRightClick: ({ event, node }) => {
              event.preventDefault();
              if (paneMode !== 'vault' || !(canUpdate || canDelete || canCreate)) return;
              const folderUuid = folderUuidFromTreeKey(String(node.key));
              if (!folderUuid) return;
              const folder = findDrawingFolderByUuid(folders, folderUuid);
              if (!folder) return;
              setFolderCtx({
                x: event.clientX,
                y: event.clientY,
                uuid: folder.uuid,
                name: folder.name,
              });
            },
          },
        }}
        rightPanel={{
          contentPadding: 0,
          content: (
            <div
              className="drawings-main-split"
              style={{
                display: 'flex',
                flexDirection: showPreviewPane ? 'row' : 'column',
                height: '100%',
                minHeight: 0,
              }}
            >
              {tableBlock}
              {showPreviewPane && (
                <InlinePreviewPane
                  file={deferredPreviewFile}
                  activeDrawing={selectedDrawing}
                  previewPending={previewPending}
                  canImportStepBomAction={canImport}
                  onOpenLargePreview={handleOpenLargePreview}
                  onOpenStepBom={openStepBomWizard}
                />
              )}
            </div>
          ),
        }}
      />

      <ProcessMasterDetailDrawer
        title={t('app.master-data.drawings.detailTitle')}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          setDetail(null);
          setDetailError(null);
          resetDetailFieldValues();
        }}
        loading={detailLoading}
        error={detailError}
        onRetry={() => {
          const uuid = detailRetryUuidRef.current;
          if (uuid) void loadDetail(uuid);
        }}
        detail={detail}
        detailColumns={detailColumns}
        customFields={customFields}
        customFieldValues={customFieldValues}
        extra={
          detail ? (
            <DetailDrawerActions
              items={[
                {
                  key: 'lifecycle',
                  // 与操作列同一套溢出：主行少量直出，其余进「更多」，避免标题被挤成竖排
                  render: renderRowActionsOverflow(
                    renderLifecycleActions(detail, true),
                    `drawing-detail-${detail.uuid}`,
                    { directMax: 3 },
                  ),
                },
              ]}
            />
          ) : null
        }
        linesTitle={t('app.master-data.drawings.detailRecords')}
        lines={
          <DrawingDetailRecordTabs
            drawing={detail}
            revisions={revisions}
            revisionsLoading={revisionsLoading}
            statusLabel={statusLabel}
            statusColor={STATUS_COLOR}
            reloadToken={detailRecordsReloadToken}
            onOpenRevision={(rev) => {
              if (rev.uuid !== detail?.uuid) {
                detailRetryUuidRef.current = rev.uuid;
                void loadDetail(rev.uuid);
                if (rev.uuid) {
                  void drawingApi.get(rev.uuid).then(selectRowForPreview);
                }
              }
            }}
          />
        }
      />

      <DrawingWhereUsedModal
        open={!!whereUsedDrawing}
        drawing={whereUsedDrawing}
        onClose={() => setWhereUsedDrawing(null)}
      />
      <DrawingDistributeFromDrawingModal
        open={!!distributeDrawing}
        drawing={distributeDrawing}
        onClose={() => setDistributeDrawing(null)}
        onSuccess={() => {
          setDetailRecordsReloadToken((n) => n + 1);
          actionRef.current?.reload();
        }}
      />
      <DrawingLoanFromDrawingModal
        open={!!loanDrawing}
        drawing={loanDrawing}
        onClose={() => setLoanDrawing(null)}
        onSuccess={() => {
          setDetailRecordsReloadToken((n) => n + 1);
          actionRef.current?.reload();
        }}
      />

      {folderCtx ? (
        <Dropdown
          open
          trigger={['click']}
          onOpenChange={(open) => {
            if (!open) setFolderCtx(null);
          }}
          menu={{
            items: [
              canCreate
                ? {
                    key: 'child',
                    label: t('app.master-data.drawings.folder.createChild'),
                    onClick: () => {
                      setFolderForm({ open: true, mode: 'create', parentUuid: folderCtx.uuid });
                      setFolderCtx(null);
                    },
                  }
                : null,
              canUpdate
                ? {
                    key: 'rename',
                    label: t('common.edit'),
                    onClick: () => {
                      openEditFolder(folderCtx);
                      setFolderCtx(null);
                    },
                  }
                : null,
              canDelete
                ? {
                    key: 'delete',
                    danger: true,
                    label: t('common.delete'),
                    onClick: () => {
                      const target = folderCtx;
                      setFolderCtx(null);
                      confirmDeleteFolder(target);
                    },
                  }
                : null,
            ],
          }}
        >
          <span style={{ position: 'fixed', left: folderCtx.x, top: folderCtx.y, width: 1, height: 1 }} />
        </Dropdown>
      ) : null}

      <DrawingFolderFormModal
        open={folderForm.open}
        mode={folderForm.mode}
        parentUuid={folderForm.parentUuid}
        folderUuid={folderForm.folderUuid}
        initialName={folderForm.initialName}
        onClose={() => setFolderForm((prev) => ({ ...prev, open: false }))}
        onSuccess={() => {
          void loadFolders();
        }}
      />

      <DrawingWatermarkSettingsModal
        open={watermarkSettingsOpen}
        onClose={() => setWatermarkSettingsOpen(false)}
      />

      <DrawingMoveFolderModal
        open={moveFolder.open}
        drawingUuids={moveFolder.drawingUuids}
        folders={folders}
        currentFolderUuid={moveFolder.currentFolderUuid}
        onClose={() => setMoveFolder({ open: false, drawingUuids: [] })}
        onSuccess={() => {
          setSelectedRowKeys([]);
          actionRef.current?.reload();
          void loadFolders();
          if (detail?.uuid && moveFolder.drawingUuids.includes(detail.uuid)) {
            void loadDetail(detail.uuid);
          }
        }}
      />

      <DrawingFormModal
        open={modalVisible}
        editUuid={editUuid}
        defaultFolderUuid={defaultCreateFolderUuid}
        folders={folders}
        requireChangeSummary={requireChangeSummaryOnEdit}
        onClose={() => {
          setModalVisible(false);
          setEditUuid(null);
          setRequireChangeSummaryOnEdit(false);
        }}
        onSuccess={() => {
          actionRef.current?.reload();
          void loadFolders();
        }}
      />

      <DrawingBatchUploadModal
        open={batchUploadOpen}
        defaultFolderUuid={defaultCreateFolderUuid}
        folders={folders}
        onClose={() => setBatchUploadOpen(false)}
        onSuccess={() => {
          actionRef.current?.reload();
          void loadFolders();
        }}
      />

      <FilePreviewModal
        open={(!showInlinePreview && previewOpen) || largePreviewOpen}
        onClose={() => {
          setPreviewOpen(false);
          setLargePreviewOpen(false);
          if (!showInlinePreview) setPreviewFile(null);
        }}
        fileUuid={largePreviewOpen ? inlinePreviewFile?.uuid : previewFile?.uuid}
        fileName={largePreviewOpen ? inlinePreviewFile?.originalName : previewFile?.originalName}
        fileExtension={largePreviewOpen ? inlinePreviewFile?.fileExtension : previewFile?.fileExtension}
        title={
          (largePreviewOpen ? inlinePreviewFile?.originalName : previewFile?.originalName) ||
          t('app.master-data.drawings.preview')
        }
        width="calc(100vw - 32px)"
        height="calc(100vh - 32px)"
      />

      <StepBomImportWizard
        open={stepBomOpen}
        drawingUuid={stepBomDrawing?.uuid ?? ''}
        drawing={stepBomDrawing ?? undefined}
        onClose={() => {
          setStepBomOpen(false);
          setStepBomDrawing(null);
        }}
        onSuccess={(result) => {
    actionRef.current?.reload();
          if (detail?.uuid === result.drawing.uuid) {
            setDetail(result.drawing);
          }
          if (selectedDrawing?.uuid === result.drawing.uuid) {
            setSelectedDrawing(result.drawing);
          }
        }}
      />
    </>
  );
};

export default DrawingsPage;
