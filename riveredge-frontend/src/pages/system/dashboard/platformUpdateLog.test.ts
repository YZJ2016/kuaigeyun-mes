import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import type { Application } from '../../../services/application';
import type { PlatformUpdateLogEntry } from './platformUpdateLog';
import {
  collectDedicatedAppCodesFromEntries,
  filterPlatformUpdates,
  filterVisiblePlatformUpdates,
  getAvailableUpdateLogTabs,
  isDedicatedPlatformUpdateEntry,
  mergePlatformUpdateLogs,
  resolveEnabledDedicatedAppCodes,
} from './platformUpdateLog';

function app(partial: Partial<Application> & Pick<Application, 'code'>): Application {
  return {
    uuid: 'u1',
    tenant_id: 1,
    name: partial.code,
    code: partial.code,
    is_system: false,
    is_active: partial.is_active ?? true,
    is_installed: partial.is_installed ?? true,
    is_custom_name: false,
    is_custom_sort: false,
    sort_order: 0,
    created_at: '',
    updated_at: '',
    is_dedicated: partial.is_dedicated,
  };
}

const generalEntry: PlatformUpdateLogEntry = {
  id: 'general-r01',
  date: '2026-09-24',
  type: 'fix',
  titleKey: 'pages.dashboard.updateLog.entries.general-r01.title',
};

const funideEntry: PlatformUpdateLogEntry = {
  id: 'funide-r01',
  date: '2026-09-24',
  type: 'improvement',
  titleKey: 'pages.dashboard.updateLog.entries.funide-r01.title',
  scope: 'dedicated',
  dedicatedAppCode: 'funide-oa',
};

const otherDedicatedEntry: PlatformUpdateLogEntry = {
  id: 'other-dedicated-r01',
  date: '2026-09-24',
  type: 'feature',
  titleKey: 'pages.dashboard.updateLog.entries.other-dedicated-r01.title',
  scope: 'dedicated',
  dedicatedAppCode: 'other-dedicated-app',
};

describe('isDedicatedPlatformUpdateEntry', () => {
  it('treats scope or dedicatedAppCode as dedicated record', () => {
    assert.strictEqual(isDedicatedPlatformUpdateEntry(funideEntry), true);
    assert.strictEqual(isDedicatedPlatformUpdateEntry({
        ...generalEntry,
        dedicatedAppCode: 'funide-oa',
      }), true);
    assert.strictEqual(isDedicatedPlatformUpdateEntry(generalEntry), false);
  });
});

describe('resolveEnabledDedicatedAppCodes', () => {
  const catalog = collectDedicatedAppCodesFromEntries([funideEntry, otherDedicatedEntry]);

  it('matches active installed apps in dedicated catalog without requiring is_dedicated flag', () => {
    const codes = resolveEnabledDedicatedAppCodes(
      [
        app({ code: 'funide-oa', is_dedicated: false }),
        app({ code: 'kuaiplm', is_dedicated: false }),
        app({ code: 'other-dedicated-app', is_active: false }),
      ],
      catalog,
    );
    assert.deepStrictEqual([...codes], ['funide-oa']);
  });

  it('does not drop apps when is_installed is omitted from API payload', () => {
    const codes = resolveEnabledDedicatedAppCodes(
      [
        {
          ...app({ code: 'funide-oa' }),
          is_installed: undefined as unknown as boolean,
        },
      ],
      catalog,
    );
    assert.deepStrictEqual([...codes], ['funide-oa']);
  });
});

describe('mergePlatformUpdateLogs', () => {
  it('keeps dedicated entries on the same date group as general entries', () => {
    const merged = mergePlatformUpdateLogs(
      [
        { ...generalEntry, date: '2026-09-24' },
        { ...generalEntry, id: 'general-old', date: '2026-09-20' },
      ],
      [{ ...funideEntry, date: '2026-09-24' }],
    );
    assert.deepStrictEqual(merged.map((entry) => entry.id), [
      'general-r01',
      'funide-r01',
      'general-old',
    ]);
  });
});

describe('filterPlatformUpdates dedicated tab', () => {
  const entries = [generalEntry, funideEntry];

  it('dedicated tab shows only dedicated entries', () => {
    assert.deepStrictEqual(filterPlatformUpdates('dedicated', entries).map((e) => e.id), ['funide-r01']);
  });

  it('appends dedicated tab after type tabs when dedicated entries exist', () => {
    assert.deepStrictEqual(getAvailableUpdateLogTabs(entries), [
      'all',
      'improvement',
      'fix',
      'dedicated',
    ]);
  });

  it('omits dedicated tab when no dedicated entries in list', () => {
    assert.deepStrictEqual(getAvailableUpdateLogTabs([generalEntry]), ['all', 'fix']);
  });
});

describe('filterVisiblePlatformUpdates', () => {
  const entries = [generalEntry, funideEntry, otherDedicatedEntry];

  it('shows general entries when no dedicated app is enabled', () => {
    const visible = filterVisiblePlatformUpdates(entries, new Set());
    assert.deepStrictEqual(visible.map((e) => e.id), ['general-r01']);
  });

  it('shows only matching dedicated entries per enabled app', () => {
    const visible = filterVisiblePlatformUpdates(entries, new Set(['funide-oa']));
    assert.deepStrictEqual(visible.map((e) => e.id), ['general-r01', 'funide-r01']);
  });

  it('merges multiple enabled dedicated apps without cross-leak', () => {
    const visible = filterVisiblePlatformUpdates(
      entries,
      new Set(['funide-oa', 'other-dedicated-app']),
    );
    assert.deepStrictEqual(visible.map((e) => e.id), ['general-r01', 'funide-r01', 'other-dedicated-r01']);
  });
});
