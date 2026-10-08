import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  STATION_ENTRY_PATH,
  isPureStationAccount,
  isStationAllowedPathname,
} from './stationAccess.ts';

const ENTRY = '/apps/kuaizhizao/production-execution/station';

test('all-station roles make a pure station account', () => {
  assert.equal(
    isPureStationAccount({ roles: [{ role_type: 'station' }] }),
    true,
  );
  assert.equal(
    isPureStationAccount({
      roles: [{ role_type: 'station' }, { role_type: 'STATION' }, { role_type: ' station ' }],
    }),
    true,
  );
});

test('mixed or non-station roles are not a pure station account', () => {
  assert.equal(
    isPureStationAccount({
      roles: [{ role_type: 'station' }, { role_type: 'internal' }],
    }),
    false,
  );
  assert.equal(
    isPureStationAccount({
      roles: [{ role_type: 'station' }, { role_type: 'external' }],
    }),
    false,
  );
  assert.equal(
    isPureStationAccount({ roles: [{ role_type: 'internal' }] }),
    false,
  );
  // 缺 role_type（旧缓存/未透出）一律按非 station 处理
  assert.equal(isPureStationAccount({ roles: [{ role_type: null }] }), false);
  assert.equal(isPureStationAccount({ roles: [{}] }), false);
  assert.equal(isPureStationAccount({ roles: [null, { role_type: 'station' }] }), false);
});

test('no roles or admin means not a pure station account', () => {
  assert.equal(isPureStationAccount({ roles: [] }), false);
  assert.equal(isPureStationAccount({}), false);
  assert.equal(isPureStationAccount({ roles: null }), false);
  assert.equal(isPureStationAccount(null), false);
  assert.equal(isPureStationAccount(undefined), false);
  assert.equal(
    isPureStationAccount({
      is_infra_admin: true,
      roles: [{ role_type: 'station' }],
    }),
    false,
  );
});

test('station entry and real subpaths are allowed', () => {
  assert.equal(isStationAllowedPathname(ENTRY), true);
  assert.equal(isStationAllowedPathname(`${ENTRY}/`), true);
  assert.equal(isStationAllowedPathname(`${ENTRY}/andon`), true);
  assert.equal(isStationAllowedPathname(`${ENTRY}/work-orders/12/kiosk`), true);
  assert.equal(isStationAllowedPathname(`${ENTRY}/reporting/kiosk`), true);
  assert.equal(isStationAllowedPathname(`${ENTRY}/execution?workstationId=9`), true);
  assert.equal(isStationAllowedPathname(`${ENTRY}/andon#frag`), true);
});

test('lock screen stays reachable for a pure station account', () => {
  assert.equal(isStationAllowedPathname('/lock-screen'), true);
  assert.equal(isStationAllowedPathname('/lock-screen?from=station'), true);
});

test('fake prefixes and PC paths are rejected', () => {
  assert.equal(isStationAllowedPathname(`${ENTRY}x`), false);
  assert.equal(isStationAllowedPathname(`${ENTRY}other`), false);
  assert.equal(isStationAllowedPathname('/apps/kuaizhizao/production-execution/station-reporting'), false);
  assert.equal(isStationAllowedPathname('/apps/kuaizhizao/production-execution/reporting'), false);
  assert.equal(isStationAllowedPathname('/apps/kuaizhizao/production-execution/work-orders'), false);
  assert.equal(isStationAllowedPathname('/system/users'), false);
  assert.equal(isStationAllowedPathname('/login'), false);
  assert.equal(isStationAllowedPathname('/'), false);
  assert.equal(isStationAllowedPathname(''), false);
});

test('exported entry path stays aligned with the client channel constant', () => {
  assert.equal(STATION_ENTRY_PATH, ENTRY);
});
