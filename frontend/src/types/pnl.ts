import { ProductGroup, ScenarioType } from './common';

export type PnlViewMode =
  | 'ACTUAL_ONLY'              // 실적만 보기
  | 'PLAN_ACTUAL_COMPARE'      // 계획 / 실적 비교
  | 'CUSTOM_PERIOD_COMPARE';   // 기간 설정 비교 (시작월 ~ 종료월 누계)

export type PnlSubTab =
  | 'pnl_statement'            // 1. 손익계산서
  | 'mfg_cost_breakdown'       // 2. 제품/반제품 매출원가 내역
  | 'sga_breakdown'            // 3. 판매관리비 명세
  | 'item_segment_pnl';        // 4. Item별 구분손익

export type TrendChartType =
  | 'REVENUE'                  // 매출액
  | 'OP_PROFIT'                // 영업이익
  | 'ADJ_OP_PROFIT'            // 조정 영업이익
  | 'COMBINED';                // 월별 데이터표

export interface PnlKpiMetric {
  title: string;
  monthlyActual: number;        // 당월 실적 (백만원)
  monthlyPlan: number;          // 당월 계획
  monthlyVariance: number;      // 당월 차이 (실적 - 계획)
  monthlyAchievementRate: number; // 당월 달성률 (%)

  ytdActual: number;            // 누계 실적 (1월 ~ 당월)
  ytdPlan: number;              // 누계 계획
  ytdVariance: number;          // 누계 차이

  annualPlan: number;           // 연간 계획 (연간 목표)
  annualProgressRate: number;   // 연간 계획 대비 진도율 (%)
  ytdAchievementRate: number;   // 실적 입력기간 계획 대비 달성률 (%)
}

export interface PnlKpiSummary {
  revenue: PnlKpiMetric;                  // 1. 매출액
  operatingProfit: PnlKpiMetric;          // 2. 영업이익 (★Primary Highlight)
  adjustedOperatingProfit: PnlKpiMetric;  // 3. 조정 영업이익 (일반 KPI)

  operatingMargin: number;                // 영업이익률 (%)
  planOperatingMargin: number;            // 계획 영업이익률 (%)
  operatingMarginGap: number;             // 영업이익률 Gap (%p)

  adjustedOperatingMargin: number;        // 조정 영업이익률 (%)
  planAdjustedOperatingMargin: number;    // 계획 조정 영업이익률 (%)
  adjustedOperatingMarginGap: number;     // 조정 영업이익률 Gap (%p)
}

export interface MonthlyTrendItem {
  month: string;                // '2026-01' ~ '2026-12'
  monthLabel: string;           // '1월' ~ '12월'
  isActual: boolean;            // 실적 확정 여부

  planRevenue: number;
  actualRevenue?: number;
  forecastRevenue?: number;

  planOpProfit: number;
  actualOpProfit?: number;
  forecastOpProfit?: number;
  planOpMargin: number;
  actualOpMargin?: number;
  forecastOpMargin?: number;

  planAdjOpProfit: number;      // 조정 영업이익 계획
  actualAdjOpProfit?: number;   // 조정 영업이익 실적
  forecastAdjOpProfit?: number; // 조정 영업이익 추정
  planAdjOpMargin: number;      // 조정 영업이익률
  actualAdjOpMargin?: number;
  forecastAdjOpMargin?: number;
}

export interface PnlLineItem {
  id: string;
  code: string;
  name: string;
  level: number;                // 0: 대분류, 1: 중분류, 2: 세부항목
  isHeader?: boolean;
  isTotal?: boolean;
  isRate?: boolean;             // true일 경우 차이 단위가 %p로 표시됨
  unit?: string;                // 기본 '백만원', 수량은 '천대/EA', 비율은 '%'

  plan: number;                 // 당월 계획
  actual: number;               // 당월 실적/추정
  variance: number;             // 당월 차이 (실적 - 계획)
  varianceRate: number;         // 당월 증감률 (% 또는 %p)

  ytdPlan?: number;             // 기간 누계 계획
  ytdActual?: number;           // 기간 누계 실적
  ytdVariance?: number;         // 기간 누계 차이
  ytdVarianceRate?: number;     // 누계 증감률

  ratioToRevenue?: number;      // 매출액 대비 비중 (%)
  children?: PnlLineItem[];
}

export interface MfgCostBreakdownItem {
  id: string;
  name: string;                 // 원부재료비, 노무비, 외주가공비, 기타 제조경비, 합계
  planAmount: number;           // 계획 금액 (백만원)
  actualAmount: number;         // 실적 금액 (백만원)
  variance: number;             // 차이
  varianceRate: number;         // 증감률 (%)

  planRatioToRevenue: number;   // 계획 대비 매출 비율 (%)
  ratioToRevenue: number;       // 실적 대비 매출 비율 (%)
  ratioDiff: number;            // 비율 차이 (%p)

  ytdPlanAmount: number;        // 누계 계획
  ytdActualAmount: number;      // 누계 실적
  ytdVariance: number;          // 누계 차이
  note?: string;
}

export interface SgaBreakdownItem {
  id: string;
  category: '일반관리비' | '판매비' | '총계';
  name: string;
  level: number;                // 0: 카테고리 헤더, 1: 세부항목, 2: 총계
  plan: number;
  actual: number;
  variance: number;
  varianceRate: number;

  ytdPlan: number;
  ytdActual: number;
  ytdVariance: number;
  ytdVarianceRate: number;

  ratioToRevenue: number;       // 매출 대비 비율 (%)
}

export interface ProductSegmentPnl {
  itemId: string;
  itemName: string;             // '8인치 SW', '8인치 BW', '4인치 LC', '신사업'
  categoryName: string;

  volume: { plan: number; actual: number; variance: number; ytdPlan: number; ytdActual: number; unit: string };
  asp: { plan: number; actual: number; variance: number; ytdPlan: number; ytdActual: number; unit: string };

  revenue: { plan: number; actual: number; variance: number; ytdPlan: number; ytdActual: number };
  cogs: { plan: number; actual: number; variance: number; ytdPlan: number; ytdActual: number };
  cogsRatio: { plan: number; actual: number; variance: number }; // %p
  grossProfit: { plan: number; actual: number; variance: number; ytdPlan: number; ytdActual: number };
  grossProfitMargin: { plan: number; actual: number; variance: number }; // %p
  sga: { plan: number; actual: number; variance: number; ytdPlan: number; ytdActual: number };
  opProfit: { plan: number; actual: number; variance: number; ytdPlan: number; ytdActual: number };
  opMargin: { plan: number; actual: number; variance: number }; // %p
}

export interface ProductGroupPnlItem {
  productGroup: ProductGroup;
  groupName: string;
  revenue: number;
  planRevenue: number;
  revenueVariance: number;
  revenueAchievementRate: number;
  cogs: number;
  grossProfit: number;
  grossProfitMargin: number;
  operatingProfit: number;
  planOperatingProfit: number;
  opProfitVariance: number;
  operatingMargin: number;
  planOperatingMargin: number;
  shareOfRevenue: number;
}

export interface KeyVarianceNote {
  id: string;
  category: 'REVENUE' | 'COST' | 'MARGIN' | 'MARKET';
  title: string;
  impactType: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  impactAmountText: string;
  description: string;
}

export interface PnlFilterState {
  baseYear: number;             // 2026 (기준년도)
  baseMonth: string;            // '2026-06'
  startMonth?: string;          // '2026-01'
  endMonth?: string;            // '2026-06'
  productGroup?: ProductGroup;  // 'ALL'
  viewMode?: PnlViewMode;       // Local to sub-tabs
  activeSubTab: PnlSubTab;      // 'pnl_statement' | 'mfg_cost_breakdown' | 'sga_breakdown' | 'item_segment_pnl'
  selectedSegmentId?: string;
}
