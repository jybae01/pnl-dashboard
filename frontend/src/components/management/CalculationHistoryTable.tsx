import React, { useState } from 'react';
import { History, CheckCircle2, XCircle, ArrowRight, Download, FileSpreadsheet } from 'lucide-react';

export interface CalculationHistoryRecord {
  id: string;
  calculatedAt: string;
  baselineModelName: string;
  comparisonModelName: string;
  analysisType: 'PLAN_VS_ACTUAL' | 'PLAN_VS_FORECAST';
  analysisTypeLabel: string;
  status: 'COMPLETED' | 'FAILED';
  statusLabel: string;
  varianceAmountText: string;
}

export const DUMMY_CALC_HISTORY: CalculationHistoryRecord[] = [
  {
    id: 'job_hist_01',
    calculatedAt: '2026-08-10 12:30',
    baselineModelName: '[PLAN] 2026년 6월 경영계획 확정본 (V2.1)',
    comparisonModelName: '[ACTUAL] 2026년 6월 마감 실적 (V1.0)',
    analysisType: 'PLAN_VS_ACTUAL',
    analysisTypeLabel: '계획 대비 실적',
    status: 'COMPLETED',
    statusLabel: '계산 완료',
    varianceAmountText: '+320 백만원 (초과 달성)',
  },
  {
    id: 'job_hist_02',
    calculatedAt: '2026-08-08 17:15',
    baselineModelName: '[PLAN] 2026년 6월 경영계획 확정본 (V2.1)',
    comparisonModelName: '[FORECAST] 2026년 6월 1차 추정 (V1.2)',
    analysisType: 'PLAN_VS_FORECAST',
    analysisTypeLabel: '계획 대비 추정',
    status: 'COMPLETED',
    statusLabel: '계산 완료',
    varianceAmountText: '+280 백만원 (추정 호조)',
  },
  {
    id: 'job_hist_03',
    calculatedAt: '2026-08-05 09:40',
    baselineModelName: '[PLAN] 2026년 6월 경영계획 확정본 (V2.0)',
    comparisonModelName: '[ACTUAL] 2026년 6월 가마감 실적 (V0.9)',
    analysisType: 'PLAN_VS_ACTUAL',
    analysisTypeLabel: '계획 대비 실적',
    status: 'FAILED',
    statusLabel: '계산 실패 (SHA 불일치)',
    varianceAmountText: '-',
  }
];

interface CalculationHistoryTableProps {
  onGoToVariance: () => void;
}

export const CalculationHistoryTable: React.FC<CalculationHistoryTableProps> = ({ onGoToVariance }) => {
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const handleDownloadExcel = (jobId: string) => {
    setToastMessage(`[${jobId}] 분석 근거 엑셀 생성 기능은 기존 실제 프로젝트 PR 모듈과 연결됩니다.`);
    setTimeout(() => setToastMessage(null), 3500);
  };

  return (
    <div className="financial-table-container" style={{ marginTop: 16, marginBottom: 20 }}>
      <div style={{
        padding: '10px 14px',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        backgroundColor: '#f8fafc'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '13px', color: '#0f172a' }}>
          <History size={15} color="#2563eb" />
          과거 계산 이력 (Calculation History)
        </div>
        <span className="unit-tag">총 {DUMMY_CALC_HISTORY.length}건의 계산 이력</span>
      </div>

      {toastMessage && (
        <div style={{
          padding: '8px 14px',
          backgroundColor: '#f0fdf4',
          borderBottom: '1px solid #bbf7d0',
          fontSize: '11.5px',
          color: '#16a34a',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: 6
        }}>
          <FileSpreadsheet size={14} color="#16a34a" />
          <span>{toastMessage}</span>
        </div>
      )}

      <table className="financial-table">
        <thead>
          <tr>
            <th style={{ width: '13%' }}>계산 일시</th>
            <th style={{ width: '27%' }}>기준 모형</th>
            <th style={{ width: '27%' }}>비교 모형</th>
            <th className="text-center" style={{ width: '10%' }}>분석 구분</th>
            <th className="text-center" style={{ width: '9%' }}>상태</th>
            <th className="text-center" style={{ width: '14%' }}>결과 및 액션</th>
          </tr>
        </thead>
        <tbody>
          {DUMMY_CALC_HISTORY.map((row) => {
            const isSuccess = row.status === 'COMPLETED';

            return (
              <tr key={row.id}>
                <td style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
                  {row.calculatedAt}
                </td>
                <td className="text-left" style={{ fontWeight: 600, fontSize: '11.5px' }}>
                  {row.baselineModelName}
                </td>
                <td className="text-left" style={{ fontWeight: 600, fontSize: '11.5px' }}>
                  {row.comparisonModelName}
                </td>
                <td className="text-center" style={{ fontSize: '11px' }}>
                  <span className="model-pill model-pill-plan">
                    {row.analysisTypeLabel}
                  </span>
                </td>
                <td className="text-center">
                  <span
                    className={isSuccess ? 'badge-favorable' : 'badge-unfavorable'}
                    style={{ fontSize: '10.5px', display: 'inline-flex', alignItems: 'center', gap: 3 }}
                  >
                    {isSuccess ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                    {row.statusLabel}
                  </span>
                </td>
                <td className="text-center">
                  {isSuccess ? (
                    <div style={{ display: 'flex', gap: 4, justifyContent: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        style={{ fontSize: '10.5px', padding: '2px 6px', display: 'inline-flex', alignItems: 'center', gap: 2 }}
                        onClick={onGoToVariance}
                        title="손익 분석 화면으로 이동"
                      >
                        결과 보기
                        <ArrowRight size={10} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        style={{ fontSize: '10.5px', padding: '2px 7px', color: '#0f766e', borderColor: '#99f6e4', display: 'inline-flex', alignItems: 'center', gap: 3 }}
                        onClick={() => handleDownloadExcel(row.id)}
                        title="분석 근거 엑셀 내려받기"
                      >
                        <Download size={10} />
                        분석 근거 엑셀
                      </button>
                    </div>
                  ) : (
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>-</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
