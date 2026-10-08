import 'antd/es/table/interface';
import 'antd/lib/table/interface';

/** Layout metadata consumed by UniTable, carried through ProColumns. */
interface UniTableColumnLayout {
  uniTableKeepWidth?: boolean;
  uniTableRemainderFlex?: boolean;
  uniTablePrimaryFlex?: boolean;
  uniTablePrimaryFlexMaxWidth?: number;
  uniTableAuditStackedColumn?: boolean;
  uniTableMarkerBadgeColumn?: boolean;
  uniTableFillerColumn?: boolean;
  uniTableProgressColumn?: boolean;
  uniTableDetailProgressColumn?: boolean;
  resizable?: boolean;
  defaultShow?: boolean;
}

declare module 'antd/es/table/interface' {
  interface ColumnType<RecordType> extends UniTableColumnLayout {}
}

declare module 'antd/lib/table/interface' {
  interface ColumnType<RecordType> extends UniTableColumnLayout {}
}
