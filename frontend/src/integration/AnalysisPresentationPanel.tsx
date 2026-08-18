import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Package, Sparkles } from 'lucide-react';
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

type EffectGroupKey = 'sales' | 'fx' | 'cost';

interface EffectGroup {
  key: EffectGroupKey;
  title: string;
  categoryLabel: string;
  effects: MappedPresentationEffect[];
}

const EFFECT_GROUPS: Array<{ key: EffectGroupKey; title: string; categoryLabel: string; codes: Array<MappedPresentationEffect['code']> }> = [
  { key: 'sales', title: '판매 효과', categoryLabel: '내부', codes: ['sales_quantity', 'sales_price'] },
  { key: 'fx', title: '환율 효과', categoryLabel: '외부', codes: ['sales_fx'] },
  {
    key: 'cost',
    title: '비용 효과',
    categoryLabel: '비용',
    codes: ['material_total', 'sga_variable', 'sga_fixed', 'manufacturing_realized', 'inventory_timing'],
  },
];

function groupEffects(effects: MappedPresentationEffect[]): EffectGroup[] {
  const byCode = new Map(effects.map((effect) => [effect.code, effect]));
  return EFFECT_GROUPS.map((definition) => {
    const grouped = definition.codes
      .map((code) => byCode.get(code))
      .filter((effect): effect is MappedPresentationEffect => Boolean(effect));
    return { ...definition, effects: grouped };
  });
}

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
  const groups = useMemo(() => groupEffects(mapping.effects), [mapping.effects]);
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
      <ExecutiveNarrative
        groups={groups}
        effects={mapping.effects}
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
      <AdditionalEvidence value={value} />
    </article>
  );
}

function PresentationHeader({ value, role, onUnavailable }: { value: AnalysisPresentationDto; role: Role; onUnavailable?: () => void }) {
  const kpi = value.kpis;
  const tone = profitEffectTone(kpi.operating_profit_delta);
  const isPositive = kpi.operating_profit_delta >= 0;

  return (
    <section className="variance-analysis__hero" data-testid="analysis-summary-header" aria-labelledby="variance-result-title">
      <div className="variance-analysis__hero-main">
        <div className="variance-analysis__model-line" id="variance-result-title">
          <span className="variance-analysis__model-pill model-pill-plan">기준 모형: {value.identity.baseline_model_name}</span>
          <ArrowRight size={14} aria-hidden="true" color="#94a3b8" />
          <span className="variance-analysis__model-pill model-pill-actual">비교 모형: {value.identity.comparison_model_name}</span>
        </div>
        <div className="variance-analysis__identity-meta">
          {value.identity.start_month}월–{value.identity.end_month}월 · {value.currency_unit} · 결과 스키마 {value.identity.result_schema_version}
        </div>
      </div>
      <div className="variance-analysis__summary-kpis" aria-label="영업이익 요약">
        <KpiLine label="기준 영업이익" value={kpi.baseline_operating_profit} />
        <KpiLine label="비교 영업이익" value={kpi.comparison_operating_profit} />
        <div className={`variance-analysis__delta-box variance-analysis__tone--${tone}`}>
          <span className="variance-analysis__summary-label">영업이익 증감</span>
          <strong className="variance-analysis__summary-value">{formatMillions(kpi.operating_profit_delta, true)}</strong>
          <span className={`variance-analysis__delta-badge ${isPositive ? 'is-positive' : 'is-negative'}`}>
            {isPositive ? '증익' : '감익'}
          </span>
        </div>
        <EvidenceDownloadButton resultId={value.identity.result_id} role={role} onUnavailable={onUnavailable} />
      </div>
    </section>
  );
}

function KpiLine({ label, value }: { label: string; value: number }) {
  return (
    <div className="variance-analysis__kpi-line">
      <span>{label}</span>
      <strong>{formatMillions(value)}</strong>
    </div>
  );
}

function ExecutiveNarrative({
  groups,
  effects,
  residual,
  kpiDelta,
  selectedEffect,
  onSelectEffect,
}: {
  groups: EffectGroup[];
  effects: MappedPresentationEffect[];
  residual: MappedResidual;
  kpiDelta: number;
  selectedEffect?: string;
  onSelectEffect: (code: string) => void;
}) {
  const positiveCount = effects.filter((effect) => effect.profit_effect > 0).length;
  const negativeCount = effects.filter((effect) => effect.profit_effect < 0).length;
  const isNetPositive = kpiDelta >= 0;

  return (
    <section className="variance-analysis__executive" data-testid="analysis-executive-narrative" aria-labelledby="executive-facts-title">
      <div className="variance-analysis__executive-header">
        <div className="variance-analysis__executive-title">
          <span className="variance-analysis__executive-icon" aria-hidden="true"><Sparkles size={15} /></span>
          <h2 id="executive-facts-title">손익 분석 요약</h2>
        </div>
        <div className="variance-analysis__executive-badges" aria-label="손익 효과 요약">
          <span className="variance-analysis__summary-badge is-positive">증익 요인 {positiveCount}건</span>
          <span className="variance-analysis__summary-badge is-negative">감익 요인 {negativeCount}건</span>
          <span className={`variance-analysis__summary-badge is-net-${isNetPositive ? 'positive' : 'negative'}`}>
            순 손익 효과: {formatMillions(kpiDelta, true)}
          </span>
        </div>
      </div>
      <div className="variance-analysis__narrative-grid">
        {groups.map((group) => (
          <section key={group.key} className="variance-analysis__narrative-group" data-testid={`analysis-effect-group-${group.key}`}>
            <div className="variance-analysis__narrative-group-header">
              <div>
                <h3>{group.title}</h3>
                <span>{group.categoryLabel}</span>
              </div>
            </div>
            {group.effects.length ? group.effects.map((effect) => {
              const tone = profitEffectTone(effect.profit_effect);
              const isSelected = selectedEffect === effect.code;
              return (
                <button
                  key={effect.code}
                  type="button"
                  className={`variance-analysis__narrative-effect variance-analysis__tone--${tone} ${isSelected ? 'is-selected' : ''}`}
                  aria-pressed={isSelected}
                  onClick={() => onSelectEffect(effect.code)}
                >
                  <span className="variance-analysis__narrative-effect-label">{effect.uiLabel}</span>
                  <strong>{formatMillions(effect.profit_effect, true)}</strong>
                </button>
              );
            }) : <div className="variance-analysis__narrative-empty">해당 Effect 없음</div>}
          </section>
        ))}
      </div>
      <div className={`variance-analysis__residual-summary ${selectedEffect === residual.code ? 'is-selected' : ''}`}>
        <button
          type="button"
          aria-pressed={selectedEffect === residual.code}
          onClick={() => onSelectEffect(residual.code)}
          className="variance-analysis__residual-button"
        >
          <Package size={13} aria-hidden="true" />
          <strong>{residual.uiLabel}</strong>
          <span>손익 영향</span>
          <b className={`variance-analysis__tone--${profitEffectTone(residual.amount)}`}>{formatMillions(residual.amount, true)}</b>
        </button>
      </div>
    </section>
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

  useEffect(() => {
    setExpanded((previous) => {
      const availableCodes = new Set<string>(effects.filter((effect) => effect.drilldown.available).map((effect) => effect.code));
      const retained = Object.fromEntries(
        Object.entries(previous).filter(([code, isOpen]) => isOpen && availableCodes.has(code)),
      );
      if (Object.keys(retained).length > 0) return retained;
      const firstAvailable = effects.find((effect) => effect.drilldown.available);
      return firstAvailable ? { [firstAvailable.code]: true } : {};
    });
  }, [effects]);

  return (
    <section className="variance-analysis__effect-section variance-analysis__detail-shell" data-testid="analysis-detail-section" aria-labelledby="analysis-detail-section-title">
      <div data-testid="effect-table">
        <div className="variance-analysis__section-header">
          <div>
            <h2 id="analysis-detail-section-title">손익 변동 상세</h2>
            <span>금액 단위: 백만원 · 상세 값은 서버 DTO 그대로 표시</span>
          </div>
        </div>
        <div className="variance-analysis__table-scroll">
          <table className="financial-table variance-analysis__effect-table">
            <thead className="variance-analysis__table-head"><tr>
              <th>구분</th><th>손익 변동 원인</th><th>단위</th><th>기준</th><th>비교</th><th>원인변동</th><th>손익 영향 금액</th><th>근거</th>
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
                <td>기타 요인</td>
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
                <td>서버 제공 기타 요인</td>
              </tr>
            </tbody>
          </table>
        </div>
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
            aria-expanded={available ? open : undefined}
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
              <thead className="variance-analysis__table-head"><tr>
                <th>구분</th><th>근거 항목</th><th>단위</th><th>기준</th><th>비교</th><th>증감</th><th>손익 영향</th>
              </tr></thead>
              <tbody>{effect.drilldown.rows.map((row) => (
                <tr key={row.row_id}>
                  <td>{effect.uiCategoryLabel}</td>
                  <td>{effect.code.startsWith('sga') && !row.row_id.startsWith('manufacturing:') ? formatSgaLabel(row.label) : row.label}</td>
                  <td>{row.unit === 'KRW' ? '백만원' : row.unit}</td>
                  <td className="text-right">{displayDrilldownValue(row.baseline, row.unit)}</td>
                  <td className="text-right">{displayDrilldownValue(row.comparison, row.unit)}</td>
                  <td className="text-right">{displayDrilldownValue(row.delta, row.unit, true)}</td>
                  <td className={`text-right ${row.profit_effect === null ? '' : `variance-analysis__tone--${profitEffectTone(row.profit_effect)}`}`}>{row.profit_effect === null ? '—' : formatMillions(row.profit_effect, true)}</td>
                </tr>
              ))}</tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

function AdditionalEvidence({ value }: { value: AnalysisPresentationDto }) {
  if (!value.product_groups.length && !value.manufacturing_activities.length) return null;
  return (
    <section className="variance-analysis__additional-evidence" data-testid="analysis-additional-evidence" aria-labelledby="analysis-additional-evidence-title">
      <div className="variance-analysis__additional-evidence-header">
        <h2 id="analysis-additional-evidence-title">추가 근거</h2>
        <span>서버가 제공한 판매 수량/매출·생산 수량 근거</span>
      </div>
      <div className="variance-analysis__additional-evidence-grid">
        <ProductGroupTable value={value} />
        <ManufacturingActivityTable value={value} />
      </div>
    </section>
  );
}

function ProductGroupTable({ value }: { value: AnalysisPresentationDto }) {
  if (!value.product_groups.length) return null;
  return (
    <section className="variance-analysis__evidence-table variance-analysis__evidence-table--product" aria-labelledby="product-groups-title">
      <div className="variance-analysis__section-header"><h3 id="product-groups-title">판매 수량/매출</h3><span>수량 단위는 DTO 값 유지 · 금액 단위: 백만원</span></div>
      <div className="variance-analysis__table-scroll"><table className="financial-table"><thead className="variance-analysis__table-head"><tr>
        <th>제품군</th><th>수량 단위</th><th>기준 수량</th><th>비교 수량</th><th>기준 매출</th><th>비교 매출</th>
      </tr></thead><tbody>{value.product_groups.map((row) => (
        <tr key={row.code}><td>{row.display_name}</td><td>{row.quantity_unit}</td><td className="text-right">{formatQuantity(row.baseline_quantity)}</td><td className="text-right">{formatQuantity(row.comparison_quantity)}</td><td className="text-right">{formatMillions(row.baseline_revenue)}</td><td className="text-right">{formatMillions(row.comparison_revenue)}</td></tr>
      ))}</tbody></table></div>
    </section>
  );
}

function ManufacturingActivityTable({ value }: { value: AnalysisPresentationDto }) {
  if (!value.manufacturing_activities.length) return null;
  return (
    <section className="variance-analysis__evidence-table variance-analysis__evidence-table--activity" aria-labelledby="manufacturing-activity-title">
      <div className="variance-analysis__section-header"><h3 id="manufacturing-activity-title">생산 수량</h3><span>PCS / m 단위는 DTO 값 유지</span></div>
      <div className="variance-analysis__table-scroll"><table className="financial-table"><thead className="variance-analysis__table-head"><tr>
        <th>공정</th><th>Basis</th><th>단위</th><th>기준</th><th>비교</th><th>증감</th>
      </tr></thead><tbody>{value.manufacturing_activities.map((row) => (
        <tr key={`${row.process}:${row.production_basis}`}><td>{row.process}</td><td>{row.production_basis}</td><td>{row.unit}</td><td className="text-right">{formatQuantity(row.baseline)}</td><td className="text-right">{formatQuantity(row.comparison)}</td><td className="text-right">{formatQuantity(row.delta, true)}</td></tr>
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

export function formatQuantity(value: number, signed = false): string {
  const formatted = value.toLocaleString('ko-KR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
  return `${signed && value > 0 ? '+' : ''}${formatted}`;
}

function displayDrilldownValue(value: number | null, unit: string, signed = false): string {
  if (value === null) return '—';
  return unit === 'KRW' ? formatMillions(value, signed) : formatQuantity(value, signed);
}
