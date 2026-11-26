/**
 * 物料下拉选项统一展示：编号/名称 + 规格/型号 + 缩略图（名称可能重复时用于区分）
 */
import React from 'react';
import { theme } from 'antd';
import { useTranslation } from 'react-i18next';
import i18n from '../../config/i18n';
import { EMPTY_VALUE_PLACEHOLDER } from '../../utils/format';
import { SecureImage } from '../secure-image';

export const MATERIAL_SELECT_OPTION_ITEM_HEIGHT = 56;

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 下拉候选项内对当前搜索词做不区分大小写高亮（支持空格分隔多词） */
export function renderTextWithSearchHighlight(
  text: string,
  keyword: string,
  highlightStyle: React.CSSProperties,
): React.ReactNode {
  const tokens = keyword
    .trim()
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
  if (!tokens.length || !text) return text;
  const pattern = tokens.map(escapeRegExp).join('|');
  const re = new RegExp(`(${pattern})`, 'gi');
  const parts = text.split(re);
  if (parts.length <= 1) return text;
  return parts.map((part, index) =>
    index % 2 === 1 ? (
      <mark
        key={`${index}-${part}`}
        style={{
          padding: '0 1px',
          borderRadius: 2,
          ...highlightStyle,
        }}
      >
        {part}
      </mark>
    ) : (
      <React.Fragment key={`${index}-${part}`}>{part}</React.Fragment>
    ),
  );
}

function pickField(m: Record<string, unknown>, key: string): string {
  if (m == null || typeof m !== 'object') return '';
  const camel = m[key];
  if (camel != null && String(camel).trim()) return String(camel).trim();
  const snake = key.replace(/([A-Z])/g, '_$1').toLowerCase();
  const snakeVal = m[snake];
  if (snakeVal != null && String(snakeVal).trim()) return String(snakeVal).trim();
  return '';
}

export function resolveMaterialSelectImageFileUuid(raw: unknown): string | null {
  if (typeof raw === 'string') {
    const val = raw.trim();
    return /^[0-9a-fA-F-]{32,36}$/.test(val) ? val : null;
  }
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as { uuid?: unknown; uid?: unknown };
  const uuid = typeof obj.uuid === 'string' ? obj.uuid.trim() : '';
  if (/^[0-9a-fA-F-]{32,36}$/.test(uuid)) return uuid;
  const uid = typeof obj.uid === 'string' ? obj.uid.trim() : '';
  if (/^[0-9a-fA-F-]{32,36}$/.test(uid)) return uid;
  return null;
}

/** 下拉展开时的主行：编码：xxx - 品名：xxx */
export function formatMaterialSelectDropdownTitle(m: Record<string, unknown> | null | undefined): string {
  if (!m) return '';
  const mainCode = pickField(m, 'mainCode') || pickField(m, 'code');
  const nameVal = pickField(m, 'name');
  if (mainCode && nameVal) {
    return i18n.t('app.master-data.materials.selectCodeName', { code: mainCode, name: nameVal });
  }
  if (mainCode) return i18n.t('app.master-data.materials.selectCodeOnly', { code: mainCode });
  if (nameVal) return i18n.t('app.master-data.materials.selectNameOnly', { name: nameVal });
  return String(m.id ?? m.uuid ?? '');
}

/** 选中后输入框：品名 - 编码，不带字段前缀 */
export function formatMaterialSelectLabel(m: Record<string, unknown> | null | undefined): string {
  if (!m) return '';
  const mainCode = pickField(m, 'mainCode') || pickField(m, 'code');
  const nameVal = pickField(m, 'name');
  if (nameVal && mainCode) {
    return i18n.t('app.master-data.materials.selectChosen', { name: nameVal, code: mainCode });
  }
  return nameVal || mainCode || String(m.id ?? m.uuid ?? '');
}

export type MaterialSelectOptionContentProps = {
  material: Record<string, unknown> | null | undefined;
  /** 无物料数据时的回退文案 */
  fallbackLabel?: React.ReactNode;
  /** 下拉搜索框当前关键词，用于候选项高亮 */
  searchKeyword?: string;
};

export const MaterialSelectOptionContent: React.FC<MaterialSelectOptionContentProps> = ({
  material,
  fallbackLabel,
  searchKeyword = '',
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();

  if (!material) {
    return <span>{fallbackLabel ?? EMPTY_VALUE_PLACEHOLDER}</span>;
  }

  const mainCode = pickField(material, 'mainCode') || pickField(material, 'code');
  const nameVal = pickField(material, 'name');
  const specification = pickField(material, 'specification');
  const model = pickField(material, 'model');
  const images = Array.isArray(material.images) ? material.images : [];
  const fileUuid = images.length ? resolveMaterialSelectImageFileUuid(images[0]) : null;

  const metaParts: string[] = [];
  if (specification) {
    metaParts.push(`${t('app.master-data.materials.specification')}: ${specification}`);
  }
  if (model) {
    metaParts.push(`${t('app.master-data.materials.model')}: ${model}`);
  }

  const titleText =
    mainCode || nameVal ? formatMaterialSelectDropdownTitle(material) : String(fallbackLabel ?? '');
  const highlightStyle: React.CSSProperties = {
    background: token.colorPrimaryBg,
    color: token.colorPrimary,
    fontWeight: 600,
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        minWidth: 0,
        padding: '2px 0',
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          flexShrink: 0,
          borderRadius: token.borderRadiusSM,
          overflow: 'hidden',
          background: token.colorFillAlter,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: token.colorTextQuaternary,
          fontSize: 12,
        }}
      >
        {fileUuid ? (
          <SecureImage
            fileUuid={fileUuid}
            width={40}
            height={40}
            lazyLoad
            thumbSize={64}
            alt={nameVal || mainCode || t('app.master-data.materials.productImage')}
          />
        ) : (
          '-'
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0, lineHeight: 1.3 }}>
        <div
          title={formatMaterialSelectDropdownTitle(material)}
          style={{
            whiteSpace: 'normal',
            wordBreak: 'break-word',
            fontWeight: 500,
          }}
        >
          {mainCode || nameVal
            ? renderTextWithSearchHighlight(titleText, searchKeyword, highlightStyle)
            : fallbackLabel || EMPTY_VALUE_PLACEHOLDER}
        </div>
        {metaParts.length > 0 ? (
          <div
            style={{
              marginTop: 2,
              fontSize: 12,
              color: token.colorTextSecondary,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {metaParts.map((part, index) => (
              <React.Fragment key={part}>
                {index > 0 ? '  ' : null}
                {renderTextWithSearchHighlight(part, searchKeyword, highlightStyle)}
              </React.Fragment>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
};
