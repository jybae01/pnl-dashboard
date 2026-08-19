import { createRoot } from 'react-dom/client';
import { PnlReportingUploadSection } from './management/PnlReportingUploadSection';

createRoot(document.getElementById('root')!).render(
  <PnlReportingUploadSection
    templateDownloadAvailable={false}
    existingPlan={{ reportingYear: 2026, registeredAt: '2026-08-18T09:00:00Z' }}
    validationSummary={{
      status: 'INVALID',
      errorCount: 3,
      warningCount: 1,
      truncated: true,
      errors: [
        {
          severity: 'ERROR',
          errorCode: 'VALUE_REQUIRED',
          sheet: '03_판관비상세',
          displayLabel: '1. 인건비',
          month: 5,
          message: '실적 기준월 이내의 값은 비워둘 수 없습니다.',
        },
        {
          severity: 'ERROR',
          errorCode: 'VALUE_REQUIRED',
          sheet: '03_판관비상세',
          displayLabel: '2. 복리후생비',
          month: 5,
          message: '필수 값을 입력하세요.',
        },
      ],
      warnings: [
        {
          severity: 'WARNING',
          errorCode: 'ROUNDING',
          sheet: '01_손익계산서',
          displayLabel: '매출총이익',
          message: '합계와 세부 항목에 반올림 차이가 있습니다.',
        },
      ],
    }}
  />,
);
