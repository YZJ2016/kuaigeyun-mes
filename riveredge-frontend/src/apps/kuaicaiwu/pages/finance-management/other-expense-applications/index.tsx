import React from 'react';
import MiscVoucherListPage from '../shared/MiscVoucherListPage';
import {
  OTHER_EXPENSE_APPLICATION_RESOURCE,
  otherExpenseApplicationService,
} from '../../../services/finance/other-expense-application';
import { KUAIZHIZAO_DOC_HOST } from '../../../../../utils/documentFormReferenceLoad';

const OtherExpenseApplicationsPage: React.FC = () => (
  <MiscVoucherListPage
    kind="expense"
    documentVariant="expense_application"
    auditEntityType="other_expense_application"
    resource={OTHER_EXPENSE_APPLICATION_RESOURCE}
    hostResource={KUAIZHIZAO_DOC_HOST.otherExpenseApplication}
    menuTitleKey="app.kuaicaiwu.menu.finance-management.other-expense-applications"
    i18nPrefix="app.kuaicaiwu.otherExpense"
    createButtonI18nKey="app.kuaicaiwu.otherExpenseApplication.createButton"
    createTitleI18nKey="app.kuaicaiwu.otherExpenseApplication.createTitle"
    editTitleI18nKey="app.kuaicaiwu.otherExpenseApplication.editTitle"
    columnPersistenceId="apps.kuaicaiwu.pages.finance-management.other-expense-applications.list-v1"
    service={otherExpenseApplicationService}
  />
);

export default OtherExpenseApplicationsPage;
