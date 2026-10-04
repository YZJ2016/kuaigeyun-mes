/**
 * 把报表挂到侧栏应用菜单。系统菜单不可选。
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Alert, App, Button, Form, Input, Modal, TreeSelect } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { MenuTree } from '../../../../services/menu';
import { getNavigationMenuTree } from '../../../../services/menu';
import { NAVIGATION_MENU_TREE_QUERY_KEY } from '../../../../hooks/useNavigationMenuTreeQuery';
import { clearReportMount, getReportMount, mountReport } from './api';

const SELF_MADE_NAMES = ['app.kuaireport.menu.selfMadeReports', '自制报表'];

type TreeNode = {
  title: string;
  value: string;
  key: string;
  disabled?: boolean;
  children?: TreeNode[];
};

function menuLabel(name: string, t: (key: string) => string): string {
  if (!name.includes('.')) return name;
  const translated = t(name);
  return translated && translated !== name ? translated : name;
}

function toTree(nodes: MenuTree[], t: (key: string) => string): TreeNode[] {
  return nodes.map((node) => ({
    title: menuLabel(node.name, t),
    value: node.uuid,
    key: node.uuid,
    disabled: !(node.application_uuid || '').trim(),
    children: node.children?.length ? toTree(node.children, t) : undefined,
  }));
}

function findMenu(nodes: MenuTree[], names: string[]): MenuTree | undefined {
  for (const node of nodes) {
    if (names.includes(node.name)) return node;
    const child = node.children?.length ? findMenu(node.children, names) : undefined;
    if (child) return child;
  }
  return undefined;
}

type Mountable = { id: number; name: string };

export function MountReportModal({
  report,
  onClose,
  defaultParentNames = SELF_MADE_NAMES,
  description,
  loadMount = getReportMount,
  saveMount = mountReport,
  removeMount = clearReportMount,
}: {
  report: Mountable | null;
  onClose: (changed: boolean) => void;
  defaultParentNames?: string[];
  description?: React.ReactNode;
  loadMount?: typeof getReportMount;
  saveMount?: typeof mountReport;
  removeMount?: typeof clearReportMount;
}) {
  const { message } = App.useApp();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<{ parent_uuid: string; menu_name: string }>();
  const [tree, setTree] = useState<MenuTree[]>([]);
  const [mounted, setMounted] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!report) return;
    let cancelled = false;
    form.setFieldsValue({ menu_name: report.name, parent_uuid: undefined });
    setMounted(false);
    void (async () => {
      try {
        const [menus, state] = await Promise.all([
          getNavigationMenuTree({ fresh: true }),
          loadMount(report.id),
        ]);
        if (cancelled) return;
        setTree(Array.isArray(menus) ? menus : []);
        setMounted(Boolean(state.mounted));
        const fallback = findMenu(menus || [], defaultParentNames);
        form.setFieldsValue({
          menu_name: state.menu_name || report.name,
          parent_uuid: state.parent_uuid || fallback?.uuid,
        });
      } catch (err) {
        if (!cancelled) {
          message.error(err instanceof Error ? err.message : '菜单加载失败');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [defaultParentNames, form, loadMount, message, report]);

  const treeData = useMemo(() => toTree(tree, t), [t, tree]);

  const refreshSidebar = () => {
    void queryClient.invalidateQueries({ queryKey: [NAVIGATION_MENU_TREE_QUERY_KEY] });
  };

  const onMount = async () => {
    if (!report) return;
    const values = await form.validateFields();
    setSaving(true);
    try {
      await saveMount(report.id, {
        parent_uuid: values.parent_uuid,
        menu_name: values.menu_name.trim(),
      });
      message.success('已挂载到菜单');
      refreshSidebar();
      onClose(true);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '挂载失败');
    } finally {
      setSaving(false);
    }
  };

  const onClear = async () => {
    if (!report) return;
    setSaving(true);
    try {
      await removeMount(report.id);
      message.success('已清除挂载');
      refreshSidebar();
      onClose(true);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '清除挂载失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="挂载到菜单"
      open={report != null}
      onCancel={() => onClose(false)}
      destroyOnHidden
      width={640}
      footer={[
        <Button key="clear" danger disabled={!mounted} loading={saving} onClick={() => void onClear()}>
          清除挂载
        </Button>,
        <Button key="cancel" onClick={() => onClose(false)}>
          取消
        </Button>,
        <Button key="ok" type="primary" loading={saving} onClick={() => void onMount()}>
          确定挂载
        </Button>,
      ]}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          description ?? (
            <span>
              将报表加入左侧菜单，可选快报表或其他应用下的分组。
              <br />
              将出现在「自制报表」下。入口仍打开本报表页面，需具备对应查看权限。
            </span>
          )
        }
      />
      <Form form={form} layout="vertical">
        <Form.Item
          name="parent_uuid"
          label="挂载位置（父级菜单）"
          extra="支持挂到其他 APP 菜单下；系统菜单不可选。默认仍建议挂在快报表分组内。"
          rules={[{ required: true, message: '请选择挂载位置' }]}
        >
          <TreeSelect
            treeData={treeData}
            treeDefaultExpandAll
            showSearch
            treeNodeFilterProp="title"
            placeholder="请选择"
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item name="menu_name" label="菜单名称" rules={[{ required: true, message: '请填写菜单名称' }]}>
          <Input allowClear maxLength={100} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
