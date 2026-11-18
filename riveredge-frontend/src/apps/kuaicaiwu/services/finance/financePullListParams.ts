/** 轻财务取单候选列表查询（与 UniPullQuery date_from/date_to 对齐） */
export type FinancePullCandidateListParams = {
  skip?: number;
  limit?: number;
  keyword?: string;
  date_from?: string;
  date_to?: string;
  supplier_id?: number;
  customer_id?: number;
};
