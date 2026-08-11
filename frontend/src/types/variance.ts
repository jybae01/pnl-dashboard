import { ProductGroup, ComparisonType, PeriodType, ImpactDirection } from './common';

export type EffectCategory =
  | 'START_TOTAL'
  | 'INTERNAL'    // 내부효과 (판매수량, 판가)
  | 'EXTERNAL'    // 외부효과 (매출환율, 원재료환율)
  | 'COST'        // 비용효과 (원재료, 변동비, 고정비)
  | 'LAG'         // 시차효과 (재고·원가 반영시차)
  | 'END_TOTAL';

export interface DrilldownDetailRow {
  id: string;
  subItemName: string;
  unit: string;
  planValue: number;
  actualValue: number;
  diffValue: number;
  diffRate: number;
  profitEffect: number;      // 손익영향금액 (백만원)
  note: string;
}

export interface VarianceEffectItem {
  id: string;
  name: string;
  category: EffectCategory;
  categoryLabel: string;
  unit: string;
  planValue: number;
  actualValue: number;
  diffValue: number;
  diffRate: number;
  profitEffect: number;        // 손익 영향 금액 (백만원: +익, -손)
  contributionRate: number;    // 전체 변동 대비 기여율 (%)
  impactDirection: ImpactDirection;
  description: string;
  isExpanded?: boolean;
  drilldownRows: DrilldownDetailRow[];
}

export interface WaterfallBarData {
  id: string;
  name: string;
  category: EffectCategory;
  startValue: number;
  endValue: number;
  delta: number;
  isTotal: boolean;
  isStart: boolean;
  isEnd: boolean;
  colorType: 'start' | 'end' | 'favorable' | 'unfavorable' | 'neutral';
}

export interface VarianceAnalysisResult {
  baselineModelName: string;
  comparisonModelName: string;
  baseMonth: string;
  periodType: PeriodType;
  comparisonType: ComparisonType;
  productGroup: ProductGroup;

  planOpProfit: number;          // 계획 영업이익 (백만원)
  actualOpProfit: number;        // 실적/추정 영업이익 (백만원)
  totalVariance: number;         // 총 손익 차이 (+320 백만원)
  varianceRate: number;          // 증감율 (%)

  effects: VarianceEffectItem[];
  waterfallBars: WaterfallBarData[];

  executiveSummary: string;      // 자동 생성 문장형 분석 요약
  keyPositiveFactors: string[];
  keyNegativeFactors: string[];
}

export interface VarianceFilterState {
  baseMonth: string;
  periodType: PeriodType;
  comparisonType: ComparisonType;
  productGroup: ProductGroup;
}
