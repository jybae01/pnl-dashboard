export type ProductGroup = 'ALL' | 'SW' | 'BW' | 'LC';

export type ScenarioType = 'ACTUAL' | 'FORECAST';

export type ComparisonType = 'PLAN_VS_ACTUAL' | 'PLAN_VS_FORECAST' | 'FORECAST_VS_PLAN' | 'MOM_CHANGE';

export type PeriodType = 'MONTHLY' | 'YTD' | 'CUSTOM';

export type ImpactDirection = 'FAVORABLE' | 'UNFAVORABLE' | 'NEUTRAL';

export type ViewTab = 'pnl_status' | 'forecast_generation' | 'variance_analysis' | 'data_management';

export interface ProductGroupOption {
  code: ProductGroup;
  name: string;
  shortDesc: string;
}

export const PRODUCT_GROUPS: ProductGroupOption[] = [
  { code: 'ALL', name: '전체 제품군', shortDesc: '전사 손익 종합' },
  { code: 'SW', name: '8인치 SW', shortDesc: '8인치 SW' },
  { code: 'BW', name: '8인치 BW', shortDesc: '8인치 BW' },
  { code: 'LC', name: '4인치 LC', shortDesc: '4인치 LC' },
];
