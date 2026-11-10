import { describe, expect, it } from 'vitest';
import {
  isAssociatedObjectDisplayOnly,
  resolveAssociatedDisplayMode,
} from './customFieldAssociatedDisplayMode';

describe('isAssociatedObjectDisplayOnly', () => {
  it('is true for associated_object + displayMode display', () => {
    expect(
      isAssociatedObjectDisplayOnly({
        field_type: 'associated_object',
        config: { displayMode: 'display', sourceField: 'materialId' },
      }),
    ).toBe(true);
  });

  it('is false for input / number / select', () => {
    expect(
      isAssociatedObjectDisplayOnly({
        field_type: 'associated_object',
        config: { displayMode: 'input', sourceField: 'materialId' },
      }),
    ).toBe(false);
    expect(
      isAssociatedObjectDisplayOnly({
        field_type: 'associated_object',
        config: { displayMode: 'select' },
      }),
    ).toBe(false);
  });

  it('is false for display without sourceField', () => {
    expect(
      isAssociatedObjectDisplayOnly({
        field_type: 'associated_object',
        config: { displayMode: 'display' },
      }),
    ).toBe(false);
  });

  it('defaults with sourceField to input (not display-only)', () => {
    expect(resolveAssociatedDisplayMode('associated_object', { sourceField: 'materialId' })).toBe(
      'input',
    );
    expect(
      isAssociatedObjectDisplayOnly({
        field_type: 'associated_object',
        config: { sourceField: 'materialId' },
      }),
    ).toBe(false);
  });
});

describe('detail visibility for display-only', () => {
  it('marks display-only associated_object for exclusion from detail', () => {
    expect(
      isAssociatedObjectDisplayOnly({
        field_type: 'associated_object',
        config: { displayMode: 'display', sourceField: 'materialId', returnField: 'base_unit' },
      }),
    ).toBe(true);
  });
});
