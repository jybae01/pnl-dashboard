import { useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';
import { EffectWaterfallChart } from '../components/variance/EffectWaterfallChart';
import { WaterfallBarData } from '../types/variance';
import { AnalysisPresentationDto, AnalysisPresentationEffectDto, Role } from './types';
import { EvidenceDownloadButton } from './EvidenceDownloadButton';

const MILLION = 1_000_000;

export function AnalysisPresentationPanel({
  value,
  role,
  onUnavailable,
}: {
  value: AnalysisPresentationDto;
  role: Role;
  onUnavailable?: () => void;
}) {
  const [selectedEffect, setSelectedEffect] = useState<string | undefined>(value.effects[0]?.code);
  const bars = useMemo(() => waterfallBars(value), [value]);
  return <article data-testid="analysis-presentation" style={{ marginTop: 12 }}>
    <PresentationHeader value={value} role={role} onUnavailable={onUnavailable} />
    <ExecutiveFacts value={value} />
    <EffectWaterfallChart bars={bars} selectedEffectId={selectedEffect} onSelectEffect={setSelectedEffect} />
    <EffectTable effects={value.effects} residual={value.residual} effectsTotal={value.kpis.effects_total}
      selectedEffect={selectedEffect} onSelectEffect={setSelectedEffect} />
    <ProductGroupTable value={value} />
    <ManufacturingActivityTable value={value} />
  </article>;
}

function PresentationHeader({ value, role, onUnavailable }: {
  value: AnalysisPresentationDto; role: Role; onUnavailable?: () => void;
}) {
  const kpi = value.kpis;
  const positive = kpi.operating_profit_delta >= 0;
  return <div className="variance-hero-banner" style={{ marginBottom: 14 }}>
    <div className="variance-hero-left">
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="model-pill model-pill-plan">Base: {value.identity.baseline_model_name}</span>
          <ArrowRight size={13} color="#94a3b8" />
          <span className="model-pill model-pill-actual">Comparison: {value.identity.comparison_model_name}</span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 5 }}>
          {value.identity.start_month}월–{value.identity.end_month}월 · Base FX {formatNumber(value.identity.baseline_sales_fx)} · Comparison FX {formatNumber(value.identity.comparison_sales_fx)} · schema {value.identity.result_schema_version}
        </div>
      </div>
      <div className="variance-hero-score">
        <div>
          <div className="score-label">영업이익 증감</div>
          <div className="score-amount tabular-nums" style={{ color: positive ? 'var(--color-favorable)' : 'var(--color-unfavorable)' }}>
            {formatMillion(kpi.operating_profit_delta, true)}
          </div>
        </div>
      </div>
    </div>
    <div style={{ display: 'grid', gap: 7, borderLeft: '1px solid var(--border-subtle)', paddingLeft: 16 }}>
      <KpiLine label="Base 매출" value={kpi.baseline_revenue} />
      <KpiLine label="Comparison 매출" value={kpi.comparison_revenue} />
      <KpiLine label="매출 증감" value={kpi.revenue_delta} signed />
      <KpiLine label="Base 영업이익" value={kpi.baseline_operating_profit} />
      <KpiLine label="Comparison 영업이익" value={kpi.comparison_operating_profit} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#15803d', fontSize: 11, fontWeight: 700 }}>
        <ShieldCheck size={13} /> Effects {formatMillion(kpi.effects_total, true)} + Residual {formatMillion(kpi.residual, true)} = OP Delta
      </div>
      <EvidenceDownloadButton resultId={value.identity.result_id} role={role} onUnavailable={onUnavailable} />
    </div>
  </div>;
}

function KpiLine({ label, value, signed = false }: { label: string; value: number; signed?: boolean }) {
  return <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, fontSize: 11 }}>
    <span style={{ color: 'var(--text-muted)' }}>{label}</span>
    <strong className="tabular-nums">{formatMillion(value, signed)}</strong>
  </div>;
}

function ExecutiveFacts({ value }: { value: AnalysisPresentationDto }) {
  return <section className="narrative-card" aria-labelledby="executive-facts-title">
    <div className="narrative-header">
      <strong id="executive-facts-title">결정론적 주요 Fact</strong>
      <span className="unit-tag">AI narrative 아님</span>
    </div>
    <div className="narrative-text">영업이익 증감 {formatMillion(value.executive_summary.operating_profit_delta, true)}</div>
    <div className="factor-tags-grid">
      <FactorList title="주요 Positive Effect" effects={value.executive_summary.top_positive_effects} />
      <FactorList title="주요 Negative Effect" effects={value.executive_summary.top_negative_effects} />
    </div>
    <div style={{ marginTop: 10, fontSize: 11, color: '#475569' }}>
      Residual: {formatMillion(value.residual.amount, true)} · {value.residual.display_label} ({value.residual.classification})
    </div>
  </section>;
}

function FactorList({ title, effects }: { title: string; effects: AnalysisPresentationEffectDto[] }) {
  return <div><div className="factor-col-title">{title}</div>{effects.length
    ? effects.map((effect) => <div className="factor-item" key={effect.code}>{effect.label}: {formatMillion(effect.profit_effect, true)}</div>)
    : <div className="factor-item">해당 Effect 없음</div>}</div>;
}

function EffectTable({ effects, residual, effectsTotal, selectedEffect, onSelectEffect }: {
  effects: AnalysisPresentationEffectDto[];
  residual: AnalysisPresentationDto['residual'];
  effectsTotal: number;
  selectedEffect?: string;
  onSelectEffect: (code: string) => void;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  return <section className="financial-table-container" style={{ marginBottom: 16 }}>
    <div style={{ padding: '10px 14px', fontWeight: 700 }}>Canonical Effect 상세</div>
    <table className="financial-table"><thead><tr>
      <th>Effect</th><th>분류</th><th className="text-right">손익 영향</th><th>근거</th>
    </tr></thead><tbody>
      {effects.map((effect) => {
        const open = Boolean(expanded[effect.code]);
        return <FragmentRow key={effect.code} effect={effect} open={open} selected={selectedEffect === effect.code}
          onSelect={() => onSelectEffect(effect.code)} onToggle={() => setExpanded((state) => ({ ...state, [effect.code]: !open }))} />;
      })}
      <tr className="row-total"><td colSpan={2}>Effects 합계</td><td className="text-right tabular-nums">{formatMillion(effectsTotal, true)}</td><td>Backend canonical total</td></tr>
      <tr><td>Residual</td><td>{residual.classification}</td><td className="text-right tabular-nums">{formatMillion(residual.amount, true)}</td><td>{residual.display_label}</td></tr>
    </tbody></table>
  </section>;
}

function FragmentRow({ effect, open, selected, onSelect, onToggle }: {
  effect: AnalysisPresentationEffectDto; open: boolean; selected: boolean; onSelect: () => void; onToggle: () => void;
}) {
  return <>
    <tr className={selected ? 'row-active' : ''}>
      <td><button type="button" className="expand-toggle-btn" disabled={!effect.drilldown.available} onClick={onToggle}>
        {effect.drilldown.available ? (open ? <ChevronDown size={13} /> : <ChevronRight size={13} />) : <AlertTriangle size={13} />}
      </button><button type="button" className="btn-link" onClick={onSelect}>{effect.label}</button></td>
      <td>{effect.category}</td>
      <td className={`text-right tabular-nums ${effect.profit_effect >= 0 ? 'val-favorable' : 'val-unfavorable'}`}>{formatMillion(effect.profit_effect, true)}</td>
      <td>{effect.drilldown.available ? effect.description : effect.drilldown.unavailable_reason}</td>
    </tr>
    {open && effect.drilldown.available && <tr><td colSpan={4} style={{ padding: 0 }}><table className="drilldown-table"><thead><tr>
      <th>근거 항목</th><th>단위</th><th className="text-right">Base</th><th className="text-right">Comparison</th><th className="text-right">Delta</th><th className="text-right">Effect</th><th>비고</th>
    </tr></thead><tbody>{effect.drilldown.rows.map((row) => <tr key={row.row_id}>
      <td>{row.label}</td><td>{row.unit}</td><td className="text-right">{displayNullable(row.baseline, row.unit)}</td>
      <td className="text-right">{displayNullable(row.comparison, row.unit)}</td><td className="text-right">{displayNullable(row.delta, row.unit)}</td>
      <td className="text-right">{row.profit_effect === null ? '—' : formatMillion(row.profit_effect, true)}</td><td>{row.note}</td>
    </tr>)}</tbody></table></td></tr>}
  </>;
}

function ProductGroupTable({ value }: { value: AnalysisPresentationDto }) {
  if (!value.product_groups.length) return null;
  return <section className="financial-table-container" style={{ marginBottom: 16 }}><div style={{ padding: '10px 14px', fontWeight: 700 }}>제품군</div>
    <table className="financial-table"><thead><tr><th>제품군</th><th>수량 단위</th><th className="text-right">Base 수량</th><th className="text-right">Comparison 수량</th><th className="text-right">Base 매출</th><th className="text-right">Comparison 매출</th></tr></thead>
      <tbody>{value.product_groups.map((row) => <tr key={row.code}><td>{row.display_name}</td><td>{row.quantity_unit}</td><td className="text-right">{formatNumber(row.baseline_quantity)}</td><td className="text-right">{formatNumber(row.comparison_quantity)}</td><td className="text-right">{formatMillion(row.baseline_revenue)}</td><td className="text-right">{formatMillion(row.comparison_revenue)}</td></tr>)}</tbody>
    </table></section>;
}

function ManufacturingActivityTable({ value }: { value: AnalysisPresentationDto }) {
  if (!value.manufacturing_activities.length) return null;
  return <section className="financial-table-container"><div style={{ padding: '10px 14px', fontWeight: 700 }}>제조 조업도 Basis</div>
    <table className="financial-table"><thead><tr><th>공정</th><th>Basis</th><th>단위</th><th className="text-right">Base</th><th className="text-right">Comparison</th><th className="text-right">Delta</th></tr></thead>
      <tbody>{value.manufacturing_activities.map((row) => <tr key={`${row.process}:${row.production_basis}`}><td>{row.process}</td><td>{row.production_basis}</td><td>{row.unit}</td><td className="text-right">{formatNumber(row.baseline)}</td><td className="text-right">{formatNumber(row.comparison)}</td><td className="text-right">{formatNumber(row.delta, true)}</td></tr>)}</tbody>
    </table></section>;
}

function waterfallBars(value: AnalysisPresentationDto): WaterfallBarData[] {
  let running = value.kpis.baseline_operating_profit / MILLION;
  const bars: WaterfallBarData[] = [{ id: 'baseline', name: 'Base OP', category: 'START_TOTAL', startValue: 0, endValue: running, delta: running, isTotal: true, isStart: true, isEnd: false, colorType: 'start' }];
  for (const effect of value.effects) {
    const delta = effect.profit_effect / MILLION;
    const startValue = running;
    running += delta;
    bars.push({ id: effect.code, name: effect.label, category: effect.category, startValue, endValue: running, delta, isTotal: false, isStart: false, isEnd: false, colorType: delta >= 0 ? 'favorable' : 'unfavorable' });
  }
  const residualDelta = value.residual.amount / MILLION;
  const residualStart = running;
  running += residualDelta;
  bars.push({ id: 'residual', name: 'Residual', category: 'LAG', startValue: residualStart, endValue: running, delta: residualDelta, isTotal: false, isStart: false, isEnd: false, colorType: residualDelta === 0 ? 'neutral' : residualDelta > 0 ? 'favorable' : 'unfavorable' });
  bars.push({ id: 'comparison', name: 'Comparison OP', category: 'END_TOTAL', startValue: 0, endValue: value.kpis.comparison_operating_profit / MILLION, delta: value.kpis.comparison_operating_profit / MILLION, isTotal: true, isStart: false, isEnd: true, colorType: 'end' });
  return bars;
}

function formatMillion(value: number, signed = false): string {
  const number = value / MILLION;
  const formatted = number.toLocaleString('ko-KR', { maximumFractionDigits: 1 });
  return `${signed && number > 0 ? '+' : ''}${formatted} 백만원`;
}

function formatNumber(value: number, signed = false): string {
  return `${signed && value > 0 ? '+' : ''}${value.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}`;
}

function displayNullable(value: number | null, unit: string): string {
  if (value === null) return '—';
  return unit === 'KRW' ? formatMillion(value) : formatNumber(value);
}
