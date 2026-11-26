/**
 * 产品工艺 — 按物料或物料分组指派工艺路线并维护序列、资源、工价
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Alert, App, Empty, Spin, Tag, Typography } from 'antd';
import { ListPageTemplate, TwoColumnLayout } from '../../../../../components/layout-templates';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import { materialApi, materialGroupApi } from '../../../services/material';
import { processRouteApi } from '../../../services/process';
import { productProcessApi } from '../../../services/productProcess';
import type { Material, MaterialGroup } from '../../../types/material';
import { formatMaterialGroupLabel } from '../../../types/material';
import type { ProcessRoute } from '../../../types/process';
import { ProductProcessPanel } from '../../../components/ProductProcessPanel';
import {
  effectiveProcessRouteLabel,
  materialHasEffectiveProcessRoute,
  resolveEffectiveProcessRouteUuid,
  type ProductProcessRouteByMaterialUuid,
} from '../../../utils/productProcessMaterialUtils';

type AssignFilter = 'all' | 'assigned' | 'unassigned';
type ListScope = 'material' | 'group';

type ProductProcessRouteByGroupUuid = Record<string, string>;

const API_LIST_LIMIT = 1000;

function effectiveGroupRouteLabel(
  group: MaterialGroup,
  processRoutes: ProcessRoute[],
  notSetText: string,
  productProcessGroupRouteByUuid: ProductProcessRouteByGroupUuid,
): string {
  const fromProductProcess = productProcessGroupRouteByUuid[group.uuid];
  if (fromProductProcess) {
    const pr = processRoutes.find((r) => r.uuid === fromProductProcess);
    if (pr) return `${pr.code} - ${pr.name}`;
  }
  const prId = group.processRouteId ?? group.process_route_id;
  if (prId != null) {
    const pr = processRoutes.find((r) => r.id === prId);
    if (pr) return `${pr.code} - ${pr.name}`;
  }
  return notSetText;
}

function groupHasEffectiveProcessRoute(
  group: MaterialGroup,
  processRoutes: ProcessRoute[],
  productProcessGroupRouteByUuid: ProductProcessRouteByGroupUuid,
): boolean {
  if (productProcessGroupRouteByUuid[group.uuid]) {
    return true;
  }
  const prId = group.processRouteId ?? group.process_route_id;
  return prId != null && processRoutes.some((r) => r.id === prId);
}

const ProductProcessPage: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { message: messageApi } = App.useApp();

  const materialUuidFromUrl = searchParams.get('materialUuid') ?? undefined;
  const groupUuidFromUrl = searchParams.get('groupUuid') ?? undefined;
  const routeUuidFromUrl = searchParams.get('routeUuid') ?? undefined;

  const initialScope: ListScope = groupUuidFromUrl ? 'group' : 'material';

  const [keyword, setKeyword] = useState('');
  const [listScope, setListScope] = useState<ListScope>(initialScope);
  const [assignFilter, setAssignFilter] = useState<AssignFilter>('all');
  const [materials, setMaterials] = useState<Material[]>([]);
  const [materialsTotal, setMaterialsTotal] = useState(0);
  const [materialsLoading, setMaterialsLoading] = useState(false);
  const [selectedMaterial, setSelectedMaterial] = useState<Material | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);

  const [materialGroups, setMaterialGroups] = useState<MaterialGroup[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<MaterialGroup | null>(null);
  const [groupDetailLoading, setGroupDetailLoading] = useState(false);

  const [processRoutes, setProcessRoutes] = useState<ProcessRoute[]>([]);
  const [processRoutesLoading, setProcessRoutesLoading] = useState(false);
  const [productProcessRouteByMaterialUuid, setProductProcessRouteByMaterialUuid] =
    useState<ProductProcessRouteByMaterialUuid>({});
  const [productProcessGroupRouteByUuid, setProductProcessGroupRouteByUuid] =
    useState<ProductProcessRouteByGroupUuid>({});

  const filterRoute = useMemo(
    () => (routeUuidFromUrl ? processRoutes.find((r) => r.uuid === routeUuidFromUrl) : undefined),
    [routeUuidFromUrl, processRoutes],
  );

  const notSetText = t('app.master-data.source.processRouteNotSet');

  const loadProcessRoutes = useCallback(async () => {
    setProcessRoutesLoading(true);
    try {
      const result = await processRouteApi.list({ limit: API_LIST_LIMIT, isActive: true });
      const list = Array.isArray(result) ? result : result?.data ?? [];
      setProcessRoutes(list);
    } catch (e: unknown) {
      messageApi.error((e as Error).message || t('app.master-data.materialForm.fetchProcessRoutesFailed'));
      setProcessRoutes([]);
    } finally {
      setProcessRoutesLoading(false);
    }
  }, [messageApi, t]);

  const loadProductProcessRouteAssignments = useCallback(async () => {
    try {
      const items = await productProcessApi.listRouteAssignments();
      const next: ProductProcessRouteByMaterialUuid = {};
      items.forEach((item) => {
        const materialUuid = item.materialUuid ?? (item as { material_uuid?: string }).material_uuid;
        const routeUuid =
          item.processRouteUuid ?? (item as { process_route_uuid?: string }).process_route_uuid;
        if (materialUuid && routeUuid) {
          next[materialUuid] = routeUuid;
        }
      });
      setProductProcessRouteByMaterialUuid(next);
    } catch (e: unknown) {
      messageApi.error((e as Error).message || t('common.loadFailed'));
      setProductProcessRouteByMaterialUuid({});
    }
  }, [messageApi, t]);

  const loadProductProcessGroupRouteAssignments = useCallback(async () => {
    try {
      const items = await productProcessApi.listGroupRouteAssignments();
      const next: ProductProcessRouteByGroupUuid = {};
      items.forEach((item) => {
        const groupUuid =
          item.materialGroupUuid ?? (item as { material_group_uuid?: string }).material_group_uuid;
        const routeUuid =
          item.processRouteUuid ?? (item as { process_route_uuid?: string }).process_route_uuid;
        if (groupUuid && routeUuid) {
          next[groupUuid] = routeUuid;
        }
      });
      setProductProcessGroupRouteByUuid(next);
    } catch (e: unknown) {
      messageApi.error((e as Error).message || t('common.loadFailed'));
      setProductProcessGroupRouteByUuid({});
    }
  }, [messageApi, t]);

  const loadMaterials = useCallback(
    async (searchKeyword = '') => {
      setMaterialsLoading(true);
      try {
        const kw = searchKeyword.trim();
        const { items, total } = await materialApi.list({
          skip: 0,
          limit: API_LIST_LIMIT,
          sourceType: 'Make',
          mastersOnly: true,
          isActive: true,
          ...(kw ? { keyword: kw } : {}),
        });
        setMaterials(items ?? []);
        setMaterialsTotal(typeof total === 'number' ? total : items?.length ?? 0);
      } catch (e: unknown) {
        messageApi.error((e as Error).message || t('common.loadFailed'));
        setMaterials([]);
        setMaterialsTotal(0);
      } finally {
        setMaterialsLoading(false);
      }
    },
    [messageApi, t],
  );

  const loadMaterialGroups = useCallback(
    async (searchKeyword = '') => {
      setGroupsLoading(true);
      try {
        const kw = searchKeyword.trim().toLowerCase();
        const list = await materialGroupApi.list({ limit: API_LIST_LIMIT, isActive: true });
        const filtered = kw
          ? list.filter((g) =>
              `${g.code ?? ''} ${g.name ?? ''} ${g.alias ?? ''}`.toLowerCase().includes(kw),
            )
          : list;
        setMaterialGroups(filtered);
      } catch (e: unknown) {
        messageApi.error((e as Error).message || t('common.loadFailed'));
        setMaterialGroups([]);
      } finally {
        setGroupsLoading(false);
      }
    },
    [messageApi, t],
  );

  useEffect(() => {
    void loadProcessRoutes();
    void loadProductProcessRouteAssignments();
    void loadProductProcessGroupRouteAssignments();
  }, [loadProcessRoutes, loadProductProcessRouteAssignments, loadProductProcessGroupRouteAssignments]);

  useEffect(() => {
    if (listScope === 'material') {
      void loadMaterials();
    } else {
      void loadMaterialGroups();
    }
  }, [listScope, loadMaterials, loadMaterialGroups]);

  const selectMaterial = useCallback(
    async (record: Material) => {
      setSelectedLoading(true);
      try {
        const detail = await materialApi.get(record.uuid);
        setSelectedMaterial(detail);
        setSelectedGroup(null);
        const next = new URLSearchParams(searchParams);
        next.set('materialUuid', record.uuid);
        next.delete('groupUuid');
        setSearchParams(next, { replace: true });
      } catch (e: unknown) {
        messageApi.error((e as Error).message || t('common.loadFailed'));
      } finally {
        setSelectedLoading(false);
      }
    },
    [messageApi, searchParams, setSearchParams, t],
  );

  const selectGroup = useCallback(
    async (record: MaterialGroup) => {
      setGroupDetailLoading(true);
      try {
        const detail = await materialGroupApi.get(record.uuid);
        setSelectedGroup(detail);
        setSelectedMaterial(null);
        const next = new URLSearchParams(searchParams);
        next.set('groupUuid', record.uuid);
        next.delete('materialUuid');
        setSearchParams(next, { replace: true });
      } catch (e: unknown) {
        messageApi.error((e as Error).message || t('common.loadFailed'));
      } finally {
        setGroupDetailLoading(false);
      }
    },
    [messageApi, searchParams, setSearchParams, t],
  );

  useEffect(() => {
    if (listScope !== 'material' || !materialUuidFromUrl || materialsLoading) return;
    const inList = materials.find((m) => m.uuid === materialUuidFromUrl);
    if (inList && selectedMaterial?.uuid !== materialUuidFromUrl) {
      void selectMaterial(inList);
    } else if (!inList && materialUuidFromUrl && !selectedLoading) {
      setSelectedLoading(true);
      materialApi
        .get(materialUuidFromUrl)
        .then((detail) => {
          if (detail.sourceType === 'Make' || (detail as { source_type?: string }).source_type === 'Make') {
            setSelectedMaterial(detail);
          }
        })
        .catch((e: Error) => messageApi.error(e.message || t('common.loadFailed')))
        .finally(() => setSelectedLoading(false));
    }
  }, [
    listScope,
    materialUuidFromUrl,
    materials,
    materialsLoading,
    selectMaterial,
    selectedMaterial?.uuid,
    selectedLoading,
    messageApi,
    t,
  ]);

  useEffect(() => {
    if (listScope !== 'group' || !groupUuidFromUrl || groupsLoading) return;
    const inList = materialGroups.find((g) => g.uuid === groupUuidFromUrl);
    if (inList && selectedGroup?.uuid !== groupUuidFromUrl) {
      void selectGroup(inList);
    } else if (!inList && groupUuidFromUrl && !groupDetailLoading) {
      setGroupDetailLoading(true);
      materialGroupApi
        .get(groupUuidFromUrl)
        .then((detail) => setSelectedGroup(detail))
        .catch((e: Error) => messageApi.error(e.message || t('common.loadFailed')))
        .finally(() => setGroupDetailLoading(false));
    }
  }, [
    groupDetailLoading,
    groupUuidFromUrl,
    groupsLoading,
    listScope,
    materialGroups,
    messageApi,
    selectGroup,
    selectedGroup?.uuid,
    t,
  ]);

  const displayedMaterials = useMemo(() => {
    let rows = materials;
    if (filterRoute) {
      rows = rows.filter(
        (m) =>
          resolveEffectiveProcessRouteUuid(m, processRoutes, productProcessRouteByMaterialUuid)
          === filterRoute.uuid,
      );
    }
    if (assignFilter === 'assigned') {
      rows = rows.filter((m) =>
        materialHasEffectiveProcessRoute(m, processRoutes, productProcessRouteByMaterialUuid),
      );
    } else if (assignFilter === 'unassigned') {
      rows = rows.filter(
        (m) => !materialHasEffectiveProcessRoute(m, processRoutes, productProcessRouteByMaterialUuid),
      );
    }
    return rows;
  }, [materials, assignFilter, filterRoute, processRoutes, productProcessRouteByMaterialUuid]);

  const displayedGroups = useMemo(() => {
    let rows = materialGroups;
    if (filterRoute) {
      rows = rows.filter(
        (g) =>
          (productProcessGroupRouteByUuid[g.uuid] ?? '') === filterRoute.uuid
          || processRoutes.find((r) => r.id === (g.processRouteId ?? g.process_route_id))?.uuid
            === filterRoute.uuid,
      );
    }
    if (assignFilter === 'assigned') {
      rows = rows.filter((g) =>
        groupHasEffectiveProcessRoute(g, processRoutes, productProcessGroupRouteByUuid),
      );
    } else if (assignFilter === 'unassigned') {
      rows = rows.filter(
        (g) => !groupHasEffectiveProcessRoute(g, processRoutes, productProcessGroupRouteByUuid),
      );
    }
    return rows;
  }, [assignFilter, filterRoute, materialGroups, processRoutes, productProcessGroupRouteByUuid]);

  const handleScopeChange = (value: string | number) => {
    const nextScope = value as ListScope;
    setListScope(nextScope);
    setKeyword('');
    setAssignFilter('all');
    if (nextScope === 'material') {
      setSelectedGroup(null);
      const next = new URLSearchParams(searchParams);
      next.delete('groupUuid');
      setSearchParams(next, { replace: true });
    } else {
      setSelectedMaterial(null);
      const next = new URLSearchParams(searchParams);
      next.delete('materialUuid');
      setSearchParams(next, { replace: true });
    }
  };

  const clearRouteFilter = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('routeUuid');
    setSearchParams(next, { replace: true });
  };

  const leftMaterialList = (
    <div className="product-process-material-list">
      {materialsLoading ? (
        <div className="product-process-material-list__loading">
          <Spin />
        </div>
      ) : displayedMaterials.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.master-data.productProcess.noMaterials')} />
      ) : (
        displayedMaterials.map((m) => {
          const hasRoute = materialHasEffectiveProcessRoute(
            m,
            processRoutes,
            productProcessRouteByMaterialUuid,
          );
          const routeLabel = effectiveProcessRouteLabel(
            m,
            processRoutes,
            notSetText,
            productProcessRouteByMaterialUuid,
          );
          const active = selectedMaterial?.uuid === m.uuid;
          return (
            <button
              key={m.uuid}
              type="button"
              className={`product-process-material-list__item${active ? ' product-process-material-list__item--active' : ''}`}
              onClick={() => void selectMaterial(m)}
            >
              <div className="product-process-material-list__row">
                <span className="product-process-material-list__code">{m.code}</span>
                <Tag
                  variant="filled"
                  color={hasRoute ? 'processing' : 'default'}
                  className="product-process-material-list__tag"
                >
                  {routeLabel}
                </Tag>
              </div>
              <div className="product-process-material-list__name" title={m.name}>
                {m.name}
              </div>
            </button>
          );
        })
      )}
    </div>
  );

  const leftGroupList = (
    <div className="product-process-material-list">
      {groupsLoading ? (
        <div className="product-process-material-list__loading">
          <Spin />
        </div>
      ) : displayedGroups.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.master-data.productProcess.noGroups')} />
      ) : (
        displayedGroups.map((g) => {
          const hasRoute = groupHasEffectiveProcessRoute(g, processRoutes, productProcessGroupRouteByUuid);
          const routeLabel = effectiveGroupRouteLabel(
            g,
            processRoutes,
            notSetText,
            productProcessGroupRouteByUuid,
          );
          const active = selectedGroup?.uuid === g.uuid;
          return (
            <button
              key={g.uuid}
              type="button"
              className={`product-process-material-list__item${active ? ' product-process-material-list__item--active' : ''}`}
              onClick={() => void selectGroup(g)}
            >
              <div className="product-process-material-list__row">
                <span className="product-process-material-list__code">{g.code}</span>
                <Tag
                  variant="filled"
                  color={hasRoute ? 'processing' : 'default'}
                  className="product-process-material-list__tag"
                >
                  {routeLabel}
                </Tag>
              </div>
              <div className="product-process-material-list__name" title={g.name}>
                {formatMaterialGroupLabel(g)}
              </div>
            </button>
          );
        })
      )}
    </div>
  );

  const rightLoading = listScope === 'material' ? selectedLoading : groupDetailLoading;
  const listCount = listScope === 'material' ? displayedMaterials.length : displayedGroups.length;
  const listTotal = listScope === 'material' ? materialsTotal : materialGroups.length;

  return (
    <ListPageTemplate fillMain>
      {filterRoute ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 8, flexShrink: 0 }}
          title={t('app.master-data.productProcess.filteredByRoute', {
            code: filterRoute.code,
            name: filterRoute.name,
          })}
          action={
            <Typography.Link onClick={clearRouteFilter}>
              {t('app.master-data.productProcess.clearRouteFilter')}
            </Typography.Link>
          }
        />
      ) : null}

      <TwoColumnLayout
        style={{ flex: 1, minHeight: 0 }}
        layoutPersistenceId="apps.master-data.pages.process.product-process"
        leftPanel={{
          search: {
            placeholder:
              listScope === 'material'
                ? t('app.master-data.productProcess.searchMaterial')
                : t('app.master-data.productProcess.searchGroup'),
            value: keyword,
            onChange: setKeyword,
            onSearch: (v) => {
              const q = v.trim();
              if (listScope === 'material') {
                void loadMaterials(q);
              } else {
                void loadMaterialGroups(q);
              }
            },
            allowClear: true,
          },
          actions: [
            <ThemedSegmented
              key="scope"
              block
              surfaceBackground
              size="medium"
              value={listScope}
              onChange={handleScopeChange}
              options={[
                { label: t('app.master-data.productProcess.scopeMaterial'), value: 'material' },
                { label: t('app.master-data.productProcess.scopeGroup'), value: 'group' },
              ]}
            />,
            <ThemedSegmented
              key="assign-filter"
              block
              surfaceBackground
              size="medium"
              value={assignFilter}
              onChange={(value) => setAssignFilter(value as AssignFilter)}
              options={[
                { label: t('app.master-data.productProcess.filterAll'), value: 'all' },
                { label: t('app.master-data.productProcess.filterAssigned'), value: 'assigned' },
                { label: t('app.master-data.productProcess.filterUnassigned'), value: 'unassigned' },
              ]}
            />,
            listScope === 'material' && materialsTotal > API_LIST_LIMIT ? (
              <Typography.Text key="trunc-hint" type="warning" style={{ fontSize: 12, display: 'block' }}>
                {t('app.master-data.productProcess.listTruncated', {
                  total: materialsTotal,
                  limit: API_LIST_LIMIT,
                })}
              </Typography.Text>
            ) : null,
          ].filter(Boolean),
          leftContent: listScope === 'material' ? leftMaterialList : leftGroupList,
        }}
        rightPanel={{
          contentPadding: 12,
          content: (
            <Spin spinning={rightLoading}>
              {listScope === 'material' && selectedMaterial ? (
                <ProductProcessPanel
                  scope="material"
                  material={selectedMaterial}
                  processRoutes={processRoutes}
                  processRoutesLoading={processRoutesLoading}
                  hideMaterialHeading
                  hidePanelHint
                  onMaterialUpdated={(m) => {
                    setSelectedMaterial(m);
                    setMaterials((prev) => prev.map((row) => (row.uuid === m.uuid ? { ...row, ...m } : row)));
                  }}
                  onProductProcessRouteSaved={(materialUuid, processRouteUuid) => {
                    setProductProcessRouteByMaterialUuid((prev) => {
                      const next = { ...prev };
                      if (processRouteUuid) {
                        next[materialUuid] = processRouteUuid;
                      } else {
                        delete next[materialUuid];
                      }
                      return next;
                    });
                  }}
                  onProcessRoutesRefresh={loadProcessRoutes}
                />
              ) : listScope === 'group' && selectedGroup ? (
                <ProductProcessPanel
                  scope="group"
                  materialGroup={selectedGroup}
                  processRoutes={processRoutes}
                  processRoutesLoading={processRoutesLoading}
                  hideMaterialHeading
                  hidePanelHint
                  onMaterialGroupUpdated={(g) => {
                    setSelectedGroup(g);
                    setMaterialGroups((prev) => prev.map((row) => (row.uuid === g.uuid ? { ...row, ...g } : row)));
                  }}
                  onProductProcessGroupRouteSaved={(groupUuid, processRouteUuid) => {
                    setProductProcessGroupRouteByUuid((prev) => {
                      const next = { ...prev };
                      if (processRouteUuid) {
                        next[groupUuid] = processRouteUuid;
                      } else {
                        delete next[groupUuid];
                      }
                      return next;
                    });
                  }}
                  onProcessRoutesRefresh={loadProcessRoutes}
                />
              ) : (
                <Empty
                  style={{ marginTop: 80 }}
                  description={
                    listScope === 'material'
                      ? t('app.master-data.productProcess.selectMaterialHint')
                      : t('app.master-data.productProcess.selectGroupHint')
                  }
                />
              )}
            </Spin>
          ),
          footer: (
            <span>
              {listCount}
              {listScope === 'material' && listTotal > listCount ? ` / ${listTotal}` : ''}
            </span>
          ),
        }}
      />
    </ListPageTemplate>
  );
};

export default ProductProcessPage;