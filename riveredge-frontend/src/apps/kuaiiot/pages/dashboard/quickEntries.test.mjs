import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('KuaiIOT dashboard renders an icon for every quick entry', () => {
  const source = readFileSync(new URL('./index.tsx', import.meta.url), 'utf8');
  const expectedIcons = [
    'LinkOutlined',
    'DeploymentUnitOutlined',
    'AlertOutlined',
    'ClusterOutlined',
    'DashboardOutlined',
    'TagsOutlined',
  ];

  expectedIcons.forEach((iconName) => {
    assert.match(source, new RegExp(`<${iconName}\\b`));
  });
});
