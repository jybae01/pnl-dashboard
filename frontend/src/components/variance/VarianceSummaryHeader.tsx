import React from 'react';
import { VarianceAnalysisResult } from '../../types/variance';
import { ArrowRight, ShieldCheck, AlertTriangle, Download } from 'lucide-react';

interface VarianceSummaryHeaderProps {
  data: VarianceAnalysisResult;
  onDownloadExcel?: () => void;
}

export const VarianceSummaryHeader: React.FC<VarianceSummaryHeaderProps> = ({ data, onDownloadExcel }) => {
  const isPositive = data.totalVariance >= 0;
  const formatAmount = (num: number) => Math.round(num).toLocaleString();
  const formatSignAmount = (num: number) => (num > 0 ? `+${Math.round(num).toLocaleString()}` : Math.round(num).toLocaleString());

  const totalEffectSum = data.effects.reduce((sum, eff) => sum + eff.profitEffect, 0);
  const residualVariance = data.totalVariance - totalEffectSum;
  const isIntegrityVerified = residualVariance === 0;

  return (
    <div className="variance-hero-banner" style={{ marginBottom: 14 }}>
      {/* Left: Model and Main Variance Hero */}
      <div className="variance-hero-left">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className="model-pill model-pill-plan">기준 모형: {data.baselineModelName}</span>
            <ArrowRight size={13} color="#94a3b8" />
            <span className="model-pill model-pill-actual">비교 모형: {data.comparisonModelName}</span>
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            분석 대상: {data.baseMonth} ({data.productGroup === 'ALL' ? '전사 통합' : `${data.productGroup} 제품군`})
          </div>
        </div>

        <div className="variance-hero-score">
          <div>
            <div className="score-label">실제 영업이익 증감 (Total Variance)</div>
            <div className="score-amount tabular-nums" style={{ color: isPositive ? 'var(--color-favorable)' : 'var(--color-unfavorable)' }}>
              {formatSignAmount(data.totalVariance)} <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-secondary)' }}>백만원</span>
            </div>
          </div>
          <span className={`score-rate ${isPositive ? 'badge-favorable' : 'badge-unfavorable'}`}>
            {isPositive ? `+${data.varianceRate.toFixed(1)}% 초과달성` : `${data.varianceRate.toFixed(1)}% 미달`}
          </span>
        </div>
      </div>

      {/* Right: Plan/Actual, Effect Sum, and Residual Variance Verification */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        borderLeft: '1px solid var(--border-subtle)',
        paddingLeft: 16,
        flexWrap: 'wrap'
      }}>
        <div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>계획 영업이익</div>
          <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-plan)' }} className="tabular-nums">
            {formatAmount(data.planOpProfit)} 백만원
          </div>
        </div>

        <div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>실적 영업이익</div>
          <div style={{ fontSize: '14px', fontWeight: 800, color: 'var(--color-actual)' }} className="tabular-nums">
            {formatAmount(data.actualOpProfit)} 백만원
          </div>
        </div>

        {/* Verification Status Box */}
        <div style={{
          backgroundColor: isIntegrityVerified ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${isIntegrityVerified ? '#bbf7d0' : '#fca5a5'}`,
          borderRadius: 'var(--radius-sm)',
          padding: '6px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 2
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '11px', fontWeight: 700, color: isIntegrityVerified ? '#16a34a' : '#dc2626' }}>
            {isIntegrityVerified ? <ShieldCheck size={13} /> : <AlertTriangle size={13} />}
            <span>{isIntegrityVerified ? '정합성 확인 완료' : '정합성 불일치 Warning'}</span>
          </div>
          <div style={{ fontSize: '10.5px', color: '#475569' }}>
            손익효과 합계: <strong>{formatSignAmount(totalEffectSum)}</strong> | 잔여 차이: <strong style={{ color: isIntegrityVerified ? '#16a34a' : '#dc2626' }}>{formatAmount(residualVariance)} 백만원</strong>
          </div>
        </div>

        {/* Action Button: 분석 근거 엑셀 내려받기 */}
        {onDownloadExcel && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onDownloadExcel}
            style={{
              color: '#0f766e',
              borderColor: '#99f6e4',
              backgroundColor: '#f0fdfa',
              fontSize: '11.5px',
              fontWeight: 700,
              padding: '6px 12px',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 5,
              marginLeft: 4,
            }}
            title="분석 근거 엑셀 내려받기"
          >
            <Download size={13} />
            분석 근거 엑셀 내려받기
          </button>
        )}
      </div>
    </div>
  );
};
