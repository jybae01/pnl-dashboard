import { FormEvent, useId, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  Info,
  LoaderCircle,
  UploadCloud,
  X,
} from 'lucide-react';
import '../../styles/pnl-reporting-upload.css';

export type PnlReportingUploadStatus =
  | 'IDLE'
  | 'FILE_SELECTED'
  | 'PENDING'
  | 'INVALID'
  | 'SUCCESS'
  | 'ERROR';

export interface PnlReportingUploadPresentation {
  status: PnlReportingUploadStatus;
  message?: string;
  reportingYear?: number;
  actualThroughMonth?: number;
  registeredAt?: string;
  replacedExisting?: boolean;
  warningCount?: number;
}

export interface PnlReportingValidationIssue {
  severity: 'ERROR' | 'WARNING';
  errorCode?: string;
  sheet?: string;
  rowKey?: string;
  displayLabel?: string;
  month?: number;
  field?: string;
  message: string;
}

export interface PnlReportingValidationSummary {
  status: 'VALID' | 'INVALID' | 'ERROR';
  errorCount: number;
  warningCount: number;
  truncated: boolean;
  errors: PnlReportingValidationIssue[];
  warnings: PnlReportingValidationIssue[];
}

export interface PnlReportingExistingDatasetSummary {
  reportingYear: number;
  actualThroughMonth?: number;
  registeredAt?: string;
}

export interface PnlReportingPlanSubmitPayload {
  reportingYear: number;
  file: File;
}

export interface PnlReportingActualSubmitPayload extends PnlReportingPlanSubmitPayload {
  actualThroughMonth: number;
}

export interface PnlReportingUploadSectionProps {
  templateDownloadAvailable: boolean;
  onTemplateDownload?: () => void;
  onPlanSubmit?: (payload: PnlReportingPlanSubmitPayload) => void;
  onActualSubmit?: (payload: PnlReportingActualSubmitPayload) => void;
  planState?: PnlReportingUploadPresentation;
  actualState?: PnlReportingUploadPresentation;
  validationSummary?: PnlReportingValidationSummary | null;
  existingPlan?: PnlReportingExistingDatasetSummary | null;
  existingActual?: PnlReportingExistingDatasetSummary | null;
  validationIssueLimit?: number;
}

type DatasetKind = 'PLAN' | 'ACTUAL';

const IDLE_STATE: PnlReportingUploadPresentation = { status: 'IDLE' };

function isXlsxFile(file: File): boolean {
  return /\.xlsx$/i.test(file.name);
}

function parseReportingYear(draft: string): number | null {
  const normalized = draft.trim();
  if (!/^\d{4}$/.test(normalized)) return null;
  const year = Number(normalized);
  return year >= 2000 && year <= 2200 ? year : null;
}

function fileSizeLabel(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function dateTimeLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

function selectedStatus(
  state: PnlReportingUploadPresentation,
  file: File | null,
  localError: string | null,
  selectionChanged: boolean,
): PnlReportingUploadPresentation {
  if (localError) return { status: 'INVALID', message: localError };
  if (state.status === 'PENDING') return state;
  if (selectionChanged) return file ? { status: 'FILE_SELECTED' } : IDLE_STATE;
  if (state.status === 'IDLE' && file) return { status: 'FILE_SELECTED' };
  return state;
}

function FileSelector({
  kind,
  file,
  disabled,
  onFileChange,
}: {
  kind: DatasetKind;
  file: File | null;
  disabled: boolean;
  onFileChange: (file: File | null) => void;
}) {
  const [isDragging, setIsDragging] = useState(false);
  const inputId = useId();

  return <div
    className={`pnl-reporting-upload__file-field ${isDragging ? 'is-dragging' : ''} ${disabled ? 'is-disabled' : ''}`}
    onDragOver={(event) => {
      event.preventDefault();
      if (!disabled) setIsDragging(true);
    }}
    onDragLeave={() => setIsDragging(false)}
    onDrop={(event) => {
      event.preventDefault();
      setIsDragging(false);
      if (!disabled) onFileChange(event.dataTransfer.files?.[0] || null);
    }}
  >
    <label
      className="pnl-reporting-upload__dropzone"
      htmlFor={inputId}
      aria-disabled={disabled}
    >
      <input
        id={inputId}
        aria-label={`${kind} Excel 파일`}
        type="file"
        accept=".xlsx"
        disabled={disabled}
        onChange={(event) => {
          const nextFile = event.currentTarget.files?.[0] || null;
          onFileChange(nextFile);
          event.currentTarget.value = '';
        }}
      />
      <FileSpreadsheet size={25} aria-hidden="true" />
      <span className="pnl-reporting-upload__file-copy">
        <strong>{file ? file.name : 'Excel 파일을 선택하거나 끌어 놓으세요.'}</strong>
        <small>{file ? fileSizeLabel(file.size) : '.xlsx 형식만 지원합니다.'}</small>
      </span>
    </label>
    {file && !disabled && <button
      type="button"
      className="pnl-reporting-upload__remove-file"
      aria-label={`${kind} 선택 파일 해제`}
      onClick={() => onFileChange(null)}
    ><X size={13} aria-hidden="true" /> 파일 선택 해제</button>}
  </div>;
}

function ExistingDatasetNotice({
  kind,
  dataset,
}: {
  kind: DatasetKind;
  dataset: PnlReportingExistingDatasetSummary;
}) {
  return <div className="pnl-reporting-upload__replacement" role="note">
    <Info size={14} aria-hidden="true" />
    <span>
      <strong>{dataset.reportingYear}년 {kind}</strong>
      {kind === 'ACTUAL' && dataset.actualThroughMonth ? ` · ${dataset.actualThroughMonth}월 기준` : ''} 데이터가 등록되어 있습니다.
      {' '}새 파일 등록 시 기존 데이터를 교체합니다.
      {dataset.registeredAt && <small> 기존 등록 {dateTimeLabel(dataset.registeredAt)}</small>}
    </span>
  </div>;
}

function UploadStatus({
  kind,
  state,
}: {
  kind: DatasetKind;
  state: PnlReportingUploadPresentation;
}) {
  const isProblem = state.status === 'INVALID' || state.status === 'ERROR';
  const defaultMessage: Record<PnlReportingUploadStatus, string> = {
    IDLE: '파일 선택 대기',
    FILE_SELECTED: '업로드 준비',
    PENDING: '업로드 처리 중',
    INVALID: '입력값과 검증 결과를 확인하세요.',
    SUCCESS: `${kind} 등록 완료`,
    ERROR: '업로드를 완료하지 못했습니다.',
  };
  const Icon = state.status === 'PENDING'
    ? LoaderCircle
    : state.status === 'SUCCESS'
      ? CheckCircle2
      : isProblem
        ? AlertCircle
        : Info;

  return <div
    className={`pnl-reporting-upload__status is-${state.status.toLowerCase()}`}
    role={isProblem ? 'alert' : 'status'}
    aria-live="polite"
    data-testid={`${kind.toLowerCase()}-upload-status`}
  >
    <Icon size={14} aria-hidden="true" />
    <div>
      <strong>{state.message || defaultMessage[state.status]}</strong>
      {state.status === 'SUCCESS' && <dl className="pnl-reporting-upload__success-details">
        {state.reportingYear !== undefined && <div><dt>기준연도</dt><dd>{state.reportingYear}년</dd></div>}
        {state.actualThroughMonth !== undefined && <div><dt>실적 기준월</dt><dd>{state.actualThroughMonth}월</dd></div>}
        {state.registeredAt && <div><dt>등록 일시</dt><dd>{dateTimeLabel(state.registeredAt)}</dd></div>}
        {state.replacedExisting !== undefined && <div><dt>처리</dt><dd>{state.replacedExisting ? '기존 데이터 교체' : '신규 등록'}</dd></div>}
        {state.warningCount !== undefined && <div><dt>경고</dt><dd>{state.warningCount}건</dd></div>}
      </dl>}
    </div>
  </div>;
}

function ValidationSummary({
  summary,
  issueLimit,
}: {
  summary?: PnlReportingValidationSummary | null;
  issueLimit: number;
}) {
  const headingId = useId();
  if (!summary) {
    return <section className="pnl-reporting-upload__validation" aria-labelledby={headingId}>
      <div className="pnl-reporting-upload__validation-heading">
        <div><Info size={16} aria-hidden="true" /><h3 id={headingId}>Validation Summary</h3></div>
        <span className="pnl-reporting-upload__validation-empty">검증 결과 대기</span>
      </div>
      <p className="pnl-reporting-upload__validation-placeholder">업로드 검증 결과가 전달되면 오류와 경고를 여기에 표시합니다.</p>
    </section>;
  }

  const limit = Math.max(1, issueLimit);
  const issues = [...summary.errors, ...summary.warnings].slice(0, limit);
  const undisplayedCount = Math.max(0, summary.errorCount + summary.warningCount - issues.length);

  return <section className={`pnl-reporting-upload__validation is-${summary.status.toLowerCase()}`} aria-labelledby={headingId}>
    <div className="pnl-reporting-upload__validation-heading">
      <div><AlertCircle size={16} aria-hidden="true" /><h3 id={headingId}>Validation Summary</h3></div>
      <div className="pnl-reporting-upload__validation-counts" aria-label={`오류 ${summary.errorCount}건, 경고 ${summary.warningCount}건`}>
        <span className="is-error">오류 {summary.errorCount}건</span>
        <span className="is-warning">경고 {summary.warningCount}건</span>
      </div>
    </div>
    {issues.length > 0 ? <ul className="pnl-reporting-upload__issues">
      {issues.map((issue, index) => {
        const location = [issue.month ? `${issue.month}월` : null, issue.displayLabel, issue.field].filter(Boolean).join(' · ');
        return <li key={`${issue.severity}-${issue.errorCode || 'issue'}-${issue.sheet || 'sheet'}-${issue.rowKey || index}-${index}`} className={`is-${issue.severity.toLowerCase()}`}>
          <span className="pnl-reporting-upload__issue-severity">{issue.severity === 'ERROR' ? '오류' : '경고'}</span>
          <div>
            {(issue.sheet || location) && <strong>{[issue.sheet, location].filter(Boolean).join(' / ')}</strong>}
            <p>{issue.message}</p>
          </div>
        </li>;
      })}
    </ul> : <p className="pnl-reporting-upload__validation-placeholder">표시할 검증 항목이 없습니다.</p>}
    {(undisplayedCount > 0 || summary.truncated) && <p className="pnl-reporting-upload__more-issues">
      상위 {issues.length}개 표시{undisplayedCount > 0 ? ` · 추가 ${undisplayedCount}건` : ''}{summary.truncated ? ' · 전체 목록은 일부 생략됨' : ''}
    </p>}
  </section>;
}

export function PnlReportingUploadSection({
  templateDownloadAvailable,
  onTemplateDownload,
  onPlanSubmit,
  onActualSubmit,
  planState = IDLE_STATE,
  actualState = IDLE_STATE,
  validationSummary,
  existingPlan,
  existingActual,
  validationIssueLimit = 6,
}: PnlReportingUploadSectionProps) {
  const [planYearDraft, setPlanYearDraft] = useState('');
  const [actualYearDraft, setActualYearDraft] = useState('');
  const [actualThroughMonthDraft, setActualThroughMonthDraft] = useState('');
  const [planFile, setPlanFile] = useState<File | null>(null);
  const [actualFile, setActualFile] = useState<File | null>(null);
  const [planSelectionChanged, setPlanSelectionChanged] = useState(false);
  const [actualSelectionChanged, setActualSelectionChanged] = useState(false);
  const [planLocalError, setPlanLocalError] = useState<string | null>(null);
  const [actualLocalError, setActualLocalError] = useState<string | null>(null);
  const sectionHeadingId = useId();
  const planHeadingId = useId();
  const actualHeadingId = useId();
  const planBusy = planState.status === 'PENDING';
  const actualBusy = actualState.status === 'PENDING';

  function chooseFile(kind: DatasetKind, file: File | null) {
    const setFile = kind === 'PLAN' ? setPlanFile : setActualFile;
    const setError = kind === 'PLAN' ? setPlanLocalError : setActualLocalError;
    const setSelectionChanged = kind === 'PLAN' ? setPlanSelectionChanged : setActualSelectionChanged;
    setSelectionChanged(true);
    if (file && !isXlsxFile(file)) {
      setFile(null);
      setError('.xlsx 파일만 선택할 수 있습니다.');
      return;
    }
    setFile(file);
    setError(null);
  }

  function submitPlan(event: FormEvent) {
    event.preventDefault();
    if (planBusy) return;
    const reportingYear = parseReportingYear(planYearDraft);
    if (reportingYear === null) {
      setPlanLocalError('기준연도는 2000~2200 사이의 4자리 숫자로 입력하세요.');
      return;
    }
    if (!planFile) {
      setPlanLocalError('업로드할 .xlsx 파일을 선택하세요.');
      return;
    }
    setPlanLocalError(null);
    setPlanSelectionChanged(false);
    onPlanSubmit?.({ reportingYear, file: planFile });
  }

  function submitActual(event: FormEvent) {
    event.preventDefault();
    if (actualBusy) return;
    const reportingYear = parseReportingYear(actualYearDraft);
    if (reportingYear === null) {
      setActualLocalError('기준연도는 2000~2200 사이의 4자리 숫자로 입력하세요.');
      return;
    }
    const actualThroughMonth = Number(actualThroughMonthDraft);
    if (!Number.isInteger(actualThroughMonth) || actualThroughMonth < 1 || actualThroughMonth > 12) {
      setActualLocalError('실적 기준월을 1~12월 중에서 선택하세요.');
      return;
    }
    if (!actualFile) {
      setActualLocalError('업로드할 .xlsx 파일을 선택하세요.');
      return;
    }
    setActualLocalError(null);
    setActualSelectionChanged(false);
    onActualSubmit?.({ reportingYear, actualThroughMonth, file: actualFile });
  }

  const templateEnabled = templateDownloadAvailable && Boolean(onTemplateDownload);
  const visiblePlanState = selectedStatus(planState, planFile, planLocalError, planSelectionChanged);
  const visibleActualState = selectedStatus(actualState, actualFile, actualLocalError, actualSelectionChanged);

  return <section className="pnl-reporting-upload" aria-labelledby={sectionHeadingId}>
    <header className="pnl-reporting-upload__header">
      <div>
        <p className="pnl-reporting-upload__eyebrow">P&amp;L REPORTING</p>
        <h2 id={sectionHeadingId}><UploadCloud size={17} aria-hidden="true" />P&amp;L Reporting Data</h2>
        <p>표준 양식으로 PLAN과 ACTUAL 데이터를 등록합니다.</p>
      </div>
      <button
        type="button"
        className="pnl-reporting-upload__template-action"
        disabled={!templateEnabled}
        title={!templateEnabled ? '표준 양식 다운로드는 연동 후 제공됩니다.' : undefined}
        onClick={onTemplateDownload}
      ><Download size={14} aria-hidden="true" />P&amp;L Reporting 표준 양식</button>
    </header>

    <div className="pnl-reporting-upload__blocks">
      <form className="pnl-reporting-upload__block is-plan" onSubmit={submitPlan} noValidate aria-labelledby={planHeadingId} aria-busy={planBusy}>
        <div className="pnl-reporting-upload__block-heading">
          <div><span>PLAN</span><h3 id={planHeadingId}>계획 데이터 등록</h3></div>
          <small>연간 계획</small>
        </div>
        {existingPlan && <ExistingDatasetNotice kind="PLAN" dataset={existingPlan} />}
        <label className="pnl-reporting-upload__control">
          <span>기준연도</span>
          <input
            aria-label="PLAN 기준연도"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            placeholder="예: 2026"
            value={planYearDraft}
            disabled={planBusy}
            onChange={(event) => { setPlanYearDraft(event.target.value); setPlanLocalError(null); }}
          />
        </label>
        <FileSelector kind="PLAN" file={planFile} disabled={planBusy} onFileChange={(file) => chooseFile('PLAN', file)} />
        <div className="pnl-reporting-upload__actions">
          <UploadStatus kind="PLAN" state={visiblePlanState} />
          <button type="submit" className="pnl-reporting-upload__submit" disabled={planBusy || !planFile || !onPlanSubmit}>
            {planBusy ? 'PLAN 처리 중…' : 'PLAN 업로드'}
          </button>
        </div>
      </form>

      <form className="pnl-reporting-upload__block is-actual" onSubmit={submitActual} noValidate aria-labelledby={actualHeadingId} aria-busy={actualBusy}>
        <div className="pnl-reporting-upload__block-heading">
          <div><span>ACTUAL</span><h3 id={actualHeadingId}>실적 데이터 등록</h3></div>
          <small>누적 실적</small>
        </div>
        {existingActual && <ExistingDatasetNotice kind="ACTUAL" dataset={existingActual} />}
        <div className="pnl-reporting-upload__actual-controls">
          <label className="pnl-reporting-upload__control">
            <span>기준연도</span>
            <input
              aria-label="ACTUAL 기준연도"
              type="text"
              inputMode="numeric"
              autoComplete="off"
              placeholder="예: 2026"
              value={actualYearDraft}
              disabled={actualBusy}
              onChange={(event) => { setActualYearDraft(event.target.value); setActualLocalError(null); }}
            />
          </label>
          <label className="pnl-reporting-upload__control">
            <span>실적 기준월</span>
            <select
              aria-label="ACTUAL 실적 기준월"
              value={actualThroughMonthDraft}
              disabled={actualBusy}
              onChange={(event) => { setActualThroughMonthDraft(event.target.value); setActualLocalError(null); }}
            >
              <option value="">월 선택</option>
              {Array.from({ length: 12 }, (_, index) => index + 1).map((month) => <option key={month} value={month}>{month}월</option>)}
            </select>
          </label>
        </div>
        <FileSelector kind="ACTUAL" file={actualFile} disabled={actualBusy} onFileChange={(file) => chooseFile('ACTUAL', file)} />
        <div className="pnl-reporting-upload__actions">
          <UploadStatus kind="ACTUAL" state={visibleActualState} />
          <button type="submit" className="pnl-reporting-upload__submit" disabled={actualBusy || !actualFile || !onActualSubmit}>
            {actualBusy ? 'ACTUAL 처리 중…' : 'ACTUAL 업로드'}
          </button>
        </div>
      </form>
    </div>

    <ValidationSummary summary={validationSummary} issueLimit={validationIssueLimit} />
  </section>;
}
