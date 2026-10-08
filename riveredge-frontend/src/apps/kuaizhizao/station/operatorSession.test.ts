import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  STATION_OPERATOR_SESSION_HEADER,
  acceptStationOperatorSession,
  applyStationOperatorSessionHeader,
  clearStationOperatorSession,
  getStationOperatorCredential,
  getStationOperatorSessionInfo,
  hasStationOperatorSession,
  isWriteMethodForStationSession,
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

// ===== apiRequest 注入分支（applyStationOperatorSessionHeader）=====

test('inject: write method with opt-in and credential attaches the header', () => {
  clearStationOperatorSession();
  acceptStationOperatorSession({ credential: 'cred-1', session: SESSION });
  const headers: Record<string, string> = {};
  applyStationOperatorSessionHeader(headers, { optIn: true, method: 'POST' });
  assert.equal(headers[STATION_OPERATOR_SESSION_HEADER], 'cred-1');
  clearStationOperatorSession();
});

test('inject: explicitly opted-in GET attaches the header for operator-scoped reads', () => {
  clearStationOperatorSession();
  acceptStationOperatorSession({ credential: 'cred-1', session: SESSION });
  const headers: Record<string, string> = {};
  applyStationOperatorSessionHeader(headers, { optIn: true, method: 'GET' });
  assert.equal(headers[STATION_OPERATOR_SESSION_HEADER], 'cred-1');
  clearStationOperatorSession();
});

test('inject: without credential nothing is attached', () => {
  clearStationOperatorSession();
  const headers: Record<string, string> = {};
  applyStationOperatorSessionHeader(headers, { optIn: true, method: 'POST' });
  assert.equal(STATION_OPERATOR_SESSION_HEADER in headers, false);
});

test('inject: caller-provided same-name header is not overwritten', () => {
  clearStationOperatorSession();
  acceptStationOperatorSession({ credential: 'cred-1', session: SESSION });
  const headers: Record<string, string> = {
    [STATION_OPERATOR_SESSION_HEADER]: 'caller-value',
  };
  applyStationOperatorSessionHeader(headers, { optIn: true, method: 'POST' });
  assert.equal(headers[STATION_OPERATOR_SESSION_HEADER], 'caller-value');
  clearStationOperatorSession();
});

test('inject: DELETE counts as write; missing opt-in attaches nothing', () => {
  clearStationOperatorSession();
  acceptStationOperatorSession({ credential: 'cred-1', session: SESSION });
  const del: Record<string, string> = {};
  applyStationOperatorSessionHeader(del, { optIn: true, method: 'DELETE' });
  assert.equal(del[STATION_OPERATOR_SESSION_HEADER], 'cred-1');
  const noOptIn: Record<string, string> = {};
  applyStationOperatorSessionHeader(noOptIn, { method: 'POST' });
  assert.equal(STATION_OPERATOR_SESSION_HEADER in noOptIn, false);
  const optOut: Record<string, string> = {};
  applyStationOperatorSessionHeader(optOut, { optIn: false, method: 'PUT' });
  assert.equal(STATION_OPERATOR_SESSION_HEADER in optOut, false);
  clearStationOperatorSession();
});

test('inject: write-method table matches apiRequest', () => {
  assert.equal(isWriteMethodForStationSession('POST'), true);
  assert.equal(isWriteMethodForStationSession('PUT'), true);
  assert.equal(isWriteMethodForStationSession('PATCH'), true);
  assert.equal(isWriteMethodForStationSession('DELETE'), true);
  assert.equal(isWriteMethodForStationSession('post'), true);
  assert.equal(isWriteMethodForStationSession('GET'), false);
  assert.equal(isWriteMethodForStationSession(undefined), false);
});
