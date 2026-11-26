export interface PurchaseInvoice {
    id: number;
    tenant_id: number;
    invoice_code: string;
    purchase_order_id?: number | null;
    purchase_order_code?: string | null;
    supplier_id: number;
    supplier_name: string;
    invoice_number: string;
    invoice_date: string;
    invoice_type: string;
    tax_rate: number;
    invoice_amount: number;
    tax_amount: number;
    total_amount: number;
    discount_amount?: number;
    adjust_payable?: boolean;
    status: string;
    reviewer_id?: number;
    reviewer_name?: string;
    review_time?: string;
    review_status: string;
    settlement_mode?: 'summary' | 'detail' | string;
    review_remarks?: string;
    payable_id?: number;
    payable_code?: string;
    attachment_path?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
  created_by_name?: string;
  updated_by_name?: string;
}

export interface PurchaseInvoiceListParams {
    skip?: number;
    limit?: number;
    status?: string;
    supplier_id?: number;
    purchase_order_id?: number;
    start_date?: string;
    end_date?: string;
    keyword?: string;
    invoice_code?: string;
    supplier_name?: string;
    invoice_number?: string;
    review_status?: string;
    created_start_date?: string;
    created_end_date?: string;
    updated_start_date?: string;
    updated_end_date?: string;
    sort_field?: string;
    sort_order?: 'asc' | 'desc';
    settlement_mode?: 'summary' | 'detail' | '';
}

export interface PurchaseInvoiceDetailItemCreate {
    item_name: string;
    spec_model?: string | null;
    unit?: string;
    quantity?: number;
    unit_price?: number;
    amount: number;
    tax_rate: number;
    tax_amount: number;
    source_doc_type: string;
    source_doc_id: number;
    source_line_id: number;
    partner_statement_line_id?: number | null;
}

export interface PurchaseInvoiceCreateData {
    settlement_mode?: 'summary' | 'detail';
    invoice_code?: string;
    purchase_order_id?: number | null;
    purchase_order_code?: string | null;
    supplier_id: number;
    supplier_name: string;
    invoice_number: string;
    invoice_date: string;
    invoice_type: string;
    tax_rate: number;
    invoice_amount: number;
    tax_amount?: number;
    total_amount?: number;
    discount_amount?: number;
    adjust_payable?: boolean;
    status?: string;
    review_status?: string;
    payable_id?: number;
    payable_code?: string;
    notes?: string;
    attachments?: unknown;
    source_type?: 'purchase_order' | 'purchase_receipt' | 'payable';
    source_id?: number;
    source_ids?: number[];
    pull_receipt_lines?: { purchase_receipt_item_id: number; amount: number }[];
    detail_items?: PurchaseInvoiceDetailItemCreate[];
    concurrent_settlement?: {
        enabled: boolean;
        total_amount: number;
        payment_method: string;
        bank_account_id?: number | null;
        bank_account?: string | null;
        voucher_date?: string | null;
        notes?: string | null;
    };
}
