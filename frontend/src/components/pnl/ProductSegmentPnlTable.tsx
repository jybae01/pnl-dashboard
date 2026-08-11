import React, { useState } from 'react';
import { ProductSegmentPnl, PnlViewMode } from '../../types/pnl';
import { Package, AlertCircle, Search } from 'lucide-react';

interface ProductSegmentPnlTableProps {
  segments: ProductSegmentPnl[];
  initialViewMode?: PnlViewMode;
}

const MONTHS = ['1월', '2월', '3월', '4월', '5월', '6월', '7월', '8월', '9월', '10월', '11월', '12월'];
const MAX_ACTUAL_MONTH = 6;

export const ProductSegmentPnlTable: React.FC<ProductSegmentPnlTableProps> = ({
  segments,
  initialViewMode = 'PLAN_ACTUAL_COMPARE',
}) => {
  const [viewMode, setViewMode] = useState<PnlViewMode>(initialViewMode);

  // Draft vs Applied Period State
  const [draftStartMonth, setDraftStartMonth] = useState<string>('1월');
  const [draftEndMonth, setDraftEndMonth] = useState<string>('6월');
  const [appliedStartMonth, setAppliedStartMonth] = useState<string>('1월');
  const [appliedEndMonth, setAppliedEndMonth] = useState<string>('6월');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [selectedItemId, setSelectedItemId] = useState<string>('8inch_sw');

  const currentSegment = segments.find(s => s.itemId === selectedItemId) || segments[0];
  const isNewBiz = currentSegment.itemId === 'new_biz';

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

  const formatAmount = (val: number) => Math.round(val).toLocaleString();
  const formatDiff = (val: number, isRate: boolean = false) => {
    if (isRate) return val > 0 ? `+${val.toFixed(2)}%p` : `${val.toFixed(2)}%p`;
    return val > 0 ? `+${Math.round(val).toLocaleString()}` : Math.round(val).toLocaleString();
  };

  const formatAsp = (val: number) => `${Math.round(val).toLocaleString()}원`;
  const formatAspDiff = (val: number) => (val > 0 ? `+${Math.round(val).toLocaleString()}원` : `${Math.round(val).toLocaleString()}원`);

  const isPeriod = viewMode === 'CUSTOM_PERIOD_COMPARE';

  return (
    <div className="financial-table-container" style={{ marginBottom: 16 }}>
      {/* Sub-Tab Header Toolbar with Product Selector & Local ViewMode */}
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
        {/* Title & Product Selector (8인치 SW, 8인치 BW, 4인치 LC, 신사업) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '13px', color: '#0f172a' }}>
            <Package size={15} color="#2563eb" />
            Item별 구분손익
          </div>

          <div className="segmented-control" style={{ backgroundColor: '#ffffff', border: '1px solid #cbd5e1' }}>
            {segments.map((s) => (
              <button
                key={s.itemId}
                type="button"
                className={`segmented-btn ${selectedItemId === s.itemId ? 'active' : ''}`}
                onClick={() => setSelectedItemId(s.itemId)}
              >
                {s.itemName}
              </button>
            ))}
          </div>
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
                  <option key={`seg-start-${m}`} value={m}>{m}</option>
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
                  <option key={`seg-end-${m}`} value={m}>{m}</option>
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

          <span className="unit-tag">단위: 매출/원가/이익 (백만원), 수량 (pcs), ASP (원)</span>
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

      {/* Selected Item Clean Header Tag */}
      <div style={{
        padding: '6px 14px',
        backgroundColor: '#eff6ff',
        borderBottom: '1px solid #bfdbfe',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '11.5px',
      }}>
        <span style={{ color: '#1e40af', fontWeight: 700 }}>
          선택 품목: <strong>{currentSegment.itemName}</strong> {isNewBiz && '(신규 사업 부문 - 수량/단가 미적용)'}
        </span>
        <span style={{ color: '#3b82f6', fontSize: '11px' }}>
          {viewMode === 'ACTUAL_ONLY' && '[당월 실적 모드]'}
          {viewMode === 'PLAN_ACTUAL_COMPARE' && '[당월 계획 vs 실적 비교]'}
          {viewMode === 'CUSTOM_PERIOD_COMPARE' && `[${appliedStartMonth} ~ ${appliedEndMonth} 기간 누계 비교]`}
        </span>
      </div>

      <table className="financial-table">
        <thead>
          <tr>
            <th style={{ width: '32%' }}>손익 항목</th>
            <th className="text-center" style={{ width: '10%' }}>단위</th>

            {viewMode === 'ACTUAL_ONLY' && (
              <th className="text-right" style={{ width: '58%' }}>당월 실적</th>
            )}

            {(viewMode === 'PLAN_ACTUAL_COMPARE' || viewMode === 'CUSTOM_PERIOD_COMPARE') && (
              <>
                <th className="text-right" style={{ width: '20%' }}>{isPeriod ? `${appliedStartMonth}~${appliedEndMonth} 계획 누계` : '당월 계획'}</th>
                <th className="text-right" style={{ width: '20%' }}>{isPeriod ? `${appliedStartMonth}~${appliedEndMonth} 실적 누계` : '당월 실적'}</th>
                <th className="text-right" style={{ width: '18%' }}>차이</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {/* 1. 매출액 */}
          <tr className="row-header">
            <td className="text-left">1. 매출액</td>
            <td className="text-center">백만원</td>
            {viewMode === 'ACTUAL_ONLY' ? (
              <td className="text-right tabular-nums" style={{ fontWeight: 700 }}>
                {formatAmount(currentSegment.revenue.actual)}
              </td>
            ) : (
              <>
                <td className="text-right tabular-nums">{formatAmount(isPeriod ? currentSegment.revenue.ytdPlan : currentSegment.revenue.plan)}</td>
                <td className="text-right tabular-nums" style={{ fontWeight: 700 }}>{formatAmount(isPeriod ? currentSegment.revenue.ytdActual : currentSegment.revenue.actual)}</td>
                <td className={`text-right tabular-nums ${currentSegment.revenue.variance >= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                  {formatDiff(isPeriod ? (currentSegment.revenue.ytdActual - currentSegment.revenue.ytdPlan) : currentSegment.revenue.variance)}
                </td>
              </>
            )}
          </tr>

          {/* 2. 매출수량 (신사업일 경우 제외) */}
          {!isNewBiz && (
            <tr className="row-sublevel-1">
              <td className="text-left">2. 매출수량</td>
              <td className="text-center">{currentSegment.volume.unit || 'pcs'}</td>
              {viewMode === 'ACTUAL_ONLY' ? (
                <td className="text-right tabular-nums">{currentSegment.volume.actual.toLocaleString()}</td>
              ) : (
                <>
                  <td className="text-right tabular-nums">{isPeriod ? currentSegment.volume.ytdPlan.toLocaleString() : currentSegment.volume.plan.toLocaleString()}</td>
                  <td className="text-right tabular-nums">{isPeriod ? currentSegment.volume.ytdActual.toLocaleString() : currentSegment.volume.actual.toLocaleString()}</td>
                  <td className={`text-right tabular-nums ${currentSegment.volume.variance >= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                    {formatDiff(isPeriod ? (currentSegment.volume.ytdActual - currentSegment.volume.ytdPlan) : currentSegment.volume.variance)}
                  </td>
                </>
              )}
            </tr>
          )}

          {/* 3. 평균단가 (ASP) - 단위 '원' (신사업일 경우 제외) */}
          {!isNewBiz && (
            <tr className="row-sublevel-1" style={{ backgroundColor: '#fafaf9' }}>
              <td className="text-left" style={{ fontWeight: 600 }}>3. 평균단가 (ASP)</td>
              <td className="text-center" style={{ fontWeight: 700, color: '#0f172a' }}>원</td>
              {viewMode === 'ACTUAL_ONLY' ? (
                <td className="text-right tabular-nums" style={{ fontWeight: 700 }}>
                  {formatAsp(currentSegment.asp.actual)}
                </td>
              ) : (
                <>
                  <td className="text-right tabular-nums">{formatAsp(isPeriod ? currentSegment.asp.ytdPlan : currentSegment.asp.plan)}</td>
                  <td className="text-right tabular-nums" style={{ fontWeight: 700 }}>{formatAsp(isPeriod ? currentSegment.asp.ytdActual : currentSegment.asp.actual)}</td>
                  <td className={`text-right tabular-nums ${currentSegment.asp.variance >= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                    {formatAspDiff(isPeriod ? (currentSegment.asp.ytdActual - currentSegment.asp.ytdPlan) : currentSegment.asp.variance)}
                  </td>
                </>
              )}
            </tr>
          )}

          {/* 4. 매출원가 */}
          <tr className="row-header">
            <td className="text-left">{isNewBiz ? '2. 매출원가' : '4. 매출원가'}</td>
            <td className="text-center">백만원</td>
            {viewMode === 'ACTUAL_ONLY' ? (
              <td className="text-right tabular-nums">{formatAmount(currentSegment.cogs.actual)}</td>
            ) : (
              <>
                <td className="text-right tabular-nums">{formatAmount(isPeriod ? currentSegment.cogs.ytdPlan : currentSegment.cogs.plan)}</td>
                <td className="text-right tabular-nums">{formatAmount(isPeriod ? currentSegment.cogs.ytdActual : currentSegment.cogs.actual)}</td>
                <td className={`text-right tabular-nums ${currentSegment.cogs.variance <= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                  {formatDiff(isPeriod ? (currentSegment.cogs.ytdActual - currentSegment.cogs.ytdPlan) : currentSegment.cogs.variance)}
                </td>
              </>
            )}
          </tr>

          {/* 5. 매출원가율 */}
          <tr className="row-sublevel-1">
            <td className="text-left">• 매출원가율</td>
            <td className="text-center">%</td>
            {viewMode === 'ACTUAL_ONLY' ? (
              <td className="text-right tabular-nums">{currentSegment.cogsRatio.actual.toFixed(2)}%</td>
            ) : (
              <>
                <td className="text-right tabular-nums">{currentSegment.cogsRatio.plan.toFixed(2)}%</td>
                <td className="text-right tabular-nums">{currentSegment.cogsRatio.actual.toFixed(2)}%</td>
                <td className={`text-right tabular-nums ${currentSegment.cogsRatio.variance <= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                  {formatDiff(currentSegment.cogsRatio.variance, true)}
                </td>
              </>
            )}
          </tr>

          {/* 6. 매출총이익 */}
          <tr className="row-total" style={{ backgroundColor: '#f1f5f9' }}>
            <td className="text-left">{isNewBiz ? '3. 매출총이익' : '5. 매출총이익'}</td>
            <td className="text-center">백만원</td>
            {viewMode === 'ACTUAL_ONLY' ? (
              <td className="text-right tabular-nums" style={{ fontWeight: 800 }}>{formatAmount(currentSegment.grossProfit.actual)}</td>
            ) : (
              <>
                <td className="text-right tabular-nums">{formatAmount(isPeriod ? currentSegment.grossProfit.ytdPlan : currentSegment.grossProfit.plan)}</td>
                <td className="text-right tabular-nums" style={{ fontWeight: 800 }}>{formatAmount(isPeriod ? currentSegment.grossProfit.ytdActual : currentSegment.grossProfit.actual)}</td>
                <td className={`text-right tabular-nums ${currentSegment.grossProfit.variance >= 0 ? 'val-favorable' : 'val-unfavorable'}`} style={{ fontWeight: 800 }}>
                  {formatDiff(isPeriod ? (currentSegment.grossProfit.ytdActual - currentSegment.grossProfit.ytdPlan) : currentSegment.grossProfit.variance)}
                </td>
              </>
            )}
          </tr>

          {/* 7. 매출총이익률 */}
          <tr className="row-sublevel-1">
            <td className="text-left">• 매출총이익률</td>
            <td className="text-center">%</td>
            {viewMode === 'ACTUAL_ONLY' ? (
              <td className="text-right tabular-nums">{currentSegment.grossProfitMargin.actual.toFixed(2)}%</td>
            ) : (
              <>
                <td className="text-right tabular-nums">{currentSegment.grossProfitMargin.plan.toFixed(2)}%</td>
                <td className="text-right tabular-nums">{currentSegment.grossProfitMargin.actual.toFixed(2)}%</td>
                <td className={`text-right tabular-nums ${currentSegment.grossProfitMargin.variance >= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                  {formatDiff(currentSegment.grossProfitMargin.variance, true)}
                </td>
              </>
            )}
          </tr>

          {/* 8. 판매관리비 */}
          <tr>
            <td className="text-left">{isNewBiz ? '4. 판매관리비' : '6. 판매관리비'}</td>
            <td className="text-center">백만원</td>
            {viewMode === 'ACTUAL_ONLY' ? (
              <td className="text-right tabular-nums">{formatAmount(currentSegment.sga.actual)}</td>
            ) : (
              <>
                <td className="text-right tabular-nums">{formatAmount(isPeriod ? currentSegment.sga.ytdPlan : currentSegment.sga.plan)}</td>
                <td className="text-right tabular-nums">{formatAmount(isPeriod ? currentSegment.sga.ytdActual : currentSegment.sga.actual)}</td>
                <td className={`text-right tabular-nums ${currentSegment.sga.variance <= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                  {formatDiff(isPeriod ? (currentSegment.sga.ytdActual - currentSegment.sga.ytdPlan) : currentSegment.sga.variance)}
                </td>
              </>
            )}
          </tr>

          {/* 9. 영업이익 */}
          <tr className="row-total" style={{ backgroundColor: '#eff6ff' }}>
            <td className="text-left" style={{ color: '#1e3a8a' }}>{isNewBiz ? '5. 영업이익' : '7. 영업이익'}</td>
            <td className="text-center">백만원</td>
            {viewMode === 'ACTUAL_ONLY' ? (
              <td className="text-right tabular-nums" style={{ color: '#1e3a8a', fontWeight: 800 }}>{formatAmount(currentSegment.opProfit.actual)}</td>
            ) : (
              <>
                <td className="text-right tabular-nums">{formatAmount(isPeriod ? currentSegment.opProfit.ytdPlan : currentSegment.opProfit.plan)}</td>
                <td className="text-right tabular-nums" style={{ color: '#1e3a8a', fontWeight: 800 }}>{formatAmount(isPeriod ? currentSegment.opProfit.ytdActual : currentSegment.opProfit.actual)}</td>
                <td className={`text-right tabular-nums ${currentSegment.opProfit.variance >= 0 ? 'val-favorable' : 'val-unfavorable'}`} style={{ fontWeight: 800 }}>
                  {formatDiff(isPeriod ? (currentSegment.opProfit.ytdActual - currentSegment.opProfit.ytdPlan) : currentSegment.opProfit.variance)}
                </td>
              </>
            )}
          </tr>

          {/* 10. 영업이익률 */}
          <tr className="row-sublevel-1">
            <td className="text-left" style={{ color: '#1e40af' }}>• 영업이익률</td>
            <td className="text-center">%</td>
            {viewMode === 'ACTUAL_ONLY' ? (
              <td className="text-right tabular-nums" style={{ fontWeight: 700 }}>{currentSegment.opMargin.actual.toFixed(2)}%</td>
            ) : (
              <>
                <td className="text-right tabular-nums">{currentSegment.opMargin.plan.toFixed(2)}%</td>
                <td className="text-right tabular-nums" style={{ fontWeight: 700 }}>{currentSegment.opMargin.actual.toFixed(2)}%</td>
                <td className={`text-right tabular-nums ${currentSegment.opMargin.variance >= 0 ? 'val-favorable' : 'val-unfavorable'}`}>
                  {formatDiff(currentSegment.opMargin.variance, true)}
                </td>
              </>
            )}
          </tr>
        </tbody>
      </table>
    </div>
  );
};
