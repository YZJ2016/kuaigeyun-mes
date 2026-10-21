/**
 * 编号规则组件工具函数
 * 
 * 提供规则组件与表达式之间的转换功能
 */

import dayjs from '../config/dayjs';
import {
  CodeRuleComponent,
  AutoCounterComponent,
  DateComponent,
  FixedTextComponent,
  FormFieldComponent,
  createDefaultAutoCounterComponent,
} from '../types/codeRuleComponent';
import { getTimezoneFromSiteSetting } from './format';

/** 与后端 code_rule_component_service 自定义日期格式转换一致 */
export function customCodeRuleDateFormatToExpression(customFormat: string): string {
  const raw = customFormat.trim() || 'yMd';
  return raw
    .replace(/yyyy/g, '{YYYY}')
    .replace(/yy/g, '{YY}')
    .replace(/y/g, '{YYYY}')
    .replace(/MM/g, '{MM}')
    .replace(/M/g, '{MM}')
    .replace(/dd/g, '{DD}')
    .replace(/d/g, '{DD}');
}

/** 将 y/M/d 自定义格式转为 dayjs 格式串（替换顺序与后端 strftime 转换一致） */
export function customCodeRuleDateFormatToDayjs(customFormat: string): string {
  const raw = customFormat.trim() || 'yMd';
  return raw
    .replace(/yyyy/g, 'YYYY')
    .replace(/yy/g, 'YY')
    .replace(/y/g, 'YYYY')
    .replace(/dd/g, 'DD')
    .replace(/d/g, 'D');
}

function codeRulePreviewNow() {
  return dayjs().tz(getTimezoneFromSiteSetting());
}

/**
 * 规则组件服务类（前端版本）
 */
export class CodeRuleComponentService {
  /**
   * 将表达式解析为规则组件列表（向后兼容）
   */
  static expressionToComponents(expression: string): CodeRuleComponent[] {
    if (!expression) {
      // 如果没有表达式，返回默认的自动计数组件
      return [createDefaultAutoCounterComponent(0)];
    }

    const components: CodeRuleComponent[] = [];
    let order = 0;

    // 解析字段引用 {FIELD:field_name}
    const fieldPattern = /\{FIELD:([^}]+)\}/g;
    const fieldMatches = Array.from(expression.matchAll(fieldPattern));
    for (const match of fieldMatches) {
      const fieldName = match[1];
      components.push({
        type: 'form_field',
        order: order++,
        field_name: fieldName,
      } as FormFieldComponent);
    }

    // 解析日期格式
    const datePatterns = [
      { pattern: /\{YYYY\}\{MM\}\{DD\}/, format: 'YYYYMMDD' },
      { pattern: /\{YYYY\}\{MM\}/, format: 'YYYYMM' },
      { pattern: /\{YYYY\}/, format: 'YYYY' },
      { pattern: /\{YY\}\{MM\}\{DD\}/, format: 'YYMMDD' },
      { pattern: /\{YY\}\{MM\}/, format: 'YYMM' },
      { pattern: /\{YY\}/, format: 'YY' },
    ];

    let dateFound = false;
    for (const { pattern, format } of datePatterns) {
      if (pattern.test(expression)) {
        components.push({
          type: 'date',
          order: order++,
          format_type: 'preset',
          preset_format: format,
        } as DateComponent);
        dateFound = true;
        break;
      }
    }

    // 解析序号格式
    const seqPattern = /\{SEQ(?::(\d+))?\}/;
    const seqMatch = expression.match(seqPattern);
    if (seqMatch) {
      const digits = seqMatch[1] ? parseInt(seqMatch[1]) : 5;
      components.push({
        type: 'auto_counter',
        order: order++,
        digits,
        fixed_width: true,
        reset_cycle: 'never',
        initial_value: 1,
      } as AutoCounterComponent);
    }

    // 提取固定字符（表达式中的其他文本）
    let tempExpr = expression;
    // 移除所有变量占位符
    tempExpr = tempExpr.replace(/\{FIELD:[^}]+\}/g, '');
    tempExpr = tempExpr.replace(/\{Y{2,4}\}\{M{2}\}\{D{2}\}/g, '');
    tempExpr = tempExpr.replace(/\{Y{2,4}\}\{M{2}\}/g, '');
    tempExpr = tempExpr.replace(/\{Y{2,4}\}/g, '');
    tempExpr = tempExpr.replace(/\{SEQ(?::\d+)?\}/g, '');
    tempExpr = tempExpr.replace(/\{[^}]+\}/g, ''); // 移除其他可能的变量

    // 如果还有剩余字符，作为固定字符
    if (tempExpr.trim()) {
      // 尝试分割固定字符（可能在变量前后）
      const parts = expression.split(/\{[^}]+\}/);
      for (const part of parts) {
        if (part.trim()) {
          components.push({
            type: 'fixed_text',
            order: order++,
            text: part.trim(),
          } as FixedTextComponent);
        }
      }
    }

    // 如果没有自动计数组件，添加一个默认的（必选）
    const hasCounter = components.some(comp => comp.type === 'auto_counter');
    if (!hasCounter) {
      components.push(createDefaultAutoCounterComponent(order));
    }

    // 按order排序
    components.sort((a, b) => a.order - b.order);

    return components;
  }

  /**
   * 将规则组件列表转换为表达式（向后兼容）
   */
  static componentsToExpression(components: CodeRuleComponent[]): string {
    if (!components || components.length === 0) {
      return '';
    }

    // 按order排序
    const sortedComponents = [...components].sort((a, b) => a.order - b.order);

    const parts: string[] = [];

    for (const comp of sortedComponents) {
      switch (comp.type) {
        case 'auto_counter':
          const counter = comp as AutoCounterComponent;
          if (counter.digits > 0) {
            parts.push(`{SEQ:${counter.digits}}`);
          } else {
            parts.push('{SEQ}');
          }
          break;

        case 'date':
          const date = comp as DateComponent;
          if (date.format_type === 'preset') {
            const presetFormat = date.preset_format || 'YYYYMMDD';
            const dateMap: Record<string, string> = {
              'YYYYMMDD': '{YYYY}{MM}{DD}',
              'YYYYMM': '{YYYY}{MM}',
              'YYYY': '{YYYY}',
              'YYMMDD': '{YY}{MM}{DD}',
              'YYMM': '{YY}{MM}',
              'YY': '{YY}',
            };
            parts.push(dateMap[presetFormat] || '{YYYY}{MM}{DD}');
          } else {
            parts.push(customCodeRuleDateFormatToExpression(date.custom_format || 'yMd'));
          }
          break;

        case 'fixed_text':
          const fixed = comp as FixedTextComponent;
          parts.push(fixed.text);
          break;

        case 'form_field':
          const field = comp as FormFieldComponent;
          parts.push(`{FIELD:${field.field_name}}`);
          break;
      }
    }

    return parts.join('');
  }

  /**
   * 根据规则组件生成预览编号（前端版本）
   * 用于在配置时实时预览编号效果
   */
  static previewComponents(
    components: CodeRuleComponent[],
    sampleContext?: Record<string, any>
  ): string {
    if (!components || components.length === 0) {
      return '';
    }

    // 按order排序
    const sortedComponents = [...components].sort((a, b) => a.order - b.order);

    const parts: string[] = [];
    const now = codeRulePreviewNow();

    for (const comp of sortedComponents) {
      switch (comp.type) {
        case 'auto_counter':
          const counter = comp as AutoCounterComponent;
          const sampleSeq = counter.initial_value || 1;
          let seqStr = String(sampleSeq);
          
          if (counter.fixed_width && counter.digits > 0) {
            seqStr = seqStr.padStart(counter.digits, '0');
          }
          
          parts.push(seqStr);
          break;

        case 'date':
          const date = comp as DateComponent;
          if (date.format_type === 'preset') {
            const presetFormat = date.preset_format || 'YYYYMMDD';
            const dateMap: Record<string, string> = {
              YYYYMMDD: now.format('YYYYMMDD'),
              YYYYMM: now.format('YYYYMM'),
              YYYY: now.format('YYYY'),
              YYMMDD: now.format('YYMMDD'),
              YYMM: now.format('YYMM'),
              YY: now.format('YY'),
            };
            parts.push(dateMap[presetFormat] || dateMap.YYYYMMDD);
          } else {
            const dayjsFormat = customCodeRuleDateFormatToDayjs(date.custom_format || 'yMd');
            parts.push(now.format(dayjsFormat));
          }
          break;

        case 'fixed_text':
          const fixed = comp as FixedTextComponent;
          parts.push(fixed.text || '');
          break;

        case 'form_field':
          const field = comp as FormFieldComponent;
          if (sampleContext && field.field_name in sampleContext) {
            parts.push(String(sampleContext[field.field_name]));
          } else {
            // 如果没有提供上下文，使用字段名作为占位符
            parts.push(`[${field.field_name}]`);
          }
          break;
      }
    }

    return parts.join('');
  }
}
