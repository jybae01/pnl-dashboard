import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight } from 'lucide-react';
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
      <PresentationHeader value={value} />
      <ExecutiveFacts
        positiveEffects={mapping.topPositiveEffects}
        negativeEffects={mapping.topNegativeEffects}
        residual={mapping.residual}
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
      <EvidenceAccess value={value} role={role} onUnavailable={onUnavailable} />
    </article>
  );
}

function PresentationHeader({ value }: { value: AnalysisPresentationDto }) {
  const kpi = value.kpis;
  const tone = profitEffectTone(kpi.operating_profit_delta);
  return (
    <section className="variance-analysis__hero" aria-labelledby="variance-result-title">
      <div className="variance-analysis__hero-main">
        <div className="variance-analysis__model-line" id="variance-result-title">
          <span className="variance-analysis__model-pill">기준 모형: {value.identity.baseline_model_name}</span>
          <ArrowRight size={14} aria-hidden="true" />
          <span className="variance-analysis__model-pill">비교 모형: {value.identity.comparison_model_name}</span>
        </div>
        <div className="variance-analysis__identity-meta">
          {value.identity.start_month}월–{value.identity.end_month}월 · {value.currency_unit} · 결과 스키마 {value.identity.result_schema_version}
        </div>
        <div className="variance-analysis__op-summary">
          <span className="variance-analysis__summary-label">영업이익 증감</span>
          <strong className={`variance-analysis__summary-value variance-analysis__tone--${tone}`}>
            {formatMillions(kpi.operating_profit_delta, true)}
          </strong>
        </div>
      </div>
      <div className="variance-analysis__hero-kpis" aria-label="영업이익 요약">
        <KpiLine label="기준 매출" value={kpi.baseline_revenue} />
        <KpiLine label="비교 매출" value={kpi.comparison_revenue} />
        <KpiLine label="매출 증감" value={kpi.revenue_delta} signed />
        <KpiLine label="기준 영업이익" value={kpi.baseline_operating_profit} />
        <KpiLine label="비교 영업이익" value={kpi.comparison_operating_profit} />
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
  selectedEffect,
  onSelectEffect,
}: {
  positiveEffects: MappedPresentationEffect[];
  negativeEffects: MappedPresentationEffect[];
  residual: MappedResidual;
  selectedEffect?: string;
  onSelectEffect: (code: string) => void;
}) {
  return (
    <section className="variance-analysis__executive" aria-labelledby="executive-facts-title">
      <div className="variance-analysis__section-header">
        <h2 id="executive-facts-title">경영진 분석 요약</h2>
        <span>서버가 제공한 주요 요인과 기타 요인만 표시</span>
      </div>
      <div className="variance-analysis__factor-grid">
        <FactorList title="긍정 요인" effects={positiveEffects} selectedEffect={selectedEffect} onSelectEffect={onSelectEffect} />
        <FactorList title="부정 요인" effects={negativeEffects} selectedEffect={selectedEffect} onSelectEffect={onSelectEffect} />
      </div>
      <div className={`variance-analysis__residual-summary variance-analysis__tone--${profitEffectTone(residual.amount)}`}>
        <strong>{residual.uiLabel}</strong>
        <span>{formatMillions(residual.amount, true)}</span>
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
        return (
          <button
            key={effect.code}
            type="button"
            className={`variance-analysis__factor-item variance-analysis__tone--${tone} ${selectedEffect === effect.code ? 'is-selected' : ''}`}
            aria-pressed={selectedEffect === effect.code}
            onClick={() => onSelectEffect(effect.code)}
          >
            <span>{effect.uiLabel}</span>
            <strong>{formatMillions(effect.profit_effect, true)}</strong>
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
            <th>Effect</th><th>분류</th><th className="text-right">손익 영향</th><th>근거</th>
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
              <td colSpan={2}>Effect 총액 (서버)</td>
              <td className="text-right tabular-nums">{formatMillions(effectsTotal, true)}</td>
              <td>서버 제공 effects_total</td>
            </tr>
            <tr data-testid="effect-row-residual" className={selectedEffect === residual.code ? 'row-active' : ''}>
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
              <td>—</td>
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
        <td>{effect.uiCategoryLabel}</td>
        <td data-testid={`effect-tone-${effect.code}`} className={`text-right tabular-nums variance-analysis__tone--${tone}`}>{formatMillions(effect.profit_effect, true)}</td>
        <td>{available ? effect.description : effect.drilldown.unavailable_reason}</td>
      </tr>
      {open && available && (
        <tr>
          <td colSpan={4} className="variance-analysis__drilldown-cell">
            <table className="drilldown-table variance-analysis__drilldown-table">
              <thead><tr>
                <th>근거 항목</th><th>단위</th><th className="text-right">기준</th><th className="text-right">비교</th><th className="text-right">증감</th><th className="text-right">손익 영향</th><th>비고</th>
              </tr></thead>
              <tbody>{effect.drilldown.rows.map((row) => (
                <tr key={row.row_id}>
                  <td>{effect.code.startsWith('sga') ? formatSgaLabel(row.label) : row.label}</td>
                  <td>{row.unit}</td>
                  <td className="text-right">{displayNullable(row.baseline)}</td>
                  <td className="text-right">{displayNullable(row.comparison)}</td>
                  <td className="text-right">{displayNullable(row.delta, true)}</td>
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

function EvidenceAccess({ value, role, onUnavailable }: { value: AnalysisPresentationDto; role: Role; onUnavailable?: () => void }) {
  return (
    <section className="variance-analysis__evidence-access" aria-labelledby="evidence-access-title">
      <div><h2 id="evidence-access-title">분석 근거 접근</h2><p>현재 결과에 연결된 Backend 증빙을 내려받습니다.</p></div>
      <EvidenceDownloadButton resultId={value.identity.result_id} role={role} onUnavailable={onUnavailable} />
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
