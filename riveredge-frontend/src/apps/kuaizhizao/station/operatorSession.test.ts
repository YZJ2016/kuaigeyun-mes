import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  STATION_OPERATOR_SESSION_HEADER,
  acceptStationOperatorSession,
  clearStationOperatorSession,
  getStationOperatorCredential,
  getStationOperatorSessionInfo,
  hasStationOperatorSession,
  stationOperatorSessionHeaders,
  subscribeStationOperatorSession,
  type StationOperatorSessionInfo,
} from './operatorSession.ts';

const SESSION: StationOperatorSessionInfo = {
  id: 1,
  uuid: 'u-1',
  workstation_id: 9,
  workstation_name: '装配一工位',
  operator_employee_id: 5,
  operator_user_id: 3,
  operator_name: '张三',
  confirm_method: 'employee_code',
  status: 'active',
  issued_at: '2026-10-08T10:00:00Z',
  last_seen_at: '2026-10-08T10:00:00Z',
  closed_at: null,
  close_reason: null,
};

test('credential starts empty and builds no header', () => {
  clearStationOperatorSession();
  assert.equal(getStationOperatorCredential(), null);
  assert.equal(getStationOperatorSessionInfo(), null);
  assert.equal(hasStationOperatorSession(), false);
  assert.deepEqual(stationOperatorSessionHeaders(), {});
});

test('accepted credential stays only in module memory and builds the business header', () => {
  clearStationOperatorSession();
  acceptStationOperatorSession({ credential: '  raw-credential  ', session: SESSION });
  assert.equal(getStationOperatorCredential(), 'raw-credential');
  assert.equal(hasStationOperatorSession(), true);
  assert.deepEqual(stationOperatorSessionHeaders(), {
    [STATION_OPERATOR_SESSION_HEADER]: 'raw-credential',
  });
  assert.equal(getStationOperatorSessionInfo()?.operator_user_id, 3);
  clearStationOperatorSession();
});

test('empty credential is ignored', () => {
  clearStationOperatorSession();
  acceptStationOperatorSession({ credential: '   ', session: SESSION });
  assert.equal(getStationOperatorCredential(), null);
  assert.equal(hasStationOperatorSession(), false);
});

test('clear drops credential and session info', () => {
  acceptStationOperatorSession({ credential: 'tok', session: SESSION });
  clearStationOperatorSession();
  assert.equal(getStationOperatorCredential(), null);
  assert.equal(getStationOperatorSessionInfo(), null);
  assert.deepEqual(stationOperatorSessionHeaders(), {});
});

test('subscribers are notified on accept and clear, unsubscribe stops it', () => {
  clearStationOperatorSession();
  let calls = 0;
  const unsubscribe = subscribeStationOperatorSession(() => {
    calls += 1;
  });
  acceptStationOperatorSession({ credential: 'tok', session: SESSION });
  clearStationOperatorSession();
  assert.equal(calls, 2);
  unsubscribe();
  acceptStationOperatorSession({ credential: 'tok2', session: SESSION });
  assert.equal(calls, 2);
  clearStationOperatorSession();
});
