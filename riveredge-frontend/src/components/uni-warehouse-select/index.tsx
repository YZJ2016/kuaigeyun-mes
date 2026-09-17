import React, { useMemo, useState, useEffect } from 'react';
import { App } from 'antd';
import { ProFormSelect } from '@ant-design/pro-components';
import { useDebounceFn } from 'ahooks';
import { Warehouse } from '../../apps/master-data/types/warehouse';
import { NamePath } from 'antd/es/form/interface';
import {
  ReferenceDisplayAccessError,
  searchReferenceDisplay,
  type ReferenceDisplayItem,
} from '../../utils/referenceDisplay';

const WAREHOUSE_REFERENCE_RESOURCE = 'master-data:warehouse:warehouse';

function mapWarehouseDisplayItem(item: ReferenceDisplayItem): Warehouse {
  return {
    id: Number(item.id),
    uuid: String(item.uuid ?? ''),
    code: String(item.code ?? ''),
    name: String(item.name ?? ''),
  } as Warehouse;
}

interface UniWarehouseSelectProps {
  /** 表单字段名称 */
  name: NamePath;
  /** 标签 */
  label?: string;
  /** 占位符 */
  placeholder?: string;
  /** 是否必填 */
  required?: boolean;
  /** 禁用状态 */
  disabled?: boolean;
  /** 是否只读模式 */
  readonly?: boolean;
  /** 只展示启用的仓库，默认为 true */
  activeOnly?: boolean;
  /** 宿主 {app}:{module}，供引用展示隐式鉴权；未传时按当前路由菜单自动推断 */
  hostResource?: string;
  /** 自定义宽度 */
  width?: number | 'sm' | 'md' | 'xl' | 'xs' | 'lg';
  /** 值改变时的回调，额外返回完整的 warehouse 对象 */
  onChange?: (value: number | undefined, warehouse: Warehouse | undefined) => void;
  /** 初始绑定的表单实例等 */
  [key: string]: any;
}

/**
 * 统一仓库选择组件
 *
 * @description
 * 内置防抖搜索与列表数据的自动拉取。
 * 走 reference display + 宿主隐式授权，避免业务单据页因缺少主数据仓库 read 而 403。
 */
export const UniWarehouseSelect: React.FC<UniWarehouseSelectProps> = ({
  name,
  label = '仓库',
  placeholder = '请选择或搜索仓库',
  required = false,
  disabled = false,
  readonly = false,
  activeOnly = true,
  hostResource,
  width,
  onChange,
  ...restProps
}) => {
  const { message } = App.useApp();
  const [data, setData] = useState<Warehouse[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchWarehouses = async (searchText: string = '') => {
    setLoading(true);
    try {
      const response = await searchReferenceDisplay({
        resource: WAREHOUSE_REFERENCE_RESOURCE,
        hostResource,
        keyword: searchText.trim() || undefined,
        isActive: activeOnly ? true : undefined,
        pageSize: 200,
      });
      setData((response.items || []).map(mapWarehouseDisplayItem));
    } catch (error) {
      console.error('Failed to fetch warehouses:', error);
      if (error instanceof ReferenceDisplayAccessError) {
        message.error(error.message);
      } else {
        message.error('加载仓库列表失败，请稍后重试');
      }
    } finally {
      setLoading(false);
    }
  };

  const { run: debounceFetch } = useDebounceFn(
    (value: string) => fetchWarehouses(value),
    { wait: 300 }
  );

  useEffect(() => {
    // 初始加载一次默认数据
    fetchWarehouses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hostResource, activeOnly]);

  const handleChange = (val: number, _option: any) => {
    if (onChange) {
      const selected = data.find(
        (w) => Number(w.id) === Number(val) || w.uuid === val?.toString(),
      );
      onChange(val, selected);
    }
  };

  const options = useMemo(() => {
    return data.map((item) => ({
      label: `${item.code} ${item.name}`.trim() || String(item.id),
      value: item.id || item.uuid,
      key: item.id || item.uuid,
    }));
  }, [data]);

  return (
    <ProFormSelect
      name={name}
      label={label}
      placeholder={placeholder}
      readonly={readonly}
      disabled={disabled}
      width={width}
      rules={required ? [{ required: true, message: `请选择${label}` }] : undefined}
      options={options}
      fieldProps={{
        showSearch: true,
        loading,
        filterOption: false, // 禁用默认前端过滤，交由防抖后的后端按 keyword 搜索
        onSearch: debounceFetch,
        onChange: handleChange,
      }}
      {...restProps}
    />
  );
};

export default UniWarehouseSelect;
