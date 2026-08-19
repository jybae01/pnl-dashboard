import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  PnlReportingUploadSection,
  type PnlReportingUploadSectionProps,
} from './management/PnlReportingUploadSection';

function renderShell(overrides: Partial<PnlReportingUploadSectionProps> = {}) {
  const props: PnlReportingUploadSectionProps = {
    templateDownloadAvailable: false,
    onPlanSubmit: vi.fn(),
    onActualSubmit: vi.fn(),
    ...overrides,
  };
  return { ...render(<PnlReportingUploadSection {...props} />), props };
}

function xlsx(name: string) {
  return new File(['workbook-bytes'], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('P&L reporting upload UI shell', () => {
  it('renders isolated PLAN, ACTUAL, template, and idle validation shells with .xlsx-only selectors', () => {
    renderShell();

    expect(screen.getByRole('heading', { name: 'P&L Reporting Data' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '계획 데이터 등록' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '실적 데이터 등록' })).toBeInTheDocument();
    expect(screen.getByLabelText('PLAN 기준연도')).toBeInTheDocument();
    expect(screen.getByLabelText('ACTUAL 기준연도')).toBeInTheDocument();
    expect(screen.getByLabelText('ACTUAL 실적 기준월')).toHaveValue('');
    expect(within(screen.getByLabelText('ACTUAL 실적 기준월')).getAllByRole('option')).toHaveLength(13);
    expect(screen.getByLabelText('PLAN Excel 파일')).toHaveAttribute('accept', '.xlsx');
    expect(screen.getByLabelText('ACTUAL Excel 파일')).toHaveAttribute('accept', '.xlsx');
    expect(screen.getByRole('button', { name: 'P&L Reporting 표준 양식' })).toBeDisabled();
    expect(screen.getByText('검증 결과 대기')).toBeInTheDocument();
    expect(screen.getByTestId('plan-upload-status')).toHaveTextContent('파일 선택 대기');
    expect(screen.getByTestId('actual-upload-status')).toHaveTextContent('파일 선택 대기');
  });

  it('keeps blank year drafts blank and validates only on submit', () => {
    renderShell();
    const planYear = screen.getByLabelText('PLAN 기준연도') as HTMLInputElement;
    const actualYear = screen.getByLabelText('ACTUAL 기준연도') as HTMLInputElement;

    fireEvent.change(planYear, { target: { value: '2026' } });
    fireEvent.change(planYear, { target: { value: '' } });
    fireEvent.change(actualYear, { target: { value: '2026' } });
    fireEvent.change(actualYear, { target: { value: '' } });

    expect(planYear.value).toBe('');
    expect(actualYear.value).toBe('');
    expect(planYear.value).not.toBe('0');
    expect(actualYear.value).not.toBe('0');

    fireEvent.change(screen.getByLabelText('PLAN Excel 파일'), { target: { files: [xlsx('plan.xlsx')] } });
    fireEvent.click(screen.getByRole('button', { name: 'PLAN 업로드' }));
    expect(screen.getByRole('alert')).toHaveTextContent('기준연도는 2000~2200 사이의 4자리 숫자로 입력하세요.');
    expect(planYear.value).toBe('');
  });

  it('emits only reportingYear and File for PLAN without owning a network call', () => {
    const fetchMock = vi.fn();
    const onPlanSubmit = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    renderShell({ onPlanSubmit });
    const file = xlsx('plan-2026.xlsx');

    fireEvent.change(screen.getByLabelText('PLAN 기준연도'), { target: { value: '2026' } });
    fireEvent.change(screen.getByLabelText('PLAN Excel 파일'), { target: { files: [file] } });
    expect(screen.getByTestId('plan-upload-status')).toHaveTextContent('업로드 준비');
    fireEvent.click(screen.getByRole('button', { name: 'PLAN 업로드' }));

    expect(onPlanSubmit).toHaveBeenCalledTimes(1);
    expect(onPlanSubmit).toHaveBeenCalledWith({ reportingYear: 2026, file });
    expect(Object.keys(onPlanSubmit.mock.calls[0][0]).sort()).toEqual(['file', 'reportingYear']);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('requires an explicit month and emits year, month, and File for ACTUAL', () => {
    const onActualSubmit = vi.fn();
    renderShell({ onActualSubmit });
    const file = xlsx('actual-2026-05.xlsx');

    fireEvent.change(screen.getByLabelText('ACTUAL 기준연도'), { target: { value: '2026' } });
    fireEvent.change(screen.getByLabelText('ACTUAL Excel 파일'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: 'ACTUAL 업로드' }));
    expect(screen.getByRole('alert')).toHaveTextContent('실적 기준월을 1~12월 중에서 선택하세요.');
    expect(onActualSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('ACTUAL 실적 기준월'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'ACTUAL 업로드' }));
    expect(onActualSubmit).toHaveBeenCalledWith({ reportingYear: 2026, actualThroughMonth: 5, file });
    expect(Object.keys(onActualSubmit.mock.calls[0][0]).sort()).toEqual(['actualThroughMonth', 'file', 'reportingYear']);
  });

  it('exposes the template action only when both capability and callback are present', () => {
    const onTemplateDownload = vi.fn();
    const { rerender } = render(<PnlReportingUploadSection templateDownloadAvailable={false} onTemplateDownload={onTemplateDownload} />);
    const unavailable = screen.getByRole('button', { name: 'P&L Reporting 표준 양식' });
    expect(unavailable).toBeDisabled();
    fireEvent.click(unavailable);
    expect(onTemplateDownload).not.toHaveBeenCalled();

    rerender(<PnlReportingUploadSection templateDownloadAvailable onTemplateDownload={onTemplateDownload} />);
    fireEvent.click(screen.getByRole('button', { name: 'P&L Reporting 표준 양식' }));
    expect(onTemplateDownload).toHaveBeenCalledTimes(1);
  });

  it('disables duplicate submission controls while each parent-owned state is pending', () => {
    const onPlanSubmit = vi.fn();
    const onActualSubmit = vi.fn();
    const { rerender } = render(<PnlReportingUploadSection
      templateDownloadAvailable={false}
      onPlanSubmit={onPlanSubmit}
      onActualSubmit={onActualSubmit}
    />);
    fireEvent.change(screen.getByLabelText('PLAN Excel 파일'), { target: { files: [xlsx('plan.xlsx')] } });
    fireEvent.change(screen.getByLabelText('ACTUAL Excel 파일'), { target: { files: [xlsx('actual.xlsx')] } });

    rerender(<PnlReportingUploadSection
      templateDownloadAvailable={false}
      onPlanSubmit={onPlanSubmit}
      onActualSubmit={onActualSubmit}
      planState={{ status: 'PENDING' }}
      actualState={{ status: 'PENDING' }}
    />);

    expect(screen.getByRole('button', { name: 'PLAN 처리 중…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'ACTUAL 처리 중…' })).toBeDisabled();
    expect(screen.getByLabelText('PLAN 기준연도')).toBeDisabled();
    expect(screen.getByLabelText('ACTUAL 실적 기준월')).toBeDisabled();
    expect(screen.getByTestId('plan-upload-status')).toHaveTextContent('업로드 처리 중');
    expect(screen.getByTestId('actual-upload-status')).toHaveTextContent('업로드 처리 중');
    fireEvent.click(screen.getByRole('button', { name: 'PLAN 처리 중…' }));
    fireEvent.click(screen.getByRole('button', { name: 'ACTUAL 처리 중…' }));
    expect(onPlanSubmit).not.toHaveBeenCalled();
    expect(onActualSubmit).not.toHaveBeenCalled();
  });

  it('renders invalid, success, and error states supplied by its parent', () => {
    renderShell({
      planState: { status: 'SUCCESS', reportingYear: 2026, registeredAt: '2026-08-19T04:30:00Z', replacedExisting: true, warningCount: 1 },
      actualState: { status: 'ERROR', message: 'ACTUAL 등록 중 오류가 발생했습니다.' },
      validationSummary: {
        status: 'INVALID',
        errorCount: 3,
        warningCount: 1,
        truncated: true,
        errors: [
          { severity: 'ERROR', errorCode: 'VALUE_REQUIRED', sheet: '03_판관비상세', displayLabel: '1. 인건비', month: 5, message: '실적 기준월 이내의 값은 비워둘 수 없습니다.' },
          { severity: 'ERROR', errorCode: 'VALUE_REQUIRED', sheet: '03_판관비상세', displayLabel: '2. 복리후생비', month: 5, message: '필수 값을 입력하세요.' },
        ],
        warnings: [{ severity: 'WARNING', errorCode: 'ROUNDING', sheet: '01_손익계산서', rowKey: 'gross_profit', message: '합계와 세부 항목에 반올림 차이가 있습니다.' }],
      },
      validationIssueLimit: 2,
    });

    expect(screen.getByTestId('plan-upload-status')).toHaveTextContent('PLAN 등록 완료');
    expect(screen.getByTestId('plan-upload-status')).toHaveTextContent('기존 데이터 교체');
    expect(screen.getByTestId('actual-upload-status')).toHaveTextContent('ACTUAL 등록 중 오류가 발생했습니다.');
    expect(screen.getByLabelText('오류 3건, 경고 1건')).toBeInTheDocument();
    expect(screen.getByText('03_판관비상세 / 5월 · 1. 인건비')).toBeInTheDocument();
    expect(screen.getByText('실적 기준월 이내의 값은 비워둘 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByText(/상위 2개 표시 · 추가 2건 · 전체 목록은 일부 생략됨/)).toBeInTheDocument();
  });

  it('clears a stale parent result when the user selects or removes a replacement file', () => {
    renderShell({
      planState: { status: 'SUCCESS', message: '이전 PLAN 등록 완료' },
      actualState: { status: 'ERROR', message: '이전 ACTUAL 등록 오류' },
    });

    fireEvent.change(screen.getByLabelText('PLAN Excel 파일'), { target: { files: [xlsx('replacement-plan.xlsx')] } });
    fireEvent.change(screen.getByLabelText('ACTUAL Excel 파일'), { target: { files: [xlsx('replacement-actual.xlsx')] } });
    expect(screen.getByTestId('plan-upload-status')).toHaveTextContent('업로드 준비');
    expect(screen.getByTestId('plan-upload-status')).not.toHaveTextContent('이전 PLAN 등록 완료');
    expect(screen.getByTestId('actual-upload-status')).toHaveTextContent('업로드 준비');
    expect(screen.getByTestId('actual-upload-status')).not.toHaveTextContent('이전 ACTUAL 등록 오류');

    fireEvent.click(screen.getByRole('button', { name: 'PLAN 선택 파일 해제' }));
    expect(screen.getByTestId('plan-upload-status')).toHaveTextContent('파일 선택 대기');
  });

  it('supports existing-dataset replacement notices without delete or preview workflows', () => {
    renderShell({
      existingPlan: { reportingYear: 2026, registeredAt: '2026-08-18T09:00:00Z' },
      existingActual: { reportingYear: 2026, actualThroughMonth: 5 },
    });

    expect(screen.getByText(/2026년 PLAN/).closest('[role="note"]')).toHaveTextContent('기존 데이터를 교체합니다');
    expect(screen.getByText(/2026년 ACTUAL/).closest('[role="note"]')).toHaveTextContent('5월 기준');
    expect(screen.queryByRole('button', { name: /삭제|초기화|제거/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/행 미리보기|워크북 미리보기|수식 미리보기/)).not.toBeInTheDocument();
  });

  it('rejects non-xlsx selections locally without fetch, persistence, or a fake result', () => {
    const fetchMock = vi.fn();
    const onPlanSubmit = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    renderShell({ onPlanSubmit });

    fireEvent.change(screen.getByLabelText('PLAN Excel 파일'), {
      target: { files: [new File(['legacy'], 'legacy.xls')] },
    });

    expect(screen.getByTestId('plan-upload-status')).toHaveTextContent('.xlsx 파일만 선택할 수 있습니다.');
    expect(screen.getByRole('button', { name: 'PLAN 업로드' })).toBeDisabled();
    expect(onPlanSubmit).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(window.localStorage.length).toBe(0);
  });

  it('stays outside the production graph and contains no API, fake async, persistence, parser, or business-formula path', () => {
    const appSource = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8');
    const managementSource = readFileSync(resolve(process.cwd(), 'src/integration/ModelManagementView.tsx'), 'utf8');
    const pnlSource = readFileSync(resolve(process.cwd(), 'src/views/PnlStatusView.tsx'), 'utf8');
    const componentSource = readFileSync(resolve(process.cwd(), 'src/integration/management/PnlReportingUploadSection.tsx'), 'utf8');

    expect(`${appSource}\n${managementSource}\n${pnlSource}`).not.toContain('PnlReportingUploadSection');
    expect(componentSource).not.toMatch(/bffClient|fetch\s*\(|\/api\/(admin|viewer)\/pnl-reporting/i);
    expect(componentSource).not.toMatch(/\bsupabase\b|\bstorage\b|\blocalStorage\b|\bsessionStorage\b|from\s+['"][^'"]*parser/i);
    expect(componentSource).not.toMatch(/setTimeout|Promise\.resolve|new Promise/i);
    expect(componentSource).not.toMatch(/actual\s*[-/]\s*plan|achievement|margin|ytd|workbook preview/i);
  });
});
