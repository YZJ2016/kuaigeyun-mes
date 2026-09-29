import { describe, expect, it } from 'vitest';
import {
  resolveToolbarSyncPushFlags,
  type ToolbarSyncPushCategory,
} from './useToolbarSyncPushFlags';
import type { BusinessConfig } from '../services/businessConfig';

const categories: ToolbarSyncPushCategory[] = [
  'work_order',
  'reporting',
  'sales',
  'purchase',
  'warehouse',
];

describe('resolveToolbarSyncPushFlags', () => {
  it('defaults to both enabled when config missing', () => {
    for (const category of categories) {
      const flags = resolveToolbarSyncPushFlags(null, category);
      expect(flags.syncEnabled).toBe(true);
      expect(flags.pushEnabled).toBe(true);
      expect(flags.hubVisible).toBe(true);
    }
  });

  it('honors false flags and hubVisible OR logic', () => {
    const config = {
      parameters: {
        work_order: {
          toolbar_sync_enabled: false,
          toolbar_push_enabled: true,
        },
        reporting: {
          toolbar_sync_enabled: false,
          toolbar_push_enabled: false,
        },
      },
    } as BusinessConfig;

    expect(resolveToolbarSyncPushFlags(config, 'work_order')).toEqual({
      syncEnabled: false,
      pushEnabled: true,
      hubVisible: true,
    });
    expect(resolveToolbarSyncPushFlags(config, 'reporting')).toEqual({
      syncEnabled: false,
      pushEnabled: false,
      hubVisible: false,
    });
  });

  it('parses string false/0/off as disabled', () => {
    const config = {
      parameters: {
        sales: {
          toolbar_sync_enabled: 'false',
          toolbar_push_enabled: '0',
        },
      },
    } as BusinessConfig;
    const flags = resolveToolbarSyncPushFlags(config, 'sales');
    expect(flags.syncEnabled).toBe(false);
    expect(flags.pushEnabled).toBe(false);
    expect(flags.hubVisible).toBe(false);
  });
});
