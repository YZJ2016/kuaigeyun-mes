import { describe, expect, it } from 'vitest';
import {
  resolveToolbarSyncPushFlagsFromPerms,
  resolveToolbarSyncPushResource,
} from './useToolbarSyncPushFlags';

describe('resolveToolbarSyncPushResource', () => {
  it('maps legacy category names to resource prefixes', () => {
    expect(resolveToolbarSyncPushResource('work_order')).toBe('kuaizhizao:work-order');
    expect(resolveToolbarSyncPushResource('reporting')).toBe(
      'kuaizhizao:production-execution-reporting',
    );
    expect(resolveToolbarSyncPushResource('kuaizhizao:sales-order')).toBe(
      'kuaizhizao:sales-order',
    );
  });
});

describe('resolveToolbarSyncPushFlagsFromPerms', () => {
  it('defaults to hidden when no canAction', () => {
    expect(resolveToolbarSyncPushFlagsFromPerms(undefined)).toEqual({
      syncEnabled: false,
      pushEnabled: false,
      hubVisible: false,
    });
  });

  it('honors sync/push independently', () => {
    expect(
      resolveToolbarSyncPushFlagsFromPerms((a) => a === 'sync'),
    ).toEqual({
      syncEnabled: true,
      pushEnabled: false,
      hubVisible: true,
    });
    expect(
      resolveToolbarSyncPushFlagsFromPerms((a) => a === 'push'),
    ).toEqual({
      syncEnabled: false,
      pushEnabled: true,
      hubVisible: true,
    });
    expect(resolveToolbarSyncPushFlagsFromPerms(() => false)).toEqual({
      syncEnabled: false,
      pushEnabled: false,
      hubVisible: false,
    });
  });
});
