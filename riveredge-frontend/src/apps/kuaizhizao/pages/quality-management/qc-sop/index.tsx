/**
 * QC 材料 SOP（R-01 #55）：与 PE 制造 SOP 分域，共用文控能力。
 */

import React from 'react';
import SOPPage from '../../../../master-data/pages/process/sop';

const QcSopPage: React.FC = () => <SOPPage fixedSopDomain="qc" />;

export default QcSopPage;
