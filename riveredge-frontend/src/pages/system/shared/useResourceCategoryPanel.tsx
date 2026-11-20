/**
 * 资源分类左栏面板逻辑（接口 / 数据集共用）
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Dropdown, Space, Tooltip } from 'antd';
import { DeleteOutlined, EditOutlined, FolderOutlined, PlusOutlined } from '@ant-design/icons';
import type { DataNode, TreeProps } from 'antd/es/tree';
import type { MenuProps } from 'antd';
import type { LeftPanelConfig } from '../../../components/layout-templates/TwoColumnLayout';
import { twoColumnLeftPanelWidthStorageKey } from '../../../components/layout-templates/constants';
import {
  deleteResourceCategory,
  listResourceCategories,
  loadFunctionCategoryPresets,
  RESOURCE_CATEGORY_ALL_KEY,
  RESOURCE_CATEGORY_UNCATEGORIZED_KEY,
  supportsFunctionCategoryPresets,
  type APIRelatedDocumentGroupCount,
  type ResourceCategory,
  type ResourceCategoryListFilter,
  type ResourceCategoryType,
} from '../../../services/resourceCategory';
import {
  API_TREE_DOC_ALL,
  API_TREE_DOC_NONE,
  API_TREE_DOC_SEP,
  buildApiCategoryTreeDocKey,
  groupCountsForCategory,
  normalizeApiCategoryTreeSelectKey,
  resolveApiCategoryTreeKey,
} from '../apis/apiCategoryTree';
import { ResourceCategoryFormModal } from './ResourceCategoryFormModal';

export interface UseResourceCategoryPanelOptions {
  resourceType: ResourceCategoryType;
  /** 分类切换时同步传入下一筛选条件，避免 reload 早于 state 提交导致列表错位 */
  onSelectionChange?: (nextFilter: ResourceCategoryListFilter) => void;
  /** 功能域预置完成并回填条目后刷新右侧列表 */
  onFunctionPresetsApplied?: () => void;
}

export interface UseResourceCategoryPanelResult {
  leftPanel: LeftPanelConfig;
  listFilter: ResourceCategoryListFilter;
  selectedCategoryKey: string;
  categories: ResourceCategory[];
  categorySelectOptions: { label: string; value: string }[];
  reloadCategories: () => Promise<void>;
  categoryFormModal: React.ReactNode;
}

function withCount(label: string, count?: number): string {
  return typeof count === 'number' && Number.isFinite(count) ? `${label} (${count})` : label;
}

function stopTreeNodeActionEvent(event: React.MouseEvent | React.KeyboardEvent) {
  event.preventDefault();
  event.stopPropagation();
}

export function useResourceCategoryPanel(
  options: UseResourceCategoryPanelOptions,
): UseResourceCategoryPanelResult {
  const { resourceType, onSelectionChange, onFunctionPresetsApplied } = options;
  const { t } = useTranslation();
  const { message: messageApi, modal: modalApi } = App.useApp();

  const [categories, setCategories] = useState<ResourceCategory[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [uncategorizedCount, setUncategorizedCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const [selectedCategoryKey, setSelectedCategoryKey] = useState(RESOURCE_CATEGORY_ALL_KEY);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([RESOURCE_CATEGORY_ALL_KEY]);

  const [formOpen, setFormOpen] = useState(false);
  const [formIsEdit, setFormIsEdit] = useState(false);
  const [editingCategory, setEditingCategory] = useState<ResourceCategory | null>(null);
  const [loadFunctionPresetsLoading, setLoadFunctionPresetsLoading] = useState(false);
  const [apiDocGroupCounts, setApiDocGroupCounts] = useState<APIRelatedDocumentGroupCount[]>([]);
  const [apiDocOptionCodes, setApiDocOptionCodes] = useState<string[]>([]);

  const showFunctionPresets = supportsFunctionCategoryPresets(resourceType);
  const enableApiRelatedDocumentGroups = resourceType === 'api';

  const reloadCategories = useCallback(async () => {
    try {
      setLoading(true);
      const result = await listResourceCategories(resourceType);
      setCategories(result.items);
      setTotalCount(result.total_count);
      setUncategorizedCount(result.uncategorized_count);
      if (enableApiRelatedDocumentGroups) {
        setApiDocGroupCounts(result.related_document_group_counts ?? []);
        setApiDocOptionCodes(
          (result.related_document_options ?? []).map(item => item.code),
        );
      }
    } catch (error: unknown) {
      const err = error as { message?: string };
      messageApi.error(err?.message || t('pages.system.resourceCategory.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [enableApiRelatedDocumentGroups, messageApi, resourceType, t]);

  const handleLoadFunctionPresets = useCallback(async () => {
    try {
      setLoadFunctionPresetsLoading(true);
      const result = await loadFunctionCategoryPresets(resourceType);
      messageApi.success(
        t('pages.system.resourceCategory.loadFunctionPresetsSuccess', {
          categories: result.categories_created,
          items: result.items_categorized,
        }),
      );
      await reloadCategories();
      onFunctionPresetsApplied?.();
    } catch (error: unknown) {
      const err = error as { message?: string };
      messageApi.error(err?.message || t('pages.system.resourceCategory.loadFunctionPresetsFailed'));
    } finally {
      setLoadFunctionPresetsLoading(false);
    }
  }, [messageApi, onFunctionPresetsApplied, reloadCategories, resourceType, t]);

  useEffect(() => {
    void reloadCategories();
  }, [reloadCategories]);

  const handleCreateCategory = useCallback(() => {
    setFormIsEdit(false);
    setEditingCategory(null);
    setFormOpen(true);
  }, []);

  const handleEditCategory = useCallback((category: ResourceCategory) => {
    setFormIsEdit(true);
    setEditingCategory(category);
    setFormOpen(true);
  }, []);

  const handleDeleteCategory = useCallback(
    async (category: ResourceCategory) => {
      try {
        await deleteResourceCategory(resourceType, category.uuid);
        messageApi.success(t('pages.system.resourceCategory.deleteSuccess'));
        if (selectedCategoryKey === category.uuid) {
          const nextKey = RESOURCE_CATEGORY_ALL_KEY;
          setSelectedCategoryKey(nextKey);
          onSelectionChange?.(resolveApiCategoryTreeKey(nextKey));
        }
        await reloadCategories();
      } catch (error: unknown) {
        const err = error as { message?: string };
        messageApi.error(err?.message || t('common.deleteFailed'));
        throw error;
      }
    },
    [messageApi, onSelectionChange, reloadCategories, resourceType, selectedCategoryKey, t],
  );

  const confirmDeleteCategory = useCallback(
    (category: ResourceCategory) => {
      modalApi.confirm({
        title: t('pages.system.resourceCategory.deleteConfirm'),
        okText: t('common.confirm'),
        cancelText: t('common.cancel'),
        okType: 'danger',
        onOk: () => handleDeleteCategory(category),
      });
    },
    [handleDeleteCategory, modalApi, t],
  );

  const getCategoryContextMenu = useCallback(
    (category: ResourceCategory): MenuProps['items'] => [
      {
        key: 'edit',
        icon: <EditOutlined />,
        label: t('common.edit'),
        onClick: () => handleEditCategory(category),
      },
      {
        key: 'delete',
        icon: <DeleteOutlined />,
        label: t('common.delete'),
        danger: true,
        onClick: () => confirmDeleteCategory(category),
      },
    ],
    [confirmDeleteCategory, handleEditCategory, t],
  );

  const renderCategoryTitle = useCallback(
    (category: ResourceCategory) => (
      <span className="resource-category-tree-title">
        <span className="resource-category-tree-title-text">
          {withCount(category.name, category.item_count)}
        </span>
        <span
          className="resource-category-tree-title-actions"
          onClick={stopTreeNodeActionEvent}
          onMouseDown={stopTreeNodeActionEvent}
        >
          <Space size={0} align="center">
            <Tooltip title={t('common.edit')}>
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                aria-label={t('common.edit')}
                onClick={event => {
                  stopTreeNodeActionEvent(event);
                  handleEditCategory(category);
                }}
              />
            </Tooltip>
            <Tooltip title={t('common.delete')}>
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                aria-label={t('common.delete')}
                onClick={event => {
                  stopTreeNodeActionEvent(event);
                  confirmDeleteCategory(category);
                }}
              />
            </Tooltip>
          </Space>
        </span>
      </span>
    ),
    [confirmDeleteCategory, handleEditCategory, t],
  );

  const buildApiRelatedDocumentChildren = useCallback(
    (categoryKey: string, categoryUuid: string | null, categoryTotal: number): DataNode[] => {
      const rows = groupCountsForCategory(apiDocGroupCounts, categoryUuid);
      const byDoc = new Map<string, number>();
      for (const row of rows) {
        const doc = String(row.related_document_code || '').trim();
        byDoc.set(doc, (byDoc.get(doc) || 0) + row.count);
      }
      const children: DataNode[] = [
        {
          title: withCount(t('pages.system.resourceCategory.all'), categoryTotal),
          key: buildApiCategoryTreeDocKey(categoryKey, API_TREE_DOC_ALL),
          isLeaf: true,
        },
      ];
      for (const code of apiDocOptionCodes) {
        const count = byDoc.get(code);
        if (!count) continue;
        children.push({
          title: withCount(t(`pages.system.apis.relatedDocument.${code}`, code), count),
          key: buildApiCategoryTreeDocKey(categoryKey, code),
          isLeaf: true,
        });
      }
      const noneCount = byDoc.get('') || 0;
      if (noneCount > 0) {
        children.push({
          title: withCount(t('pages.system.apis.relatedDocumentNone'), noneCount),
          key: buildApiCategoryTreeDocKey(categoryKey, API_TREE_DOC_NONE),
          isLeaf: true,
        });
      }
      return children;
    },
    [apiDocGroupCounts, apiDocOptionCodes, t],
  );

  const treeData = useMemo((): DataNode[] => {
    const keyword = searchValue.trim().toLowerCase();
    const filteredCategories = categories.filter(category => {
      if (!keyword) return true;
      return (
        category.name.toLowerCase().includes(keyword) ||
        category.code.toLowerCase().includes(keyword)
      );
    });

    const allLabel = withCount(t('pages.system.resourceCategory.all'), totalCount);
    const uncategorizedLabel = withCount(
      t('pages.system.resourceCategory.uncategorized'),
      uncategorizedCount,
    );

    return [
      {
        title: allLabel,
        key: RESOURCE_CATEGORY_ALL_KEY,
        icon: <FolderOutlined />,
        children: [
          ...filteredCategories.map(category =>
            enableApiRelatedDocumentGroups
              ? {
                  title: renderCategoryTitle(category),
                  key: category.uuid,
                  icon: <FolderOutlined />,
                  isLeaf: false,
                  children: buildApiRelatedDocumentChildren(
                    category.uuid,
                    category.uuid,
                    category.item_count,
                  ),
                }
              : {
                  title: renderCategoryTitle(category),
                  key: category.uuid,
                  icon: <FolderOutlined />,
                  isLeaf: true,
                },
          ),
          enableApiRelatedDocumentGroups
            ? {
                title: uncategorizedLabel,
                key: RESOURCE_CATEGORY_UNCATEGORIZED_KEY,
                icon: <FolderOutlined />,
                isLeaf: false,
                children: buildApiRelatedDocumentChildren(
                  RESOURCE_CATEGORY_UNCATEGORIZED_KEY,
                  null,
                  uncategorizedCount,
                ),
              }
            : {
                title: uncategorizedLabel,
                key: RESOURCE_CATEGORY_UNCATEGORIZED_KEY,
                icon: <FolderOutlined />,
                isLeaf: true,
              },
        ],
      },
    ];
  }, [
    buildApiRelatedDocumentChildren,
    categories,
    enableApiRelatedDocumentGroups,
    renderCategoryTitle,
    searchValue,
    t,
    totalCount,
    uncategorizedCount,
  ]);

  const [contextMenuCategory, setContextMenuCategory] = useState<ResourceCategory | null>(null);
  const [contextMenuPos, setContextMenuPos] = useState<{ x: number; y: number } | null>(null);

  const handleTreeSelect = useCallback<TreeProps['onSelect']>(
    keys => {
      const key = keys[0];
      if (!key) return;
      const rawKey = String(key);
      // 仅接口库有「关联单据」二级树；审批/消息/打印/数据集必须保留纯 UUID，
      // 否则 list/create 会把 uuid::doc::__all__ 当成 category_uuid（第 37 位冒号校验失败）。
      const nextKey = enableApiRelatedDocumentGroups
        ? normalizeApiCategoryTreeSelectKey(rawKey)
        : rawKey;
      if (nextKey === selectedCategoryKey) return;
      setSelectedCategoryKey(nextKey);
      onSelectionChange?.(resolveApiCategoryTreeKey(nextKey));
    },
    [enableApiRelatedDocumentGroups, onSelectionChange, selectedCategoryKey],
  );

  // resolveApiCategoryTreeKey 对纯 UUID / all / uncategorized 与 resolveResourceCategoryListFilter 等价，
  // 且能拆掉误残留的 uuid::doc:: 复合键（HMR 后 state 未重置时仍可筛）。
  const listFilter = useMemo(
    () => resolveApiCategoryTreeKey(selectedCategoryKey),
    [selectedCategoryKey],
  );

  useEffect(() => {
    if (enableApiRelatedDocumentGroups) return;
    if (!selectedCategoryKey.includes(API_TREE_DOC_SEP)) return;
    const sanitized = selectedCategoryKey.split(API_TREE_DOC_SEP, 2)[0] || RESOURCE_CATEGORY_ALL_KEY;
    setSelectedCategoryKey(sanitized);
  }, [enableApiRelatedDocumentGroups, selectedCategoryKey]);

  useEffect(() => {
    if (!enableApiRelatedDocumentGroups) return;
    setExpandedKeys(prev => {
      const next = new Set<React.Key>([...prev, RESOURCE_CATEGORY_ALL_KEY]);
      for (const category of categories) {
        next.add(category.uuid);
      }
      next.add(RESOURCE_CATEGORY_UNCATEGORIZED_KEY);
      return Array.from(next);
    });
  }, [categories, enableApiRelatedDocumentGroups, apiDocGroupCounts]);

  const categorySelectOptions = useMemo(
    () =>
      categories.map(category => ({
        label: category.name,
        value: category.uuid,
      })),
    [categories],
  );

  const leftPanel: LeftPanelConfig = {
    widthStorageKey: twoColumnLeftPanelWidthStorageKey(`system.resource-category.${resourceType}`),
    search: {
      placeholder: t('pages.system.resourceCategory.searchPlaceholder'),
      value: searchValue,
      onChange: setSearchValue,
      allowClear: true,
    },
    actions: [
      <Button
        key="create-category"
        type="primary"
        icon={<PlusOutlined />}
        block
        onClick={handleCreateCategory}
      >
        {t('pages.system.resourceCategory.createButton')}
      </Button>,
      ...(showFunctionPresets
        ? [
            <Button
              key="load-function-presets"
              block
              loading={loadFunctionPresetsLoading}
              onClick={() => void handleLoadFunctionPresets()}
            >
              {t('pages.system.resourceCategory.loadFunctionPresetsButton')}
            </Button>,
          ]
        : []),
    ],
    tree: {
      treeData,
      selectedKeys: [selectedCategoryKey],
      expandedKeys,
      onExpand: keys => setExpandedKeys(keys),
      onSelect: handleTreeSelect,
      showIcon: true,
      blockNode: true,
      loading,
      loadingTip: t('pages.system.resourceCategory.loading'),
      // 与文件管理侧栏树共用展开箭头垂直居中样式（global.less）
      className: 'resource-category-tree',
      onRightClick: info => {
        const key = String(info.node.key);
        const category = categories.find(item => item.uuid === key);
        if (!category) return;
        info.event.preventDefault();
        setContextMenuCategory(category);
        setContextMenuPos({ x: info.event.clientX, y: info.event.clientY });
      },
    },
  };

  const categoryFormModal = (
    <>
      <ResourceCategoryFormModal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        resourceType={resourceType}
        isEdit={formIsEdit}
        category={editingCategory}
        onSuccess={() => {
          void reloadCategories();
          onSelectionChange?.(resolveApiCategoryTreeKey(selectedCategoryKey));
        }}
      />
      {contextMenuCategory && contextMenuPos ? (
        <Dropdown
          open
          trigger={['contextMenu']}
          menu={{ items: getCategoryContextMenu(contextMenuCategory) }}
          onOpenChange={open => {
            if (!open) {
              setContextMenuCategory(null);
              setContextMenuPos(null);
            }
          }}
        >
          <div
            style={{
              position: 'fixed',
              left: contextMenuPos.x,
              top: contextMenuPos.y,
              width: 1,
              height: 1,
            }}
          />
        </Dropdown>
      ) : null}
    </>
  );

  return {
    leftPanel,
    listFilter,
    selectedCategoryKey,
    categories,
    categorySelectOptions,
    reloadCategories,
    categoryFormModal,
  };
}
