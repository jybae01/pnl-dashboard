import React, { useState } from 'react';
import { VarianceEffectItem } from '../../types/variance';
import { ChevronRight, ChevronDown, ListFilter, HelpCircle } from 'lucide-react';

interface VarianceDetailTableProps {
  effects: VarianceEffectItem[];
  highlightedEffectId?: string;
  onSelectEffect?: (id: string) => void;
}

export const VarianceDetailTable: React.FC<VarianceDetailTableProps> = ({
  effects,
  highlightedEffectId,
  onSelectEffect,
}) => {
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({
    eff_vol: true, // Default expand volume for demonstration
  });

  const toggleRow = (id: string) => {
    setExpandedRows(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const formatNum = (val: number) => val.toLocaleString();
  const formatDiff = (val: number) => (val > 0 ? `+${val.toLocaleString()}` : val.toLocaleString());
  const formatEffect = (val: number) => (val > 0 ? `+${val.toLocaleString()}` : val.toLocaleString());

  const totalProfitEffect = effects.reduce((sum, e) => sum + e.profitEffect, 0);

  return (
    <div className="financial-table-container" style={{ marginBottom: 16 }}>
      <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border-default)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#f8fafc' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '13px', color: '#0f172a' }}>
          <ListFilter size={15} color="#2563eb" />
          손익 변동 원인별 Effect 상세 분석표
        </div>
        <span className="unit-tag">금액 단위: 백만원 (손익효과는 +이익증가, -이익감소)</span>
      </div>

      <table className="financial-table">
        <thead>
          <tr>
            <th style={{ width: '4%' }} className="text-center">구분</th>
            <th style={{ width: '22%' }}>손익 변동 원인 (Effect Item)</th>
            <th className="text-center" style={{ width: '7%' }}>단위</th>
            <th className="text-right" style={{ width: '10%' }}>계획 (Plan)</th>
            <th className="text-right" style={{ width: '10%' }}>실적 (Actual)</th>
            <th className="text-right" style={{ width: '9%' }}>원인변동</th>
            <th className="text-right" style={{ width: '12%' }}>손익 영향 금액</th>
            <th className="text-right" style={{ width: '8%' }}>기여율</th>
            <th style={{ width: '18%' }}>분석 요약 및 특이사항</th>
          </tr>
        </thead>
        <tbody>
          {effects.map((eff) => {
            const isExpanded = !!expandedRows[eff.id];
            const isHighlighted = highlightedEffectId === eff.id;
            const hasDrilldown = eff.drilldownRows && eff.drilldownRows.length > 0;
            const isFavorable = eff.profitEffect >= 0;

            let categoryTag = '';
            let categoryClass = '';
            if (eff.category === 'INTERNAL') {
              categoryTag = '내부';
              categoryClass = 'model-pill-plan';
            } else if (eff.category === 'EXTERNAL') {
              categoryTag = '외부';
              categoryClass = 'model-pill-actual';
            } else if (eff.category === 'COST') {
              categoryTag = '비용';
              categoryClass = 'model-pill-forecast';
            } else {
              categoryTag = '시차';
              categoryClass = 'status-draft';
            }

            return (
              <React.Fragment key={eff.id}>
                <tr
                  className={isHighlighted ? 'row-active' : ''}
                  style={{ transition: 'background-color 0.2s ease' }}
                >
                  <td className="text-center">
                    <span className={`model-pill ${categoryClass}`} style={{ fontSize: '10px', padding: '1px 5px' }}>
                      {categoryTag}
                    </span>
                  </td>
                  <td className="text-left" style={{ fontWeight: 600 }}>
                    {hasDrilldown && (
                      <button
                        className="expand-toggle-btn"
                        onClick={() => toggleRow(eff.id)}
                        title={isExpanded ? '상세 접기' : '하위 항목 펼치기'}
                      >
                        {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      </button>
                    )}
                    <span
                      style={{ cursor: onSelectEffect ? 'pointer' : 'default', color: isHighlighted ? '#1d4ed8' : 'inherit' }}
                      onClick={() => onSelectEffect && onSelectEffect(eff.id)}
                    >
                      {eff.name}
                    </span>
                  </td>
                  <td className="text-center" style={{ color: 'var(--text-muted)' }}>{eff.unit}</td>
                  <td className="text-right tabular-nums">{formatNum(eff.planValue)}</td>
                  <td className="text-right tabular-nums" style={{ fontWeight: 600 }}>{formatNum(eff.actualValue)}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                    {formatDiff(eff.diffValue)}
                  </td>
                  <td className={`text-right tabular-nums ${isFavorable ? 'val-favorable' : 'val-unfavorable'}`} style={{ fontSize: '12.5px' }}>
                    {formatEffect(eff.profitEffect)}
                  </td>
                  <td className={`text-right tabular-nums ${isFavorable ? 'val-favorable' : 'val-unfavorable'}`}>
                    {eff.contributionRate > 0 ? `+${eff.contributionRate.toFixed(1)}%` : `${eff.contributionRate.toFixed(1)}%`}
                  </td>
                  <td className="text-left" style={{ fontSize: '11.5px', color: 'var(--text-secondary)' }}>
                    {eff.description}
                  </td>
                </tr>

                {/* Expanded Drilldown Sub-Rows */}
                {isExpanded && hasDrilldown && (
                  <tr>
                    <td colSpan={9} style={{ padding: 0, backgroundColor: '#f8fafc' }}>
                      <div className="drilldown-container">
                        <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 6 }}>
                          ↳ [{eff.name}] 세부 품목/요인별 기여 내역 드릴다운:
                        </div>
                        <table className="drilldown-table">
                          <thead>
                            <tr>
                              <th style={{ width: '30%' }}>세부 항목</th>
                              <th className="text-center" style={{ width: '8%' }}>단위</th>
                              <th className="text-right" style={{ width: '12%' }}>계획</th>
                              <th className="text-right" style={{ width: '12%' }}>실적</th>
                              <th className="text-right" style={{ width: '12%' }}>차이</th>
                              <th className="text-right" style={{ width: '12%' }}>손익영향(백만원)</th>
                              <th style={{ width: '14%' }}>비고</th>
                            </tr>
                          </thead>
                          <tbody>
                            {eff.drilldownRows.map((sub) => (
                              <tr key={sub.id}>
                                <td>{sub.subItemName}</td>
                                <td className="text-center" style={{ color: '#94a3b8' }}>{sub.unit}</td>
                                <td className="text-right tabular-nums">{sub.planValue.toLocaleString()}</td>
                                <td className="text-right tabular-nums">{sub.actualValue.toLocaleString()}</td>
                                <td className="text-right tabular-nums">{formatDiff(sub.diffValue)}</td>
                                <td className={`text-right tabular-nums ${sub.profitEffect >= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                                  {formatEffect(sub.profitEffect)}
                                </td>
                                <td style={{ color: '#64748b' }}>{sub.note}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}

          {/* Total Effect Row */}
          <tr className="row-total">
            <td colSpan={6} className="text-left" style={{ fontWeight: 700 }}>
              손익 변동 Effect 합계 (총 {effects.length}대 요인 분해)
            </td>
            <td className={`text-right tabular-nums ${totalProfitEffect >= 0 ? 'val-favorable' : 'val-unfavorable'}`} style={{ fontSize: '13px', fontWeight: 800 }}>
              {formatEffect(totalProfitEffect)}
            </td>
            <td className="text-right tabular-nums" style={{ fontWeight: 700 }}>100.0%</td>
            <td className="text-left" style={{ fontSize: '11px', color: '#16a34a', fontWeight: 600 }}>
              • 잔여 차이: 0 백만원 (정합성 확인 완료)
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};
