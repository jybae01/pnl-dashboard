import React from 'react';
import { PnlKpiSummary } from '../../types/pnl';
import { DollarSign, Target, Award } from 'lucide-react';

interface KpiOverviewProps {
  kpi: PnlKpiSummary;
}

export const KpiOverview: React.FC<KpiOverviewProps> = ({ kpi }) => {
  const formatAmount = (val: number) => Math.round(val).toLocaleString();
  const formatSignAmount = (val: number) => (val > 0 ? `+${Math.round(val).toLocaleString()}` : Math.round(val).toLocaleString());
  const formatRate = (val: number) => (val > 0 ? `+${val.toFixed(1)}%` : `${val.toFixed(1)}%`);

  return (
    <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 16 }}>
      {/* 1. 매출액 KPI */}
      <div className="kpi-card" style={{ border: '1px solid var(--border-default)', backgroundColor: '#ffffff' }}>
        <div className="kpi-top-row">
          <span className="kpi-title" style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#334155', fontWeight: 700 }}>
            <DollarSign size={15} color="#475569" />
            1. {kpi.revenue.title}
          </span>
          <span className="kpi-unit">단위: 백만원</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8, marginTop: 4 }}>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>당월 실적</div>
            <div className="kpi-main-val tabular-nums" style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', marginBottom: 0 }}>
              {formatAmount(kpi.revenue.monthlyActual)}
            </div>
          </div>

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>계획 대비</div>
            <div className={kpi.revenue.monthlyVariance >= 0 ? 'val-favorable' : 'val-unfavorable'} style={{ fontSize: '13px', fontWeight: 700 }}>
              {formatSignAmount(kpi.revenue.monthlyVariance)} ({formatRate(kpi.revenue.monthlyAchievementRate - 100)})
            </div>
          </div>
        </div>

        {/* 누계 실적 & 진도율 / 달성률 */}
        <div style={{ backgroundColor: '#f8fafc', padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '11px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ color: 'var(--text-secondary)' }}>• <strong>누계 실적:</strong> {formatAmount(kpi.revenue.ytdActual)} 백만원</span>
            <span className={kpi.revenue.ytdVariance >= 0 ? 'val-favorable' : 'val-unfavorable'} style={{ fontWeight: 600 }}>
              계획대비 {kpi.revenue.ytdAchievementRate.toFixed(1)}%
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
            <span>• 연간 계획({formatAmount(kpi.revenue.annualPlan)}) 대비</span>
            <span style={{ fontWeight: 700, color: '#1e40af' }}>진도율 {kpi.revenue.annualProgressRate.toFixed(1)}%</span>
          </div>
        </div>
      </div>

      {/* 2. 영업이익 KPI (동일한 디자인 & 색상 체계) */}
      <div className="kpi-card" style={{ border: '1px solid var(--border-default)', backgroundColor: '#ffffff' }}>
        <div className="kpi-top-row">
          <span className="kpi-title" style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#334155', fontWeight: 700 }}>
            <Target size={15} color="#475569" />
            2. {kpi.operatingProfit.title}
          </span>
          <span className="kpi-unit">
            이익률: {kpi.operatingMargin.toFixed(1)}% ({kpi.operatingMarginGap >= 0 ? `+${kpi.operatingMarginGap.toFixed(2)}%p` : `${kpi.operatingMarginGap.toFixed(2)}%p`})
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8, marginTop: 4 }}>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>당월 실적</div>
            <div className="kpi-main-val tabular-nums" style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', marginBottom: 0 }}>
              {formatAmount(kpi.operatingProfit.monthlyActual)}
            </div>
          </div>

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>계획 대비</div>
            <div className={kpi.operatingProfit.monthlyVariance >= 0 ? 'val-favorable' : 'val-unfavorable'} style={{ fontSize: '13px', fontWeight: 700 }}>
              {formatSignAmount(kpi.operatingProfit.monthlyVariance)} ({formatRate(kpi.operatingProfit.monthlyAchievementRate - 100)})
            </div>
          </div>
        </div>

        {/* 누계 실적 & 진도율 / 달성률 */}
        <div style={{ backgroundColor: '#f8fafc', padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '11px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ color: 'var(--text-secondary)' }}>• <strong>누계 실적:</strong> {formatAmount(kpi.operatingProfit.ytdActual)} 백만원</span>
            <span className={kpi.operatingProfit.ytdVariance >= 0 ? 'val-favorable' : 'val-unfavorable'} style={{ fontWeight: 600 }}>
              계획대비 {kpi.operatingProfit.ytdAchievementRate.toFixed(1)}%
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
            <span>• 연간 계획({formatAmount(kpi.operatingProfit.annualPlan)}) 대비</span>
            <span style={{ fontWeight: 700, color: '#1e40af' }}>진도율 {kpi.operatingProfit.annualProgressRate.toFixed(1)}%</span>
          </div>
        </div>
      </div>

      {/* 3. 조정 영업이익 KPI (동일한 디자인 & 색상 체계) */}
      <div className="kpi-card" style={{ border: '1px solid var(--border-default)', backgroundColor: '#ffffff' }}>
        <div className="kpi-top-row">
          <span className="kpi-title" style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#334155', fontWeight: 700 }}>
            <Award size={15} color="#475569" />
            3. {kpi.adjustedOperatingProfit.title}
          </span>
          <span className="kpi-unit">조정이익률: {kpi.adjustedOperatingMargin.toFixed(1)}% ({kpi.adjustedOperatingMarginGap >= 0 ? `+${kpi.adjustedOperatingMarginGap.toFixed(2)}%p` : `${kpi.adjustedOperatingMarginGap.toFixed(2)}%p`})</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 8, marginTop: 4 }}>
          <div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>당월 실적 (조정후)</div>
            <div className="kpi-main-val tabular-nums" style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', marginBottom: 0 }}>
              {formatAmount(kpi.adjustedOperatingProfit.monthlyActual)}
            </div>
          </div>

          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>계획 대비</div>
            <div className={kpi.adjustedOperatingProfit.monthlyVariance >= 0 ? 'val-favorable' : 'val-unfavorable'} style={{ fontSize: '13px', fontWeight: 700 }}>
              {formatSignAmount(kpi.adjustedOperatingProfit.monthlyVariance)} ({formatRate(kpi.adjustedOperatingProfit.monthlyAchievementRate - 100)})
            </div>
          </div>
        </div>

        {/* 누계 실적 & 진도율 / 달성률 */}
        <div style={{ backgroundColor: '#f8fafc', padding: '6px 10px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)', fontSize: '11px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ color: 'var(--text-secondary)' }}>• <strong>누계 실적:</strong> {formatAmount(kpi.adjustedOperatingProfit.ytdActual)} 백만원</span>
            <span className={kpi.adjustedOperatingProfit.ytdVariance >= 0 ? 'val-favorable' : 'val-unfavorable'} style={{ fontWeight: 600 }}>
              계획대비 {kpi.adjustedOperatingProfit.ytdAchievementRate.toFixed(1)}%
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
            <span>• 연간 계획({formatAmount(kpi.adjustedOperatingProfit.annualPlan)}) 대비</span>
            <span style={{ fontWeight: 700, color: '#1e40af' }}>진도율 {kpi.adjustedOperatingProfit.annualProgressRate.toFixed(1)}%</span>
          </div>
        </div>
      </div>
    </div>
  );
};
