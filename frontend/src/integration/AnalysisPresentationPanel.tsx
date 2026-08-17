import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Sparkles, TrendingDown, TrendingUp, Package } from 'lucide-react';
import { EffectWaterfallChart } from '../components/variance/EffectWaterfallChart';
import { AnalysisPresentationDto, Role } from './types';
import {
  MappedPresentationEffect,
  MappedResidual,
  mapAnalysisPresentation,
  profitEffectTone,
} from './analysisPresentation';
import { EvidenceDownloadButton } from './EvidenceDownloadButton';
import '../styles/variance-analysis.css';

export function AnalysisPresentationPanel({
  value,
  role,
  onUnavailable,
}: {
  value: AnalysisPresentationDto;
  role: Role;
  onUnavailable?: () => void;
}) {
  const mapping = useMemo(() => mapAnalysisPresentation(value), [value]);
  const positiveEffects = useMemo(
    () => mapping.effects.filter((effect) => effect.profit_effect > 0),
    [mapping.effects],
  );
  const negativeEffects = useMemo(
    () => mapping.effects.filter((effect) => effect.profit_effect < 0),
    [mapping.effects],
  );
  const [selectedEffect, setSelectedEffect] = useState<string | undefined>(undefined);

  useEffect(() => {
    const available = new Set<string>([
      ...mapping.effects.map((effect) => effect.code),
      mapping.residual.code,
    ]);
    setSelectedEffect((previous) => previous && available.has(previous)
      ? previous
      : mapping.effects[0]?.code ?? mapping.residual.code);
  }, [mapping]);

  return (
    <article className="variance-analysis" data-testid="analysis-presentation">
      <PresentationHeader value={value} role={role} onUnavailable={onUnavailable} />
      <ExecutiveFacts
        positiveEffects={positiveEffects}
        negativeEffects={negativeEffects}
        residual={mapping.residual}
        kpiDelta={value.kpis.operating_profit_delta}
        selectedEffect={selectedEffect}
        onSelectEffect={setSelectedEffect}
      />
      <EffectWaterfallChart
        bars={mapping.waterfallBars}
        selectedEffectId={selectedEffect}
        onSelectEffect={setSelectedEffect}
      />
      <EffectTable
        effects={mapping.effects}
        residual={mapping.residual}
        effectsTotal={value.kpis.effects_total}
        selectedEffect={selectedEffect}
        onSelectEffect={setSelectedEffect}
      />
      <ProductGroupTable value={value} />
      <ManufacturingActivityTable value={value} />
    </article>
  );
}

function PresentationHeader({ value, role, onUnavailable }: { value: AnalysisPresentationDto; role: Role; onUnavailable?: () => void }) {
  const kpi = value.kpis;
  const tone = profitEffectTone(kpi.operating_profit_delta);
  const isPositive = kpi.operating_profit_delta >= 0;

  return (
    <section className="variance-analysis__hero" aria-labelledby="variance-result-title">
      <div className="variance-analysis__hero-main">
        <div className="variance-analysis__model-line" id="variance-result-title">
          <span className="variance-analysis__model-pill model-pill-plan">기준 모형: {value.identity.baseline_model_name}</span>
          <ArrowRight size={14} aria-hidden="true" color="#94a3b8" />
          <span className="variance-analysis__model-pill model-pill-actual">비교 모형: {value.identity.comparison_model_name}</span>
        </div>
        <div className="variance-analysis__identity-meta">
          {value.identity.start_month}월–{value.identity.end_month}월 · {value.currency_unit} · 결과 스키마 {value.identity.result_schema_version}
        </div>
        <div className="variance-analysis__op-summary">
          <span className="variance-analysis__summary-label">영업이익 증감</span>
          <strong className={`variance-analysis__summary-value variance-analysis__tone--${tone}`}>
            {formatMillions(kpi.operating_profit_delta, true)}
          </strong>
          <span
            className={isPositive ? 'badge-favorable' : 'badge-unfavorable'}
            style={{
              fontSize: '12px',
              padding: '2px 8px',
              borderRadius: '4px',
              fontWeight: 700,
              backgroundColor: isPositive ? '#dcfce7' : '#fee2e2',
              color: isPositive ? '#15803d' : '#b91c1c',
            }}
          >
            {isPositive ? '증익' : '감익'}
          </span>
        </div>
      </div>
      <div className="variance-analysis__hero-kpis" aria-label="영업이익 요약">
        <KpiLine label="기준 매출" value={kpi.baseline_revenue} />
        <KpiLine label="비교 매출" value={kpi.comparison_revenue} />
        <KpiLine label="매출 증감" value={kpi.revenue_delta} signed />
        <KpiLine label="기준 영업이익" value={kpi.baseline_operating_profit} />
        <KpiLine label="비교 영업이익" value={kpi.comparison_operating_profit} />
        <div className="variance-analysis__hero-evidence">
          <EvidenceDownloadButton resultId={value.identity.result_id} role={role} onUnavailable={onUnavailable} />
        </div>
      </div>
    </section>
  );
}

function KpiLine({ label, value, signed = false }: { label: string; value: number; signed?: boolean }) {
  return (
    <div className="variance-analysis__kpi-line">
      <span>{label}</span>
      <strong>{formatMillions(value, signed)}</strong>
    </div>
  );
}

function ExecutiveFacts({
  positiveEffects,
  negativeEffects,
  residual,
  kpiDelta,
  selectedEffect,
  onSelectEffect,
}: {
  positiveEffects: MappedPresentationEffect[];
  negativeEffects: MappedPresentationEffect[];
  residual: MappedResidual;
  kpiDelta: number;
  selectedEffect?: string;
  onSelectEffect: (code: string) => void;
}) {
  const isNetPositive = kpiDelta >= 0;

  return (
    <section className="variance-analysis__executive" aria-labelledby="executive-facts-title">
      <div className="variance-analysis__section-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #f1f5f9', paddingBottom: 14, marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 6, backgroundColor: '#eff6ff',
            display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #bfdbfe',
          }}>
            <Sparkles size={15} color="#2563eb" />
          </div>
          <h2 id="executive-facts-title" style={{ fontSize: '15px', fontWeight: 800, color: '#0f172a', margin: 0 }}>손익 분석 요약</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{
            fontSize: '12px', fontWeight: 700, padding: '3px 10px', borderRadius: 6,
            backgroundColor: '#f0fdf4', color: '#15803d', border: '1px solid #bbf7d0',
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            <TrendingUp size={12} />
            증익 요인 {positiveEffects.length}건
          </span>
          <span style={{
            fontSize: '12px', fontWeight: 700, padding: '3px 10px', borderRadius: 6,
            backgroundColor: '#fef2f2', color: '#b91c1c', border: '1px solid #fecaca',
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            <TrendingDown size={12} />
            감익 요인 {negativeEffects.length}건
          </span>
          <span style={{
            fontSize: '12px', fontWeight: 800, padding: '3px 10px', borderRadius: 6,
            backgroundColor: isNetPositive ? '#1e3a8a' : '#991b1b', color: '#ffffff',
          }}>
            순 손익 효과: {formatMillions(kpiDelta, true)}
          </span>
        </div>
      </div>
      <div className="variance-analysis__factor-grid">
        <FactorList title="긍정 요인" effects={positiveEffects} selectedEffect={selectedEffect} onSelectEffect={onSelectEffect} />
        <FactorList title="부정 요인" effects={negativeEffects} selectedEffect={selectedEffect} onSelectEffect={onSelectEffect} />
      </div>
      <div
        className={`variance-analysis__residual-summary variance-analysis__tone--${profitEffectTone(residual.amount)} ${selectedEffect === residual.code ? 'is-selected' : ''}`}
        style={{
          marginTop: '12px', padding: '8px 16px', backgroundColor: '#f8fafc',
          border: selectedEffect === residual.code ? '1.5px solid #2563eb' : '1px dashed #cbd5e1',
          borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 12,
        }}
      >
        <button
          type="button"
          aria-pressed={selectedEffect === residual.code}
          onClick={() => onSelectEffect(residual.code)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8, padding: '4px 12px',
            borderRadius: '4px', backgroundColor: selectedEffect === residual.code ? '#eff6ff' : '#ffffff',
            border: selectedEffect === residual.code ? '1.5px solid #2563eb' : '1px solid #cbd5e1',
            cursor: 'pointer', fontSize: '12.5px', fontWeight: 700, color: '#334155',
          }}
        >
          <Package size={13} color="#64748b" />
          <strong>{residual.uiLabel}</strong>
          <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>손익 영향</span>
          <span className={`variance-analysis__tone variance-analysis__tone--${profitEffectTone(residual.amount)}`}>
            {formatMillions(residual.amount, true)}
          </span>
        </button>
      </div>
    </section>
  );
}

function FactorList({
  title,
  effects,
  selectedEffect,
  onSelectEffect,
}: {
  title: string;
  effects: MappedPresentationEffect[];
  selectedEffect?: string;
  onSelectEffect: (code: string) => void;
}) {
  return (
    <div>
      <h3 className="variance-analysis__factor-title">{title}</h3>
      {effects.length ? effects.map((effect) => {
        const tone = profitEffectTone(effect.profit_effect);
        const isSelected = selectedEffect === effect.code;
        return (
          <button
            key={effect.code}
            type="button"
            className={`variance-analysis__factor-item variance-analysis__tone--${tone} ${isSelected ? 'is-selected' : ''}`}
            aria-pressed={isSelected}
            onClick={() => onSelectEffect(effect.code)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{
                width: 7, height: 7, borderRadius: '50%',
                backgroundColor: tone === 'positive' ? '#10b981' : tone === 'negative' ? '#f43f5e' : '#94a3b8',
                display: 'inline-block', flexShrink: 0,
              }} />
              <span>{effect.uiLabel}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
              <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>손익 영향</span>
              <strong className={`variance-analysis__tone variance-analysis__tone--${tone}`}>
                {formatMillions(effect.profit_effect, true)}
              </strong>
            </div>
          </button>
        );
      }) : <div className="variance-analysis__factor-empty">해당 Effect 없음</div>}
    </div>
  );
}

function EffectTable({
  effects,
  residual,
  effectsTotal,
  selectedEffect,
  onSelectEffect,
}: {
  effects: MappedPresentationEffect[];
  residual: MappedResidual;
  effectsTotal: number;
  selectedEffect?: string;
  onSelectEffect: (code: string) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  return (
    <section className="variance-analysis__effect-section" data-testid="effect-table">
      <div className="variance-analysis__section-header">
        <h2>Effect 상세 / Drilldown</h2>
        <span>금액 단위: 백만원 · 상세 값은 서버 DTO 그대로 표시</span>
      </div>
      <div className="variance-analysis__table-scroll">
        <table className="financial-table variance-analysis__effect-table">
          <thead><tr>
            <th>구분</th><th>손익 변동 원인</th><th>단위</th><th className="text-right">기준</th><th className="text-right">비교</th><th className="text-right">원인변동</th><th className="text-right">손익 영향 금액</th><th>근거</th>
          </tr></thead>
          <tbody>
            {effects.map((effect) => {
              const open = Boolean(expanded[effect.code]);
              return (
                <EffectRow
                  key={effect.code}
                  effect={effect}
                  open={open}
                  selected={selectedEffect === effect.code}
                  onSelect={() => onSelectEffect(effect.code)}
                  onToggle={() => setExpanded((state) => ({ ...state, [effect.code]: !open }))}
                />
              );
            })}
            <tr className="row-total">
              <td colSpan={6}>Effect 총액 (서버)</td>
              <td className="text-right tabular-nums">{formatMillions(effectsTotal, true)}</td>
              <td>서버 제공 effects_total</td>
            </tr>
            <tr data-testid="effect-row-residual" className={selectedEffect === residual.code ? 'row-active' : ''}>
              <td>기타</td>
              <td>
                <button
                  type="button"
                  className="variance-analysis__effect-select"
                  data-testid="effect-select-residual"
                  aria-pressed={selectedEffect === residual.code}
                  onClick={() => onSelectEffect(residual.code)}
                >
                  {residual.uiLabel}
                </button>
              </td>
              <td>백만원</td>
              <td className="text-right">—</td>
              <td className="text-right">—</td>
              <td className="text-right">—</td>
              <td data-testid="effect-tone-residual" className={`text-right tabular-nums variance-analysis__tone--${profitEffectTone(residual.amount)}`}>{formatMillions(residual.amount, true)}</td>
              <td>—</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EffectRow({
  effect,
  open,
  selected,
  onSelect,
  onToggle,
}: {
  effect: MappedPresentationEffect;
  open: boolean;
  selected: boolean;
  onSelect: () => void;
  onToggle: () => void;
}) {
  const available = effect.drilldown.available;
  const tone = profitEffectTone(effect.profit_effect);
  return (
    <>
      <tr data-testid={`effect-row-${effect.code}`} className={`${selected ? 'row-active' : ''} variance-analysis__effect-row--${tone}`}>
        <td>{effect.uiCategoryLabel}</td>
        <td>
          <button
            type="button"
            className="expand-toggle-btn"
            disabled={!available}
            aria-label={`${effect.uiLabel} ${available ? (open ? '상세 접기' : '상세 펼치기') : '상세 근거 없음'}`}
            onClick={onToggle}
          >
            {available ? (open ? <ChevronDown size={13} aria-hidden="true" /> : <ChevronRight size={13} aria-hidden="true" />) : <AlertTriangle size={13} aria-hidden="true" />}
          </button>
          <button
            type="button"
            className="variance-analysis__effect-select"
            data-testid={`effect-select-${effect.code}`}
            aria-pressed={selected}
            onClick={onSelect}
          >
            {effect.uiLabel}
          </button>
        </td>
        <td>백만원</td>
        <td className="text-right">—</td>
        <td className="text-right">—</td>
        <td className="text-right">—</td>
        <td data-testid={`effect-tone-${effect.code}`} className={`text-right tabular-nums variance-analysis__tone--${tone}`}>{formatMillions(effect.profit_effect, true)}</td>
        <td>{available ? effect.description : effect.drilldown.unavailable_reason}</td>
      </tr>
      {open && available && (
        <tr>
          <td colSpan={8} className="variance-analysis__drilldown-cell">
            <table className="drilldown-table variance-analysis__drilldown-table">
              <thead><tr>
                <th>구분</th><th>근거 항목</th><th>단위</th><th className="text-right">기준</th><th className="text-right">비교</th><th className="text-right">증감</th><th className="text-right">손익 영향</th><th>비고</th>
              </tr></thead>
              <tbody>{effect.drilldown.rows.map((row) => (
                <tr key={row.row_id}>
                  <td>{effect.uiCategoryLabel}</td>
                  <td>{effect.code.startsWith('sga') ? formatSgaLabel(row.label) : row.label}</td>
                  <td>{row.unit === 'KRW' ? '백만원' : row.unit}</td>
                  <td className="text-right">{displayDrilldownValue(row.baseline, row.unit)}</td>
                  <td className="text-right">{displayDrilldownValue(row.comparison, row.unit)}</td>
                  <td className="text-right">{displayDrilldownValue(row.delta, row.unit, true)}</td>
                  <td className={`text-right ${row.profit_effect === null ? '' : `variance-analysis__tone--${profitEffectTone(row.profit_effect)}`}`}>{row.profit_effect === null ? '—' : formatMillions(row.profit_effect, true)}</td>
                  <td>{row.note}</td>
                </tr>
              ))}</tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

function ProductGroupTable({ value }: { value: AnalysisPresentationDto }) {
  if (!value.product_groups.length) return null;
  return (
    <section className="variance-analysis__evidence-table" aria-labelledby="product-groups-title">
      <div className="variance-analysis__section-header"><h2 id="product-groups-title">제품군 근거</h2><span>수량 단위는 DTO 값 유지 · 금액 단위: 백만원</span></div>
      <div className="variance-analysis__table-scroll"><table className="financial-table"><thead><tr>
        <th>제품군</th><th>수량 단위</th><th className="text-right">기준 수량</th><th className="text-right">비교 수량</th><th className="text-right">기준 매출</th><th className="text-right">비교 매출</th>
      </tr></thead><tbody>{value.product_groups.map((row) => (
        <tr key={row.code}><td>{row.display_name}</td><td>{row.quantity_unit}</td><td className="text-right">{formatNumber(row.baseline_quantity)}</td><td className="text-right">{formatNumber(row.comparison_quantity)}</td><td className="text-right">{formatMillions(row.baseline_revenue)}</td><td className="text-right">{formatMillions(row.comparison_revenue)}</td></tr>
      ))}</tbody></table></div>
    </section>
  );
}

function ManufacturingActivityTable({ value }: { value: AnalysisPresentationDto }) {
  if (!value.manufacturing_activities.length) return null;
  return (
    <section className="variance-analysis__evidence-table" aria-labelledby="manufacturing-activity-title">
      <div className="variance-analysis__section-header"><h2 id="manufacturing-activity-title">제조 조업도 근거</h2><span>PCS / m 단위는 DTO 값 유지</span></div>
      <div className="variance-analysis__table-scroll"><table className="financial-table"><thead><tr>
        <th>공정</th><th>Basis</th><th>단위</th><th className="text-right">기준</th><th className="text-right">비교</th><th className="text-right">증감</th>
      </tr></thead><tbody>{value.manufacturing_activities.map((row) => (
        <tr key={`${row.process}:${row.production_basis}`}><td>{row.process}</td><td>{row.production_basis}</td><td>{row.unit}</td><td className="text-right">{formatNumber(row.baseline)}</td><td className="text-right">{formatNumber(row.comparison)}</td><td className="text-right">{formatNumber(row.delta, true)}</td></tr>
      ))}</tbody></table></div>
    </section>
  );
}

function formatMillions(krwValue: number, signed = false): string {
  const millions = Math.round(krwValue / 1_000_000);
  const formatted = millions.toLocaleString('ko-KR');
  return `${signed && millions > 0 ? '+' : ''}${formatted} 백만원`;
}

function formatSgaLabel(label: string): string {
  if (label.includes('판매비 소계') || label.includes('판매비소계')) return '판매비 소계';
  if (label.includes('일반관리비 소계') || label.includes('일반관리비소계')) return '일반관리비 소계';
  if (label.includes('판관비 총계') || label.includes('판관비총계') || label.includes('판매관리비 총계')) return '판관비 총계';

  const clean = label.replace(/^\d+\.\s*/, '').trim();
  if (clean.startsWith('판매비_') || clean.startsWith('일반관리비_')) return clean;

  const sellingKeywords = ['운반비', '수수료', '보관료', '광고선전비', '판매', '수출비', '포장비'];
  const isSelling = sellingKeywords.some((k) => clean.includes(k));
  return isSelling ? `판매비_${clean}` : `일반관리비_${clean}`;
}

function formatNumber(value: number, signed = false): string {
  return `${signed && value > 0 ? '+' : ''}${value.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}`;
}

function displayNullable(value: number | null, signed = false): string {
  return value === null ? '—' : formatNumber(value, signed);
}

function displayDrilldownValue(value: number | null, unit: string, signed = false): string {
  if (value === null) return '—';
  return unit === 'KRW' ? formatMillions(value, signed) : formatNumber(value, signed);
}
