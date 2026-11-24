import { describe, expect, it } from 'vitest';
import { flattenMenuHomePathOptions, isVirtualMenuGroupHomePath } from './menuHomePathOptions';
import type { MenuTree } from '../services/menu';

function node(partial: Partial<MenuTree> & Pick<MenuTree, 'name'>): MenuTree {
  return {
    uuid: 'u',
    tenant_id: 1,
    sort_order: 0,
    is_active: true,
    is_external: false,
    created_at: '',
    updated_at: '',
    children: [],
    ...partial,
  };
}

describe('isVirtualMenuGroupHomePath', () => {
  it('excludes menu-entry-shell app roots', () => {
    expect(isVirtualMenuGroupHomePath('/apps/kuaiems')).toBe(true);
    expect(isVirtualMenuGroupHomePath('/apps/kuaiqms/')).toBe(true);
    expect(isVirtualMenuGroupHomePath('/apps/kuaizhizao/equipment-management/spot-checks')).toBe(false);
  });

  it('excludes custom layout virtual nodes', () => {
    expect(
      isVirtualMenuGroupHomePath('/apps/kuaizhizao/dashboard', {
        meta: { custom_layout_virtual: true },
      }),
    ).toBe(true);
  });
});

describe('flattenMenuHomePathOptions', () => {
  it('omits virtual app roots but keeps business leaves', () => {
    const tree: MenuTree[] = [
      node({
        name: '快设备',
        path: '/apps/kuaiems',
        children: [
          node({
            name: '设备点检',
            path: '/apps/kuaizhizao/equipment-management/spot-checks',
          }),
        ],
      }),
    ];
    const options = flattenMenuHomePathOptions(tree);
    const values = options.map((o) => o.value);
    expect(values).not.toContain('/apps/kuaiems');
    expect(values).toContain('/apps/kuaizhizao/equipment-management/spot-checks');
  });
});