import React, { useState } from 'react';
import { SgaBreakdownItem, PnlViewMode } from '../../types/pnl';
import { Landmark, AlertCircle, Search } from 'lucide-react';

interface SgaTableProps {
  items: SgaBreakdownItem[];
  initialViewMode?: PnlViewMode;
}

const MONTHS = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'];
const MAX_ACTUAL_MONTH = 6;

export const SgaTable: React.FC<SgaTableProps> = ({
  items,
  initialViewMode = 'PLAN_ACTUAL_COMPARE',
}) => {
  const [viewMode, setViewMode] = useState<PnlViewMode>(initialViewMode);

  // Draft vs Applied Period State
  const [draftStartMonth, setDraftStartMonth] = useState<string>('1월');
  const [draftEndMonth, setDraftEndMonth] = useState<string>('6월');
  const [appliedStartMonth, setAppliedStartMonth] = useState<string>('1월');
  const [appliedEndMonth, setAppliedEndMonth] = useState<string>('6월');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handlePeriodSearch = () => {
    const startNum = parseInt(draftStartMonth.replace('월', ''), 10);
    const endNum = parseInt(draftEndMonth.replace('월', ''), 10);

    // Validation A: 시작월 > 종료월
    if (startNum > endNum) {
      setErrorMessage(`[기간 설정 오류] 시작월(${draftStartMonth})이 종료월(${draftEndMonth})보다 이후일 수 없습니다.`);
      return;
    }

    // Validation B: 실적 미입력 월 포함
    if (endNum > MAX_ACTUAL_MONTH || startNum > MAX_ACTUAL_MONTH) {
      setErrorMessage(`[실적이 없습니다] 선택하신 기간 중 실적 데이터가 입력되지 않은 월(${Math.max(startNum, MAX_ACTUAL_MONTH + 1)}월~${endNum}월)이 포함되어 계획/실적 비교가 불가능합니다.`);
      return;
    }

    // Validation C: 정상 통과
    setErrorMessage(null);
    setAppliedStartMonth(draftStartMonth);
    setAppliedEndMonth(draftEndMonth);
  };

  const formatAmount = (num: number) => Math.round(num).toLocaleString();
  const formatDiff = (num: number) => (num > 0 ? `+${Math.round(num).toLocaleString()}` : Math.round(num).toLocaleString());
  const formatRate = (rate: number) => (rate > 0 ? `+${rate.toFixed(1)}%` : `${rate.toFixed(1)}%`);

  return (
    <div className="financial-table-container" style={{ marginBottom: 16 }}>
      {/* Sub-Tab Header Toolbar with Local ViewMode & Period Selector with [조회] */}
      <div style={{
        padding: '9px 14px',
        borderBottom: '1px solid var(--border-default)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        backgroundColor: '#f8fafc',
        flexWrap: 'wrap',
        gap: 8
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '13px', color: '#0f172a' }}>
          <Landmark size={15} color="#7c3aed" />
          판매비와 관리비 명세서
        </div>

        {/* Compact Single-Line View Mode Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div className="segmented-control">
            <button
              type="button"
              className={`segmented-btn ${viewMode === 'ACTUAL_ONLY' ? 'active' : ''}`}
              onClick={() => { setViewMode('ACTUAL_ONLY'); setErrorMessage(null); }}
            >
              실적만 보기
            </button>
            <button
              type="button"
              className={`segmented-btn ${viewMode === 'PLAN_ACTUAL_COMPARE' ? 'active' : ''}`}
              onClick={() => { setViewMode('PLAN_ACTUAL_COMPARE'); setErrorMessage(null); }}
            >
              계획 / 실적 비교
            </button>
            <button
              type="button"
              className={`segmented-btn ${viewMode === 'CUSTOM_PERIOD_COMPARE' ? 'active' : ''}`}
              onClick={() => { setViewMode('CUSTOM_PERIOD_COMPARE'); setErrorMessage(null); }}
            >
              기간 설정 비교
            </button>
          </div>

          {/* Conditional Period Selectors with [조회] Button */}
          {viewMode === 'CUSTOM_PERIOD_COMPARE' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, backgroundColor: '#eff6ff', padding: '2px 8px', borderRadius: 4, border: '1px solid #bfdbfe' }}>
              <span style={{ fontSize: '11px', color: '#1e40af', fontWeight: 600 }}>시작월</span>
              <select
                className="filter-select"
                style={{ height: '22px', fontSize: '11px', padding: '0 4px', minWidth: '52px' }}
                value={draftStartMonth}
                onChange={e => setDraftStartMonth(e.target.value)}
              >
                {MONTHS.map(m => (
                  <option key={`sga-start-${m}`} value={m}>{m}</option>
                ))}
              </select>
              <span style={{ fontSize: '11px', color: '#64748b' }}>~ 종료월</span>
              <select
                className="filter-select"
                style={{ height: '22px', fontSize: '11px', padding: '0 4px', minWidth: '52px' }}
                value={draftEndMonth}
                onChange={e => setDraftEndMonth(e.target.value)}
              >
                {MONTHS.map(m => (
                  <option key={`sga-end-${m}`} value={m}>{m}</option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                style={{ height: '22px', padding: '0 8px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: 3 }}
                onClick={handlePeriodSearch}
              >
                <Search size={10} />
                조회
              </button>
            </div>
          )}

          <span className="unit-tag">단위: 백만원 / %</span>
        </div>
      </div>

      {/* Validation Error Banner */}
      {errorMessage && (
        <div className="period-error-banner">
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <AlertCircle size={14} color="#dc2626" />
            <span style={{ fontWeight: 600 }}>{errorMessage}</span>
          </div>
          <span style={{ fontSize: '10.5px', color: '#b91c1c' }}>기존 조회 결과 유지 중</span>
        </div>
      )}

      <table className="financial-table">
        <thead>
          <tr>
            <th style={{ width: viewMode === 'ACTUAL_ONLY' ? '45%' : '36%' }}>판관비 항목</th>
            <th className="text-center" style={{ width: '10%' }}>구분</th>

            {viewMode === 'ACTUAL_ONLY' && (
              <>
                <th className="text-right" style={{ width: '25%' }}>당월 실적</th>
                <th className="text-right" style={{ width: '20%' }}>매출 대비 비중</th>
              </>
            )}

            {(viewMode === 'PLAN_ACTUAL_COMPARE' || viewMode === 'CUSTOM_PERIOD_COMPARE') && (
              <>
                <th className="text-right" style={{ width: '14%' }}>
                  {viewMode === 'CUSTOM_PERIOD_COMPARE' ? `${appliedStartMonth}~${appliedEndMonth} 계획 누계` : '당월 계획'}
                </th>
                <th className="text-right" style={{ width: '14%' }}>
                  {viewMode === 'CUSTOM_PERIOD_COMPARE' ? `${appliedStartMonth}~${appliedEndMonth} 실적 누계` : '당월 실적'}
                </th>
                <th className="text-right" style={{ width: '13%' }}>차이</th>
                <th className="text-right" style={{ width: '13%' }}>증감률</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {items.map((row) => {
            const isHeader = row.level === 0;
            const isGrandTotal = row.level === 2;

            const planVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? row.ytdPlan : row.plan;
            const actualVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? row.ytdActual : row.actual;
            const diffVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? row.ytdVariance : row.variance;
            const rateVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? row.ytdVarianceRate : row.varianceRate;

            const isFavorable = diffVal <= 0;

            return (
              <tr
                key={row.id}
                className={isGrandTotal ? 'row-total' : isHeader ? 'row-header' : 'row-sublevel-1'}
                style={{ backgroundColor: isHeader ? '#f8fafc' : isGrandTotal ? '#f1f5f9' : undefined }}
              >
                <td className="text-left" style={{ fontWeight: isHeader || isGrandTotal ? 700 : 500 }}>
                  {row.name}
                </td>
                <td className="text-center" style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  {row.category}
                </td>

                {viewMode === 'ACTUAL_ONLY' && (
                  <>
                    <td className="text-right tabular-nums" style={{ fontWeight: isGrandTotal ? 800 : isHeader ? 700 : 500 }}>
                      {formatAmount(actualVal)}
                    </td>
                    <td className="text-right tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                      {row.ratioToRevenue ? `${row.ratioToRevenue.toFixed(2)}%` : '-'}
                    </td>
                  </>
                )}

                {(viewMode === 'PLAN_ACTUAL_COMPARE' || viewMode === 'CUSTOM_PERIOD_COMPARE') && (
                  <>
                    <td className="text-right tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      {formatAmount(planVal)}
                    </td>
                    <td className="text-right tabular-nums" style={{ fontWeight: isGrandTotal ? 800 : isHeader ? 700 : 600 }}>
                      {formatAmount(actualVal)}
                    </td>
                    <td className={`text-right tabular-nums ${isFavorable ? 'val-favorable' : 'val-unfavorable'}`} style={{ fontWeight: isGrandTotal || isHeader ? 700 : 500 }}>
                      {formatDiff(diffVal)}
                    </td>
                    <td className={`text-right tabular-nums ${isFavorable ? 'val-favorable' : 'val-unfavorable'}`}>
                      {formatRate(rateVal)}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
