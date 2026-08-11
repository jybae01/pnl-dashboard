import React, { useState } from 'react';
import { PnlLineItem, PnlViewMode } from '../../types/pnl';
import { ChevronRight, ChevronDown, FileSpreadsheet, AlertCircle, Search } from 'lucide-react';

interface PnlTableProps {
  items: PnlLineItem[];
  initialViewMode?: PnlViewMode;
}

const MONTHS = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'];
const MAX_ACTUAL_MONTH = 6; // Mock actuals closed up to 6월

export const PnlTable: React.FC<PnlTableProps> = ({
  items,
  initialViewMode = 'PLAN_ACTUAL_COMPARE',
}) => {
  const [viewMode, setViewMode] = useState<PnlViewMode>(initialViewMode);

  // Draft period state (modified by dropdowns, does not update table until [조회] is clicked)
  const [draftStartMonth, setDraftStartMonth] = useState<string>('1월');
  const [draftEndMonth, setDraftEndMonth] = useState<string>('6월');

  // Applied period state (drives table calculations)
  const [appliedStartMonth, setAppliedStartMonth] = useState<string>('1월');
  const [appliedEndMonth, setAppliedEndMonth] = useState<string>('6월');

  // Validation error message
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({});

  const toggleCategory = (id: string) => {
    setCollapsedCategories(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const handlePeriodSearch = () => {
    const startNum = parseInt(draftStartMonth.replace('월', ''), 10);
    const endNum = parseInt(draftEndMonth.replace('월', ''), 10);

    // Validation A: 시작월 > 종료월
    if (startNum > endNum) {
      setErrorMessage(`[기간 설정 오류] 시작월(${draftStartMonth})이 종료월(${draftEndMonth})보다 이후일 수 없습니다.`);
      return;
    }

    // Validation B: 실적 데이터가 없는 월 포함 (7월 ~ 12월)
    if (endNum > MAX_ACTUAL_MONTH || startNum > MAX_ACTUAL_MONTH) {
      setErrorMessage(`[실적이 없습니다] 선택하신 기간 중 실적 데이터가 입력되지 않은 월(${Math.max(startNum, MAX_ACTUAL_MONTH + 1)}월~${endNum}월)이 포함되어 계획/실적 비교가 불가능합니다.`);
      return;
    }

    // Validation C: 정상 통과 -> Applied Period 갱신
    setErrorMessage(null);
    setAppliedStartMonth(draftStartMonth);
    setAppliedEndMonth(draftEndMonth);
  };

  const formatAmount = (num: number) => Math.round(num).toLocaleString();
  const formatDiff = (num: number, isRate: boolean = false) => {
    if (isRate) {
      return num > 0 ? `+${num.toFixed(2)}%p` : `${num.toFixed(2)}%p`;
    }
    return num > 0 ? `+${Math.round(num).toLocaleString()}` : Math.round(num).toLocaleString();
  };

  const formatRate = (rate: number, isRate: boolean = false) => {
    if (isRate) return `${rate.toFixed(2)}%`;
    return rate > 0 ? `+${rate.toFixed(1)}%` : `${rate.toFixed(1)}%`;
  };

  return (
    <div className="financial-table-container" style={{ marginBottom: 16 }}>
      {/* 1. Sub-Tab Header Toolbar with Local ViewMode & Period Selector with [조회] Button */}
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
        {/* Title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '13px', color: '#0f172a' }}>
          <FileSpreadsheet size={15} color="#2563eb" />
          손익계산서 (P&L)
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
                  <option key={`pnl-start-${m}`} value={m}>{m}</option>
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
                  <option key={`pnl-end-${m}`} value={m}>{m}</option>
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

          <span className="unit-tag" style={{ marginLeft: 4 }}>금액 단위: 백만원 (비율 차이는 %p)</span>
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

      {/* Applied Period Status Badge (when in CUSTOM_PERIOD_COMPARE) */}
      {viewMode === 'CUSTOM_PERIOD_COMPARE' && !errorMessage && (
        <div style={{ padding: '4px 14px', backgroundColor: '#f8fafc', borderBottom: '1px solid var(--border-subtle)', fontSize: '11px', color: '#1e40af' }}>
          • 적용 조회 기간: <strong>{appliedStartMonth} ~ {appliedEndMonth} 누계</strong> (마감 실적 기준)
        </div>
      )}

      {/* 2. Main Financial Statement Table */}
      <table className="financial-table">
        <thead>
          <tr>
            <th style={{ width: viewMode === 'ACTUAL_ONLY' ? '45%' : '32%' }}>계정과목</th>
            <th className="text-center" style={{ width: '8%' }}>단위</th>

            {/* Mode: ACTUAL_ONLY */}
            {viewMode === 'ACTUAL_ONLY' && (
              <>
                <th className="text-right" style={{ width: '25%' }}>당월 실적</th>
                <th className="text-right" style={{ width: '22%' }}>매출액 대비 비중</th>
              </>
            )}

            {/* Mode: PLAN_ACTUAL_COMPARE (당월) */}
            {viewMode === 'PLAN_ACTUAL_COMPARE' && (
              <>
                <th className="text-right" style={{ width: '15%' }}>당월 계획</th>
                <th className="text-right" style={{ width: '15%' }}>당월 실적</th>
                <th className="text-right" style={{ width: '15%' }}>차이</th>
                <th className="text-right" style={{ width: '15%' }}>달성률/증감</th>
              </>
            )}

            {/* Mode: CUSTOM_PERIOD_COMPARE (누계) */}
            {viewMode === 'CUSTOM_PERIOD_COMPARE' && (
              <>
                <th className="text-right" style={{ width: '15%' }}>{appliedStartMonth}~{appliedEndMonth} 계획 누계</th>
                <th className="text-right" style={{ width: '15%' }}>{appliedStartMonth}~{appliedEndMonth} 실적 누계</th>
                <th className="text-right" style={{ width: '15%' }}>누계 차이</th>
                <th className="text-right" style={{ width: '15%' }}>누계 달성률/증감</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {items.map((row) => {
            const isCollapsed = !!collapsedCategories[row.id];
            const hasChildren = row.children && row.children.length > 0;

            const planVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? (row.ytdPlan ?? row.plan) : row.plan;
            const actualVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? (row.ytdActual ?? row.actual) : row.actual;
            const diffVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? (row.ytdVariance ?? row.variance) : row.variance;
            const rateVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? (row.ytdVarianceRate ?? row.varianceRate) : row.varianceRate;

            const isFavorable =
              row.id.includes('cogs') || row.id.includes('sga')
                ? diffVal <= 0
                : diffVal >= 0;

            const isHighlightOp = row.id === 'pnl_op_total';

            return (
              <React.Fragment key={row.id}>
                <tr className={row.isTotal ? 'row-total' : row.isHeader ? 'row-header' : ''} style={{ backgroundColor: isHighlightOp ? '#eff6ff' : undefined }}>
                  <td className="text-left">
                    {hasChildren && (
                      <button
                        className="expand-toggle-btn"
                        onClick={() => toggleCategory(row.id)}
                        title={isCollapsed ? '펼치기' : '접기'}
                      >
                        {isCollapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                      </button>
                    )}
                    <span style={{ fontWeight: row.isTotal || row.isHeader ? 700 : 500, color: isHighlightOp ? '#1e3a8a' : undefined }}>
                      {row.name}
                    </span>
                  </td>
                  <td className="text-center" style={{ color: 'var(--text-muted)' }}>
                    {row.unit || (row.isRate ? '%' : '백만원')}
                  </td>

                  {/* Mode: ACTUAL_ONLY */}
                  {viewMode === 'ACTUAL_ONLY' && (
                    <>
                      <td className="text-right tabular-nums" style={{ fontWeight: row.isTotal ? 800 : 600 }}>
                        {row.isRate ? `${actualVal.toFixed(2)}%` : formatAmount(actualVal)}
                      </td>
                      <td className="text-right tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                        {row.ratioToRevenue !== undefined ? `${row.ratioToRevenue.toFixed(1)}%` : '-'}
                      </td>
                    </>
                  )}

                  {/* Mode: PLAN_ACTUAL_COMPARE & CUSTOM_PERIOD_COMPARE */}
                  {(viewMode === 'PLAN_ACTUAL_COMPARE' || viewMode === 'CUSTOM_PERIOD_COMPARE') && (
                    <>
                      <td className="text-right tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                        {row.isRate ? `${planVal.toFixed(2)}%` : formatAmount(planVal)}
                      </td>
                      <td className="text-right tabular-nums" style={{ fontWeight: row.isTotal ? 800 : 600 }}>
                        {row.isRate ? `${actualVal.toFixed(2)}%` : formatAmount(actualVal)}
                      </td>
                      <td className={`text-right tabular-nums ${isFavorable ? 'val-favorable' : 'val-unfavorable'}`} style={{ fontWeight: 700 }}>
                        {formatDiff(diffVal, row.isRate)}
                      </td>
                      <td className={`text-right tabular-nums ${isFavorable ? 'val-favorable' : 'val-unfavorable'}`}>
                        {row.isRate ? formatDiff(diffVal, true) : formatRate(rateVal, false)}
                      </td>
                    </>
                  )}
                </tr>

                {/* Sub-rows */}
                {!isCollapsed && hasChildren && row.children!.map((sub) => {
                  const subPlanVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? (sub.ytdPlan ?? sub.plan) : sub.plan;
                  const subActualVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? (sub.ytdActual ?? sub.actual) : sub.actual;
                  const subDiffVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? (sub.ytdVariance ?? sub.variance) : sub.variance;
                  const subRateVal = viewMode === 'CUSTOM_PERIOD_COMPARE' ? (sub.ytdVarianceRate ?? sub.varianceRate) : sub.varianceRate;

                  const subFavorable =
                    sub.id.includes('cogs') || sub.id.includes('sga')
                      ? subDiffVal <= 0
                      : subDiffVal >= 0;

                  return (
                    <tr key={sub.id} className="row-sublevel-1">
                      <td className="text-left">
                        <span>{sub.name}</span>
                      </td>
                      <td className="text-center" style={{ color: '#94a3b8' }}>
                        {sub.unit || '백만원'}
                      </td>

                      {viewMode === 'ACTUAL_ONLY' && (
                        <>
                          <td className="text-right tabular-nums">{formatAmount(subActualVal)}</td>
                          <td className="text-right tabular-nums" style={{ color: 'var(--text-muted)' }}>
                            {sub.ratioToRevenue !== undefined ? `${sub.ratioToRevenue.toFixed(1)}%` : '-'}
                          </td>
                        </>
                      )}

                      {(viewMode === 'PLAN_ACTUAL_COMPARE' || viewMode === 'CUSTOM_PERIOD_COMPARE') && (
                        <>
                          <td className="text-right tabular-nums" style={{ color: 'var(--text-muted)' }}>
                            {formatAmount(subPlanVal)}
                          </td>
                          <td className="text-right tabular-nums">{formatAmount(subActualVal)}</td>
                          <td className={`text-right tabular-nums ${subFavorable ? 'val-favorable' : 'val-unfavorable'}`}>
                            {formatDiff(subDiffVal, false)}
                          </td>
                          <td className={`text-right tabular-nums ${subFavorable ? 'val-favorable' : 'val-unfavorable'}`}>
                            {formatRate(subRateVal, false)}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
