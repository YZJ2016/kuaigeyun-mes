import assert from 'node:assert/strict';
import { test } from 'node:test';
import { eligibleIotConnections, buildIotConnectionConfig } from '../../src/pages/system/application-connections/iotConnectionConfig.ts';

test('multiple enabled connections of the same type remain individually selectable', () => {
  const rows = [
    { uuid: 'a', type: 'mqtt', is_active: true },
    { uuid: 'b', type: 'mqtt', is_active: true },
    { uuid: 'c', type: 'mqtt', is_active: false },
    { uuid: 'd', type: 'jetlinks', is_active: true },
  ];
  assert.deepEqual(eligibleIotConnections(rows, 'mqtt').map(r => r.uuid), ['a', 'b']);
  assert.deepEqual(eligibleIotConnections(rows, 'jetlinks').map(r => r.uuid), ['d']);
});

test('HTTP connections retain only supported active public types', () => {
  assert.equal(eligibleIotConnections([
    { type: 'API', is_active: true }, { type: 'Webhook', is_active: true },
    { type: 'mqtt', is_active: true }, { type: 'api', is_active: false },
  ], 'http').length, 2);
});

test('connector configuration keeps credentials and excludes connection metadata and ingest mapping', () => {
  assert.deepEqual(buildIotConnectionConfig('mqtt', {
    host: 'broker.example', port: 1883, username: 'operator', password: 'test-only', use_tls: false,
    code: 'line-a', name: 'Line A', topic: 'plant/+', integration_uuid: 'a', tags_path: 'tags',
  }), { host: 'broker.example', port: 1883, username: 'operator', password: 'test-only', use_tls: false });
  assert.deepEqual(buildIotConnectionConfig('jetlinks', { base_url: 'https://iot.example', token: 'test-only', name: 'ignore' }),
    { base_url: 'https://iot.example', token: 'test-only' });
  assert.throws(() => buildIotConnectionConfig('http', {}));
});
