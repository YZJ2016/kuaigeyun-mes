'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  isNavigationAllowed,
  STATION_ENTRY_PATH,
} = require('./navigation-policy');

const ORIGIN = 'https://mes.example.com';

test('允许：登录、锁屏、工位入口及真实子路径', () => {
  const allowed = [
    `${ORIGIN}/login`,
    `${ORIGIN}/login?redirect=%2Fapps%2Fkuaizhizao`,
    `${ORIGIN}/login?tenant_id=1#top`,
    `${ORIGIN}/login/`,
    `${ORIGIN}/lock-screen`,
    `${ORIGIN}${STATION_ENTRY_PATH}`,
    `${ORIGIN}${STATION_ENTRY_PATH}?workstationId=ws-01`,
    `${ORIGIN}${STATION_ENTRY_PATH}#section`,
    `${ORIGIN}${STATION_ENTRY_PATH}/work-orders/123`,
    `${ORIGIN}${STATION_ENTRY_PATH}/reporting/kiosk?x=1#y`,
  ];
  for (const url of allowed) {
    assert.equal(isNavigationAllowed(url, ORIGIN), true, url);
  }
});

test('允许：http 协议与带端口 origin 同样适用', () => {
  assert.equal(isNavigationAllowed('http://192.168.1.10:8080/login', 'http://192.168.1.10:8080'), true);
  assert.equal(
    isNavigationAllowed('http://192.168.1.10:8080' + STATION_ENTRY_PATH + '/a', 'http://192.168.1.10:8080'),
    true,
  );
});

test('拒绝：同源 PC 路由与其他公共路径', () => {
  const denied = [
    `${ORIGIN}/`,
    `${ORIGIN}`,
    `${ORIGIN}/docs`,
    `${ORIGIN}/init/wizard`,
    `${ORIGIN}/infra`,
    `${ORIGIN}/infra/login`,
    `${ORIGIN}/acme`,
    `${ORIGIN}/apps/kuaizhizao/master-data/items`,
    `${ORIGIN}/apps/kuaizhizao/production-execution`,
    `${ORIGIN}/apps/kuaizhizao/production-execution/terminal`,
    `${ORIGIN}/apps/kuaireport/dashboards/shared`,
    `${ORIGIN}/system/users`,
  ];
  for (const url of denied) {
    assert.equal(isNavigationAllowed(url, ORIGIN), false, url);
  }
});

test('拒绝：伪前缀不匹配', () => {
  const denied = [
    `${ORIGIN}/loginx`,
    `${ORIGIN}/loginx/page`,
    `${ORIGIN}/lock-screenx`,
    `${ORIGIN}${STATION_ENTRY_PATH}x`,
    `${ORIGIN}${STATION_ENTRY_PATH}-evil`,
    `${ORIGIN}/apps/kuaizhizao/production-execution/stationx`,
    `${ORIGIN}/login/../apps/kuaizhizao/master-data`,
    `${ORIGIN}//login`,
    `${ORIGIN}/LOGIN`,
  ];
  for (const url of denied) {
    assert.equal(isNavigationAllowed(url, ORIGIN), false, url);
  }
});

test('拒绝：跨源跳转（含相似域名与不同端口）', () => {
  const denied = [
    `https://evil.com${STATION_ENTRY_PATH}`,
    `https://evil.com/login`,
    `https://mes.example.com.evil.com/login`,
    `https://mes.example.com:8443/login`,
    `http://mes.example.com/login`,
    `https://user:pass@mes.example.com/login`,
  ];
  for (const url of denied) {
    assert.equal(isNavigationAllowed(url, ORIGIN), false, url);
  }
});

test('拒绝：非 http(s) 协议与畸形输入', () => {
  const denied = [
    'file:///etc/passwd',
    'file:///C:/Windows/system.ini',
    'javascript:alert(1)',
    'data:text/html,<h1>x</h1>',
    'ftp://mes.example.com/login',
    'about:blank',
    '',
    '   ',
    'not a url',
    '/login',
    'mes.example.com/login',
    null,
    undefined,
    123,
  ];
  for (const url of denied) {
    assert.equal(isNavigationAllowed(url, ORIGIN), false, String(url));
  }
});

test('拒绝：服务地址本身非法时不放行任何目标', () => {
  const badOrigins = ['', 'not a url', 'ftp://mes.example.com', null, undefined];
  for (const origin of badOrigins) {
    assert.equal(isNavigationAllowed(`${ORIGIN}/login`, origin), false, String(origin));
  }
});

test('serverOrigin 带路径或尾斜杠时按 origin 归一', () => {
  assert.equal(isNavigationAllowed(`${ORIGIN}/login`, `${ORIGIN}/`), true);
  assert.equal(isNavigationAllowed(`${ORIGIN}/login`, `${ORIGIN}/base/path`), true);
});
