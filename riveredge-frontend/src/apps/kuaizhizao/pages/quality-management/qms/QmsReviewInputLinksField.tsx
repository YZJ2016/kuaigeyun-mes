import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ProFormItem } from '@ant-design/pro-components';
import { Select } from 'antd';
import { useTranslation } from 'react-i18next';
import { qualityImprovementApi } from '../../../services/quality-improvement';
import { qualityQmsApi, type QmsEvidenceLink } from '../../../services/quality-qms';
import { mergeFindingLinks, splitFindingLinks } from './QmsFindingLinksField';

const DOC_TYPE = 'qms_system_document';
const AUDIT_TYPE = 'qms_internal_audit';

export function splitReviewInputLinks(links?: QmsEvidenceLink[]) {
  const docIds: number[] = [];
  const auditIds: number[] = [];
  const other: QmsEvidenceLink[] = [];
  for (const link of links || []) {
    if (link.ref_type === DOC_TYPE && link.ref_id) docIds.push(Number(link.ref_id));
    else if (link.ref_type === AUDIT_TYPE && link.ref_id) auditIds.push(Number(link.ref_id));
    else other.push(link);
  }
  const finding = splitFindingLinks(other);
  return { docIds, auditIds, ...finding, other };
}

export function mergeReviewInputLinks(
  docIds: number[],
  auditIds: number[],
  ncIds: number[],
  eightDIds: number[],
  cache: Map<string, QmsEvidenceLink>,
  otherLinks: QmsEvidenceLink[] = [],
): QmsEvidenceLink[] {
  const out: QmsEvidenceLink[] = [...otherLinks];
  for (const id of docIds) {
    const key = `${DOC_TYPE}:${id}`;
    out.push(cache.get(key) || { ref_type: DOC_TYPE, ref_id: id });
  }
  for (const id of auditIds) {
    const key = `${AUDIT_TYPE}:${id}`;
    out.push(cache.get(key) || { ref_type: AUDIT_TYPE, ref_id: id });
  }
  out.push(...mergeFindingLinks(ncIds, eightDIds, cache));
  return out;
}

type Props = {
  docIds?: number[];
  auditIds?: number[];
  ncIds?: number[];
  eightDIds?: number[];
  onChange?: (links: QmsEvidenceLink[]) => void;
};

const QmsReviewInputLinksField: React.FC<Props> = ({
  docIds = [],
  auditIds = [],
  ncIds = [],
  eightDIds = [],
  onChange,
}) => {
  const { t } = useTranslation();
  const linkCacheRef = useRef<Map<string, QmsEvidenceLink>>(new Map());
  const [docOptions, setDocOptions] = useState<{ label: string; value: number }[]>([]);
  const [auditOptions, setAuditOptions] = useState<{ label: string; value: number }[]>([]);
  const [ncOptions, setNcOptions] = useState<{ label: string; value: number }[]>([]);
  const [eightDOptions, setEightDOptions] = useState<{ label: string; value: number }[]>([]);
  const [docLoading, setDocLoading] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [ncLoading, setNcLoading] = useState(false);
  const [eightDLoading, setEightDLoading] = useState(false);

  const emit = useCallback(
    (nextDoc: number[], nextAudit: number[], nextNc: number[], next8d: number[]) => {
      onChange?.(mergeReviewInputLinks(nextDoc, nextAudit, nextNc, next8d, linkCacheRef.current));
    },
    [onChange],
  );

  const searchDocs = useCallback(async (keyword?: string) => {
    setDocLoading(true);
    try {
      const res = await qualityQmsApi.systemDocuments.list({
        skip: 0,
        limit: 30,
        keyword: keyword?.trim() || undefined,
        zone: 'formal',
      });
      const opts = (res.items || []).map((row) => {
        const code = row.document_code;
        const label = `${code} ${row.title || ''}`.trim();
        linkCacheRef.current.set(`${DOC_TYPE}:${row.id}`, {
          ref_type: DOC_TYPE,
          ref_id: row.id,
          ref_code: code,
          ref_name: row.title,
        });
        return { label, value: row.id };
      });
      setDocOptions(opts);
    } finally {
      setDocLoading(false);
    }
  }, []);

  const searchAudits = useCallback(async (keyword?: string) => {
    setAuditLoading(true);
    try {
      const res = await qualityQmsApi.internalAudits.list({
        skip: 0,
        limit: 30,
        keyword: keyword?.trim() || undefined,
      });
      const opts = (res.items || []).map((row) => {
        const code = row.audit_code;
        const label = `${code} ${row.title || ''}`.trim();
        linkCacheRef.current.set(`${AUDIT_TYPE}:${row.id}`, {
          ref_type: AUDIT_TYPE,
          ref_id: row.id,
          ref_code: code,
          ref_name: row.title,
        });
        return { label, value: row.id };
      });
      setAuditOptions(opts);
    } finally {
      setAuditLoading(false);
    }
  }, []);

  const searchNc = useCallback(async (keyword?: string) => {
    setNcLoading(true);
    try {
      const res = await qualityImprovementApi.nonconformingLedger.list({
        skip: 0,
        limit: 30,
        keyword: keyword?.trim() || undefined,
      });
      const opts = (res.data || []).map((row) => {
        const code = String((row as { code?: string }).code || row.id);
        const label = `${code} ${(row as { product_name?: string }).product_name || ''}`.trim();
        linkCacheRef.current.set(`nonconforming_ledger:${row.id}`, {
          ref_type: 'nonconforming_ledger',
          ref_id: row.id,
          ref_code: code,
          ref_name: (row as { product_name?: string }).product_name,
        });
        return { label, value: Number(row.id) };
      });
      setNcOptions(opts);
    } finally {
      setNcLoading(false);
    }
  }, []);

  const search8d = useCallback(async (keyword?: string) => {
    setEightDLoading(true);
    try {
      const res = await qualityImprovementApi.eightD.list({
        skip: 0,
        limit: 30,
        keyword: keyword?.trim() || undefined,
      });
      const opts = (res.items || []).map((row) => {
        const code = String(row.report_code || row.id);
        const label = `${code} ${row.title || ''}`.trim();
        linkCacheRef.current.set(`quality_8d:${row.id}`, {
          ref_type: 'quality_8d',
          ref_id: row.id,
          ref_code: code,
          ref_name: row.title,
        });
        return { label, value: Number(row.id) };
      });
      setEightDOptions(opts);
    } finally {
      setEightDLoading(false);
    }
  }, []);

  useEffect(() => {
    void searchDocs();
    void searchAudits();
    void searchNc();
    void search8d();
  }, [search8d, searchAudits, searchDocs, searchNc]);

  return (
    <>
      <ProFormItem label={t('app.kuaizhizao.quality.qms.reviewInputDocs')} tooltip={t('app.kuaizhizao.quality.qms.inputLinksHint')}>
        <Select
          mode="multiple"
          allowClear
          showSearch
          filterOption={false}
          loading={docLoading}
          options={docOptions}
          value={docIds}
          placeholder={t('app.kuaizhizao.quality.qms.reviewInputDocsPlaceholder')}
          onSearch={(kw) => void searchDocs(kw)}
          onChange={(next) => emit(next as number[], auditIds, ncIds, eightDIds)}
        />
      </ProFormItem>
      <ProFormItem label={t('app.kuaizhizao.quality.qms.reviewInputAudits')}>
        <Select
          mode="multiple"
          allowClear
          showSearch
          filterOption={false}
          loading={auditLoading}
          options={auditOptions}
          value={auditIds}
          placeholder={t('app.kuaizhizao.quality.qms.reviewInputAuditsPlaceholder')}
          onSearch={(kw) => void searchAudits(kw)}
          onChange={(next) => emit(docIds, next as number[], ncIds, eightDIds)}
        />
      </ProFormItem>
      <ProFormItem label={t('app.kuaizhizao.quality.qms.findingLinksNc')}>
        <Select
          mode="multiple"
          allowClear
          showSearch
          filterOption={false}
          loading={ncLoading}
          options={ncOptions}
          value={ncIds}
          onSearch={(kw) => void searchNc(kw)}
          onChange={(next) => emit(docIds, auditIds, next as number[], eightDIds)}
        />
      </ProFormItem>
      <ProFormItem label={t('app.kuaizhizao.quality.qms.findingLinks8d')}>
        <Select
          mode="multiple"
          allowClear
          showSearch
          filterOption={false}
          loading={eightDLoading}
          options={eightDOptions}
          value={eightDIds}
          onSearch={(kw) => void search8d(kw)}
          onChange={(next) => emit(docIds, auditIds, ncIds, next as number[])}
        />
      </ProFormItem>
    </>
  );
};

export default QmsReviewInputLinksField;
