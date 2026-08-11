import React, { useState, useEffect } from 'react';
import { Modal } from '../common/Modal';
import { DataModelItem, CalculationJob } from '../../types/model';
import { calculationService } from '../../services';
import { Sparkles, CheckCircle2, AlertCircle, XCircle, ArrowRight, Play, RefreshCw, ShieldAlert, FileSpreadsheet, Download } from 'lucide-react';

interface CalculationRunnerModalProps {
  isOpen: boolean;
  onClose: () => void;
  models: DataModelItem[];
  defaultBaselineId?: string;
  defaultComparisonId?: string;
  onGoToVarianceView: () => void;
}

export const CalculationRunnerModal: React.FC<CalculationRunnerModalProps> = ({
  isOpen,
  onClose,
  models,
  defaultBaselineId,
  defaultComparisonId,
  onGoToVarianceView,
}) => {
  const [baselineId, setBaselineId] = useState<string>(defaultBaselineId || (models[0]?.id ?? ''));
  const [comparisonId, setComparisonId] = useState<string>(defaultComparisonId || (models[1]?.id ?? ''));
  const [simulateError, setSimulateError] = useState<boolean>(false);

  const [job, setJob] = useState<CalculationJob | null>(null);
  const [timerId, setTimerId] = useState<any>(null);
  const [excelDownloadNotice, setExcelDownloadNotice] = useState<string | null>(null);

  useEffect(() => {
    if (defaultBaselineId) setBaselineId(defaultBaselineId);
    else if (!baselineId && models.length > 0) setBaselineId(models[0].id);

    if (defaultComparisonId) setComparisonId(defaultComparisonId);
    else if (!comparisonId && models.length > 1) setComparisonId(models[1].id);
  }, [defaultBaselineId, defaultComparisonId, models]);

  useEffect(() => {
    return () => {
      if (timerId) clearInterval(timerId);
    };
  }, [timerId]);

  // Validation logic
  const isSameModel = baselineId === comparisonId && baselineId !== '';
  const isMissingModel = !baselineId || !comparisonId;
  let validationError: string | null = null;
  if (isMissingModel) {
    validationError = '[모형 미선택] 기준 모형과 비교 모형을 모두 선택해야 분석 계산을 실행할 수 있습니다.';
  } else if (isSameModel) {
    validationError = '[모형 선택 오류] 기준 모형과 비교 모형이 동일합니다. 서로 다른 두 모형을 선택하십시오.';
  }

  const isExecutionDisabled = !!validationError || (job !== null && (job.status === 'PENDING' || job.status === 'PROCESSING'));

  const handleStartCalculation = async () => {
    if (validationError) return;

    setExcelDownloadNotice(null);
    // 1. Create Job in PENDING state
    const newJob = await calculationService.startJob(baselineId, comparisonId, simulateError);
    setJob(newJob);

    let currentStep = 0;
    const stagesCount = newJob.stages.length;

    // Simulate multi-stage progress
    const interval = setInterval(() => {
      currentStep++;

      if (simulateError && currentStep === 2) {
        clearInterval(interval);
        calculationService.updateJobProgress(
          newJob.id,
          'FAILED',
          25,
          0,
          'ERROR',
          {
            code: 'INPUT_INTEGRITY_MISMATCH',
            message: '입력 파일 무결성 오류 (INPUT_INTEGRITY_MISMATCH)',
            detail: '계산 Job에 고정된 파일의 SHA256 해시와 실제 처리 대상 파일의 SHA256이 일치하지 않습니다. (다른 버전의 파일이거나 재업로드된 파일일 수 있습니다.)'
          }
        );
        calculationService.getJobStatus(newJob.id).then(j => setJob(j));
        return;
      }

      if (currentStep <= stagesCount) {
        const stageIndex = currentStep - 1;
        const progress = Math.min(Math.round((currentStep / stagesCount) * 100), 95);

        if (stageIndex > 0) {
          calculationService.updateJobProgress(newJob.id, 'PROCESSING', progress, stageIndex - 1, 'COMPLETED');
        }
        calculationService.updateJobProgress(newJob.id, 'PROCESSING', progress, stageIndex, 'ACTIVE');
        calculationService.getJobStatus(newJob.id).then(j => setJob(j));
      } else {
        // Complete Job
        clearInterval(interval);
        calculationService.updateJobProgress(newJob.id, 'COMPLETED', 100, stagesCount - 1, 'COMPLETED');
        calculationService.getJobStatus(newJob.id).then(j => setJob(j));
      }
    }, 600);

    setTimerId(interval);
  };

  const handleReset = () => {
    if (timerId) clearInterval(timerId);
    setJob(null);
    setExcelDownloadNotice(null);
  };

  const handleCompleteAndNavigate = () => {
    onClose();
    onGoToVarianceView();
  };

  const handleDownloadExcel = () => {
    setExcelDownloadNotice('분석 근거 엑셀 생성 기능은 기존 실제 프로젝트 PR 모듈과 연결됩니다. (UI 연계 완료)');
  };

  const baselineOptions = models.filter(m => m.isBaselineEligible || m.modelType === 'PLAN');
  const comparisonOptions = models; // Allow comparison across any models

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Sparkles size={16} color="#2563eb" />
          손익 분석 계산 시뮬레이터 (Variance Engine Runner)
        </div>
      }
      maxWidth="740px"
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
          <div>
            {job && (
              <button className="btn btn-secondary btn-sm" onClick={handleReset}>
                <RefreshCw size={12} /> 설정 초기화
              </button>
            )}
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button className="btn btn-secondary" onClick={onClose}>
              닫기
            </button>

            {(!job || job.status === 'IDLE') && (
              <button
                className="btn btn-primary"
                onClick={handleStartCalculation}
                disabled={isExecutionDisabled}
                style={{ opacity: isExecutionDisabled ? 0.5 : 1, cursor: isExecutionDisabled ? 'not-allowed' : 'pointer' }}
              >
                <Play size={13} />
                손익 분석 실행
              </button>
            )}

            {job && job.status === 'COMPLETED' && (
              <>
                <button
                  className="btn btn-secondary"
                  style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#0f766e', borderColor: '#99f6e4' }}
                  onClick={handleDownloadExcel}
                  title="분석 근거 엑셀 내려받기"
                >
                  <Download size={13} />
                  분석 근거 엑셀 내려받기
                </button>
                <button className="btn btn-primary" onClick={handleCompleteAndNavigate}>
                  분석 결과 보기
                  <ArrowRight size={13} />
                </button>
              </>
            )}

            {job && job.status === 'FAILED' && (
              <button className="btn btn-primary" onClick={handleStartCalculation}>
                <RefreshCw size={13} /> 재실행 (Retry)
              </button>
            )}
          </div>
        </div>
      }
    >
      <div>
        {/* Model Selection Row */}
        <div style={{
          backgroundColor: '#f8fafc',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 16px',
          marginBottom: 16
        }}>
          <div style={{ fontSize: '12px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 10 }}>
            1. 비교 분석 대상 모형 확인 및 선택
          </div>

          <div className="grid-2col" style={{ gap: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
                기준 모형:
              </label>
              <select
                className="filter-select"
                style={{ width: '100%', borderColor: validationError && isSameModel ? '#ef4444' : undefined }}
                value={baselineId}
                onChange={(e) => setBaselineId(e.target.value)}
                disabled={job !== null && (job.status === 'PENDING' || job.status === 'PROCESSING')}
              >
                <option value="">-- 기준 모형 선택 --</option>
                {baselineOptions.map(m => (
                  <option key={`base-${m.id}`} value={m.id}>
                    [{m.modelType}] {m.modelName} ({m.baseMonth})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>
                비교 모형:
              </label>
              <select
                className="filter-select"
                style={{ width: '100%', borderColor: validationError && isSameModel ? '#ef4444' : undefined }}
                value={comparisonId}
                onChange={(e) => setComparisonId(e.target.value)}
                disabled={job !== null && (job.status === 'PENDING' || job.status === 'PROCESSING')}
              >
                <option value="">-- 비교 모형 선택 --</option>
                {comparisonOptions.map(m => (
                  <option key={`comp-${m.id}`} value={m.id}>
                    [{m.modelType}] {m.modelName} ({m.baseMonth})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Validation Error Banner */}
          {validationError && (
            <div style={{
              marginTop: 10,
              padding: '6px 10px',
              backgroundColor: '#fef2f2',
              border: '1px solid #fca5a5',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '11.5px',
              color: '#b91c1c',
              fontWeight: 600
            }}>
              <AlertCircle size={14} color="#dc2626" />
              <span>{validationError}</span>
            </div>
          )}

          {/* Error Simulation Toggle */}
          <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, fontSize: '11.5px', borderTop: '1px dashed var(--border-subtle)', paddingTop: 10 }}>
            <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>시뮬레이션 모드:</span>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
              <input
                type="radio"
                name="simMode"
                checked={!simulateError}
                onChange={() => setSimulateError(false)}
                disabled={job !== null && (job.status === 'PENDING' || job.status === 'PROCESSING')}
              />
              정상 계산 완료 (Happy Path)
            </label>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, cursor: 'pointer', marginLeft: 12 }}>
              <input
                type="radio"
                name="simMode"
                checked={simulateError}
                onChange={() => setSimulateError(true)}
                disabled={job !== null && (job.status === 'PENDING' || job.status === 'PROCESSING')}
              />
              <span style={{ color: 'var(--color-unfavorable)', fontWeight: 600 }}>
                SHA256 무결성 오류 시뮬레이션 (INPUT_INTEGRITY_MISMATCH)
              </span>
            </label>
          </div>
        </div>

        {/* Excel Download Notice */}
        {excelDownloadNotice && (
          <div style={{
            marginBottom: 12,
            padding: '8px 12px',
            backgroundColor: '#f0fdf4',
            border: '1px solid #86efac',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: '11.5px',
            color: '#15803d',
            fontWeight: 600
          }}>
            <FileSpreadsheet size={15} color="#16a34a" />
            <span>{excelDownloadNotice}</span>
          </div>
        )}

        {/* Calculation Execution Progress */}
        {job ? (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div style={{ fontSize: '12px', fontWeight: 700 }}>
                2. 엔진 연산 진행 상태
              </div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#2563eb' }}>
                {job.progressPercent}% 완료
              </div>
            </div>

            {/* Progress Bar */}
            <div style={{ width: '100%', height: 6, backgroundColor: '#e2e8f0', borderRadius: 3, overflow: 'hidden', marginBottom: 14 }}>
              <div
                style={{
                  width: `${job.progressPercent}%`,
                  height: '100%',
                  backgroundColor: job.status === 'FAILED' ? '#ef4444' : job.status === 'COMPLETED' ? '#10b981' : '#2563eb',
                  transition: 'width 0.4s ease'
                }}
              />
            </div>

            {/* Step Stepper */}
            <div className="calc-stepper">
              {job.stages.map((stage, idx) => {
                let statusClass = 'waiting';
                if (stage.status === 'COMPLETED') statusClass = 'completed';
                else if (stage.status === 'ACTIVE') statusClass = 'active';
                else if (stage.status === 'ERROR') statusClass = 'error';

                return (
                  <div key={stage.id} className={`calc-step-item ${statusClass}`}>
                    <div className="calc-step-icon">
                      {stage.status === 'COMPLETED' ? (
                        <CheckCircle2 size={14} />
                      ) : stage.status === 'ERROR' ? (
                        <XCircle size={14} />
                      ) : stage.status === 'ACTIVE' ? (
                        <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
                      ) : (
                        idx + 1
                      )}
                    </div>
                    <div className="calc-step-content">
                      <div className="calc-step-title">{stage.title}</div>
                      <div className="calc-step-detail">{stage.detail}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Success Result Box with Action Buttons */}
            {job.status === 'COMPLETED' && (
              <div style={{
                marginTop: 14,
                backgroundColor: '#ecfdf5',
                border: '1px solid #a7f3d0',
                borderRadius: 'var(--radius-sm)',
                padding: '12px 14px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 8
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#047857', fontSize: '12px', fontWeight: 700 }}>
                  <CheckCircle2 size={16} />
                  <span>입력 파일 SHA256 무결성 검증 통과 및 손익 Effect 분해 계산이 완료되었습니다.</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ color: '#0f766e', borderColor: '#99f6e4', display: 'flex', alignItems: 'center', gap: 4 }}
                    onClick={handleDownloadExcel}
                  >
                    <Download size={12} />
                    분석 근거 엑셀 내려받기
                  </button>
                  <button className="btn btn-primary btn-sm" onClick={handleCompleteAndNavigate}>
                    분석 결과 보기
                  </button>
                </div>
              </div>
            )}

            {/* Failed Error Box */}
            {job.status === 'FAILED' && (
              <div style={{
                marginTop: 14,
                backgroundColor: '#fef2f2',
                border: '1px solid #fca5a5',
                borderRadius: 'var(--radius-sm)',
                padding: '12px 14px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#b91c1c', fontSize: '13px', fontWeight: 800, marginBottom: 4 }}>
                  <ShieldAlert size={16} />
                  {job.errorMessage}
                </div>
                <div style={{ fontSize: '11.5px', color: '#7f1d1d', lineHeight: 1.5, marginBottom: 8 }}>
                  {job.errorDetail}
                </div>
                <div style={{ fontSize: '11px', color: '#991b1b', backgroundColor: '#fee2e2', padding: '6px 8px', borderRadius: 4 }}>
                  <strong>조치 가이드:</strong> 계산 Job 생성 시 지정된 원본 workbook 파일이 맞는지 확인하십시오. 파일이 업데이트되었거나 재업로드된 경우, 새 모형 버전으로 작업을 생성하여 실행하십시오.
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={{
            padding: '24px 16px',
            textAlign: 'center',
            backgroundColor: '#f8fafc',
            border: '1px dashed var(--border-default)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '12px',
            color: 'var(--text-muted)'
          }}>
            상단 모형을 확인하고 <strong>[손익 분석 실행]</strong> 버튼을 누르면 실시간 4단계 손익 분해 연산 프로세스가 시뮬레이션됩니다.
          </div>
        )}
      </div>
    </Modal>
  );
};
