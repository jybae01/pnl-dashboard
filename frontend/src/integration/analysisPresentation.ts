import {
  AnalysisPresentationDto,
  AnalysisPresentationEffectDto,
  AnalysisResidualDto,
  PresentationEffectCode,
  PresentationEffectCategory,
} from './types';

export interface AnalysisWaterfallBar {
  id: string;
  name: string;
  category: PresentationEffectCategory | 'START_TOTAL' | 'LAG' | 'END_TOTAL';
  startValue: number;
  endValue: number;
  delta: number;
  isTotal: boolean;
  isStart: boolean;
  isEnd: boolean;
  colorType: 'start' | 'end' | 'favorable' | 'unfavorable' | 'neutral';
}

/**
 * The backend owns the effect values and ordering semantics.  This map only
 * provides the stable labels/order used by the presentation layer.
 */
export const CANONICAL_EFFECT_ORDER = [
  'sales_quantity',
  'sales_mix',
  'sales_price',
  'sales_fx',
  'material_total',
  'manufacturing_realized',
  'inventory_timing',
  'sga_variable',
  'sga_fixed',
  'tariff',
] as const satisfies readonly PresentationEffectCode[];

export const CANONICAL_EFFECT_LABELS: Record<PresentationEffectCode, string> = {
  sales_quantity: '수량',
  sales_mix: '제품 Mix',
  sales_price: '판가',
  sales_fx: '매출환율',
  material_total: '원재료',
  manufacturing_realized: '제조',
  inventory_timing: '재고·원가 반영시차',
  sga_variable: '변동비',
  sga_fixed: '고정비',
  tariff: '관세',
};

export const RESIDUAL_CODE = 'residual' as const;
export const RESIDUAL_LABEL = '기타 요인' as const;

export const MANUFACTURING_VARIABLE_ACCOUNT_LABELS = [
  '수도광열비',
  '소모품비',
  '원자재운반비',
  '외주가공비',
] as const;

export const EFFECT_CATEGORY_LABELS: Record<PresentationEffectCategory, string> = {
  INTERNAL: '내부',
  EXTERNAL: '외부',
  COST: '비용',
};

export type ProfitEffectTone = 'positive' | 'negative' | 'zero';

export interface MappedPresentationEffect extends AnalysisPresentationEffectDto {
  uiLabel: string;
  uiCategoryLabel: string;
  contributionRate: number | null;
}

export interface MappedResidual extends AnalysisResidualDto {
  code: typeof RESIDUAL_CODE;
  uiLabel: typeof RESIDUAL_LABEL;
  contributionRate: number | null;
}

export type ExecutiveEffectGroupKey = 'sales' | 'fx' | 'cost';

export interface ExecutiveEffectGroup {
  key: ExecutiveEffectGroupKey;
  title: string;
  effects: MappedPresentationEffect[];
  profitEffect: number;
}

export interface AnalysisPresentationMapping {
  effects: MappedPresentationEffect[];
  executiveGroups: ExecutiveEffectGroup[];
  topPositiveEffects: MappedPresentationEffect[];
  topNegativeEffects: MappedPresentationEffect[];
  residual: MappedResidual;
  effectsTotalContributionRate: number | null;
  waterfallBars: AnalysisWaterfallBar[];
}

const EXECUTIVE_GROUP_DEFINITIONS: ReadonlyArray<{
  key: ExecutiveEffectGroupKey;
  title: string;
  codes: readonly PresentationEffectCode[];
}> = [
  { key: 'sales', title: '판매 효과', codes: ['sales_quantity', 'sales_price'] },
  { key: 'fx', title: '환율 효과', codes: ['sales_fx'] },
  {
    key: 'cost',
    title: '비용 효과',
    codes: ['material_total', 'sga_variable', 'sga_fixed', 'manufacturing_realized', 'inventory_timing'],
  },
];

const effectOrder = new Map<PresentationEffectCode, number>(
  CANONICAL_EFFECT_ORDER.map((code, index) => [code, index]),
);

/**
 * Presentation-only contribution metric confirmed by the source mockup:
 * signed effect / signed operating-profit delta. It does not change bridge amounts.
 */
export function calculateContributionRate(profitEffect: number, operatingProfitDelta: number): number | null {
  return operatingProfitDelta === 0 ? null : (profitEffect / operatingProfitDelta) * 100;
}

export function formatContributionRate(value: number | null): string {
  if (value === null) return '—';
  const formatted = Math.abs(value) < 0.05 ? 0 : value;
  return `${formatted > 0 ? '+' : ''}${formatted.toFixed(1)}%`;
}

export function mapEffect(
  effect: AnalysisPresentationEffectDto,
  operatingProfitDelta = 0,
): MappedPresentationEffect {
  return {
    ...effect,
    // Backend labels are data, while this is the stable UI vocabulary.
    uiLabel: CANONICAL_EFFECT_LABELS[effect.code] ?? effect.label,
    uiCategoryLabel: EFFECT_CATEGORY_LABELS[effect.category],
    contributionRate: calculateContributionRate(effect.profit_effect, operatingProfitDelta),
  };
}

export function mapCanonicalEffects(
  effects: AnalysisPresentationEffectDto[],
  operatingProfitDelta: number,
): MappedPresentationEffect[] {
  return effects
    .map((effect) => mapEffect(effect, operatingProfitDelta))
    .sort((left, right) => (effectOrder.get(left.code) ?? Number.MAX_SAFE_INTEGER)
      - (effectOrder.get(right.code) ?? Number.MAX_SAFE_INTEGER));
}

/**
 * User-facing regrouping of the 10 canonical effects into 8 presentation groups:
 * 1. 수량 = sales_quantity + sales_mix
 * 2. 판가 = sales_price
 * 3. 매출환율 = sales_fx
 * 4. 원재료 = material_total
 * 5. 변동비 = sga_variable + tariff
 * 6. 고정비 = sga_fixed
 * 7. 제조 = manufacturing_realized (Temporary Fallback)
 * 8. 재고·원가 반영시차 = inventory_timing
 *
 * Residual ('기타 요인') is maintained separately.
 * Mathematical identity: sum(regrouped.profit_effect) === kpis.effects_total
 */
export function mapGroupedPresentationEffects(
  canonicalEffects: AnalysisPresentationEffectDto[],
  operatingProfitDelta = 0,
): MappedPresentationEffect[] {
  const effectMap = new Map<string, AnalysisPresentationEffectDto>();
  canonicalEffects.forEach((e) => effectMap.set(e.code, e));

  const grouped: MappedPresentationEffect[] = [];
  const processedCodes = new Set<string>();
  const manufacturing = effectMap.get('manufacturing_realized');
  const manufacturingRows = manufacturing?.drilldown.kind === 'manufacturing'
    ? manufacturing.drilldown.rows
    : [];
  const manufacturingVariableMatches = MANUFACTURING_VARIABLE_ACCOUNT_LABELS.map((label) => (
    manufacturingRows.filter((row) => row.label === label)
  ));
  const hasAuthoritativeManufacturingVariableSplit = manufacturingVariableMatches.every(
    (matches) => matches.length === 1 && matches[0].profit_effect !== null,
  );
  const authoritativeManufacturingVariableRows = hasAuthoritativeManufacturingVariableSplit
    ? manufacturingVariableMatches.map(([row]) => row)
    : [];
  const manufacturingVariableEffect = authoritativeManufacturingVariableRows.reduce(
    (sum, row) => sum + (row.profit_effect ?? 0),
    0,
  );

  // 1. 수량 (sales_quantity + sales_mix)
  const qty = effectMap.get('sales_quantity');
  const mix = effectMap.get('sales_mix');
  if (qty || mix) {
    const qtyEffect = qty?.profit_effect ?? 0;
    const mixEffect = mix?.profit_effect ?? 0;
    const combinedRows = [...(qty?.drilldown.rows ?? []), ...(mix?.drilldown.rows ?? [])];
    grouped.push({
      code: 'sales_quantity' as PresentationEffectCode,
      label: '수량',
      category: 'INTERNAL',
      profit_effect: qtyEffect + mixEffect,
      description: '판매수량 및 제품 Mix 변동 영향',
      drilldown: {
        kind: 'sales',
        available: combinedRows.length > 0,
        rows: combinedRows,
        unavailable_reason: null,
      },
      uiLabel: '수량',
      uiCategoryLabel: '내부',
      contributionRate: calculateContributionRate(qtyEffect + mixEffect, operatingProfitDelta),
    });
    processedCodes.add('sales_quantity');
    processedCodes.add('sales_mix');
  }

  // 2. 판가 (sales_price)
  const price = effectMap.get('sales_price');
  if (price) {
    grouped.push({
      ...mapEffect(price, operatingProfitDelta),
      uiLabel: '판가',
    });
    processedCodes.add('sales_price');
  }

  // 3. 매출환율 (sales_fx)
  const fx = effectMap.get('sales_fx');
  if (fx) {
    grouped.push({
      ...mapEffect(fx, operatingProfitDelta),
      uiLabel: '매출환율',
    });
    processedCodes.add('sales_fx');
  }

  // 4. 원재료 (material_total)
  const material = effectMap.get('material_total');
  if (material) {
    grouped.push({
      ...mapEffect(material, operatingProfitDelta),
      uiLabel: '원재료',
    });
    processedCodes.add('material_total');
  }

  // 5. 변동비 (sga_variable + tariff + authoritative manufacturing-variable accounts)
  const sgaVar = effectMap.get('sga_variable');
  const tariff = effectMap.get('tariff');
  if (sgaVar || tariff) {
    const varEffect = sgaVar?.profit_effect ?? 0;
    const tariffEffect = tariff?.profit_effect ?? 0;
    const combinedRows = [
      ...(sgaVar?.drilldown.rows ?? []),
      ...(tariff?.drilldown.rows ?? []),
      ...authoritativeManufacturingVariableRows,
    ];
    grouped.push({
      code: 'sga_variable' as PresentationEffectCode,
      label: '변동비',
      category: 'COST',
      profit_effect: varEffect + tariffEffect + manufacturingVariableEffect,
      description: '변동 판매관리비, 관세 및 제조변동비 영향',
      drilldown: {
        kind: 'sga',
        available: combinedRows.length > 0,
        rows: combinedRows,
        unavailable_reason: null,
      },
      uiLabel: '변동비',
      uiCategoryLabel: '비용',
      contributionRate: calculateContributionRate(
        varEffect + tariffEffect + manufacturingVariableEffect,
        operatingProfitDelta,
      ),
    });
    processedCodes.add('sga_variable');
    processedCodes.add('tariff');
  }

  // 6. 고정비 (sga_fixed)
  const sgaFixed = effectMap.get('sga_fixed');
  if (sgaFixed) {
    grouped.push({
      ...mapEffect(sgaFixed, operatingProfitDelta),
      uiLabel: '고정비',
    });
    processedCodes.add('sga_fixed');
  }

  // 7. 제조 (manufacturing_realized less the four rows moved to 변동비)
  const mfg = manufacturing;
  if (mfg) {
    const movedRowIds = new Set(authoritativeManufacturingVariableRows.map((row) => row.row_id));
    const remainderRows = mfg.drilldown.rows.filter((row) => !movedRowIds.has(row.row_id));
    grouped.push({
      ...mapEffect(mfg, operatingProfitDelta),
      profit_effect: mfg.profit_effect - manufacturingVariableEffect,
      contributionRate: calculateContributionRate(
        mfg.profit_effect - manufacturingVariableEffect,
        operatingProfitDelta,
      ),
      description: hasAuthoritativeManufacturingVariableSplit
        ? '제조변동비 4개 계정을 제외한 제조 영향'
        : mfg.description,
      drilldown: hasAuthoritativeManufacturingVariableSplit
        ? {
          ...mfg.drilldown,
          available: remainderRows.length > 0,
          rows: remainderRows,
          unavailable_reason: remainderRows.length > 0 ? null : '나머지 제조경비 계정 세부 payload 없음',
        }
        : mfg.drilldown,
      uiLabel: '제조',
    });
    processedCodes.add('manufacturing_realized');
  }

  // 8. 재고·원가 반영시차 (inventory_timing)
  const invTiming = effectMap.get('inventory_timing');
  if (invTiming) {
    grouped.push({
      ...mapEffect(invTiming, operatingProfitDelta),
      uiLabel: '재고·원가 반영시차',
    });
    processedCodes.add('inventory_timing');
  }

  // 9. Unknown/Unmapped canonical effects safe preservation
  canonicalEffects.forEach((e) => {
    if (!processedCodes.has(e.code)) {
      grouped.push(mapEffect(e, operatingProfitDelta));
    }
  });

  return grouped;
}

export function mapResidual(residual: AnalysisResidualDto, operatingProfitDelta = 0): MappedResidual {
  return {
    ...residual,
    code: RESIDUAL_CODE,
    uiLabel: RESIDUAL_LABEL,
    contributionRate: calculateContributionRate(residual.amount, operatingProfitDelta),
  };
}

export function mapExecutiveEffectGroups(effects: MappedPresentationEffect[]): ExecutiveEffectGroup[] {
  const byCode = new Map(effects.map((effect) => [effect.code, effect]));
  return EXECUTIVE_GROUP_DEFINITIONS.map((definition) => {
    const grouped = definition.codes
      .map((code) => byCode.get(code))
      .filter((effect): effect is MappedPresentationEffect => Boolean(effect));
    return {
      key: definition.key,
      title: definition.title,
      effects: grouped,
      profitEffect: grouped.reduce((sum, effect) => sum + effect.profit_effect, 0),
    };
  });
}

export function profitEffectTone(value: number): ProfitEffectTone {
  if (value > 0) return 'positive';
  if (value < 0) return 'negative';
  return 'zero';
}

/**
 * Build only the cumulative geometry needed to draw the waterfall.  The
 * values used here are authoritative DTO values; this function does not
 * reconcile them, derive a residual, or replace any backend total.
 */
export function mapWaterfallBars(
  value: AnalysisPresentationDto,
  effects: MappedPresentationEffect[] = mapGroupedPresentationEffects(value.effects),
  residual: MappedResidual = mapResidual(value.residual),
): AnalysisWaterfallBar[] {
  let running = value.kpis.baseline_operating_profit;
  const bars: AnalysisWaterfallBar[] = [{
    id: 'baseline',
    name: '기준(계획)',
    category: 'START_TOTAL',
    startValue: 0,
    endValue: running,
    delta: running,
    isTotal: true,
    isStart: true,
    isEnd: false,
    colorType: 'start',
  }];

  effects.forEach((effect) => {
    const delta = effect.profit_effect;
    const startValue = running;
    running += delta;
    bars.push({
      id: effect.code,
      name: effect.code === 'inventory_timing' ? '재고차이 등' : effect.uiLabel,
      category: effect.category,
      startValue,
      endValue: running,
      delta,
      isTotal: false,
      isStart: false,
      isEnd: false,
      colorType: profitEffectTone(effect.profit_effect) === 'positive'
        ? 'favorable'
        : profitEffectTone(effect.profit_effect) === 'negative' ? 'unfavorable' : 'neutral',
    });
  });

  const residualDelta = residual.amount;
  const residualStart = running;
  running += residualDelta;
  bars.push({
    id: residual.code,
    name: residual.uiLabel,
    category: 'LAG',
    startValue: residualStart,
    endValue: running,
    delta: residualDelta,
    isTotal: false,
    isStart: false,
    isEnd: false,
    colorType: profitEffectTone(residual.amount) === 'positive'
      ? 'favorable'
      : profitEffectTone(residual.amount) === 'negative' ? 'unfavorable' : 'neutral',
  });

  const comparison = value.kpis.comparison_operating_profit;
  bars.push({
    id: 'comparison',
    name: '비교(실적)',
    category: 'END_TOTAL',
    startValue: 0,
    endValue: comparison,
    delta: comparison,
    isTotal: true,
    isStart: false,
    isEnd: true,
    colorType: 'end',
  });

  return bars;
}

export function mapAnalysisPresentation(value: AnalysisPresentationDto): AnalysisPresentationMapping {
  const operatingProfitDelta = value.kpis.operating_profit_delta;
  const effects = mapGroupedPresentationEffects(value.effects, operatingProfitDelta);
  const residual = mapResidual(value.residual, operatingProfitDelta);
  return {
    effects,
    executiveGroups: mapExecutiveEffectGroups(effects),
    topPositiveEffects: value.executive_summary.top_positive_effects.map((effect) => mapEffect(effect, operatingProfitDelta)),
    topNegativeEffects: value.executive_summary.top_negative_effects.map((effect) => mapEffect(effect, operatingProfitDelta)),
    residual,
    effectsTotalContributionRate: calculateContributionRate(value.kpis.effects_total, operatingProfitDelta),
    waterfallBars: mapWaterfallBars(value, effects, residual),
  };
}
