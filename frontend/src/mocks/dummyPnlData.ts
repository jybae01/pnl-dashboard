import {
  PnlKpiSummary,
  MonthlyTrendItem,
  PnlLineItem,
  MfgCostBreakdownItem,
  SgaBreakdownItem,
  ProductSegmentPnl,
  KeyVarianceNote,
  PnlFilterState
} from '../types/pnl';
import { ProductGroup } from '../types/common';

export const DUMMY_KPI_SUMMARY: PnlKpiSummary = {
  revenue: {
    title: '매출액',
    monthlyActual: 12500,
    monthlyPlan: 12000,
    monthlyVariance: 500,
    monthlyAchievementRate: 104.17,
    ytdActual: 71490,
    ytdPlan: 69700,
    ytdVariance: 1790,
    annualPlan: 145000,
    annualProgressRate: 49.30,
    ytdAchievementRate: 102.57,
  },
  operatingProfit: {
    title: '영업이익',
    monthlyActual: 1250,
    monthlyPlan: 930,
    monthlyVariance: 320,
    monthlyAchievementRate: 134.41,
    ytdActual: 5500,
    ytdPlan: 5270,
    ytdVariance: 230,
    annualPlan: 11500,
    annualProgressRate: 47.83,
    ytdAchievementRate: 104.36,
  },
  adjustedOperatingProfit: {
    title: '조정 영업이익',
    monthlyActual: 1430,
    monthlyPlan: 1080,
    monthlyVariance: 350,
    monthlyAchievementRate: 132.41,
    ytdActual: 6320,
    ytdPlan: 5900,
    ytdVariance: 420,
    annualPlan: 12800,
    annualProgressRate: 49.38,
    ytdAchievementRate: 107.12,
  },
  operatingMargin: 10.00,
  planOperatingMargin: 7.75,
  operatingMarginGap: 2.25,
  adjustedOperatingMargin: 11.44,
  planAdjustedOperatingMargin: 9.00,
  adjustedOperatingMarginGap: 2.44,
};

export const DUMMY_KPI_DATA = DUMMY_KPI_SUMMARY;

export const DUMMY_MONTHLY_TRENDS: MonthlyTrendItem[] = [
  {
    month: '2026-01', monthLabel: '1월', isActual: true,
    planRevenue: 10800, actualRevenue: 10950,
    planOpProfit: 780, actualOpProfit: 810, planOpMargin: 7.22, actualOpMargin: 7.40,
    planAdjOpProfit: 910, actualAdjOpProfit: 950, planAdjOpMargin: 8.43, actualAdjOpMargin: 8.68
  },
  {
    month: '2026-02', monthLabel: '2월', isActual: true,
    planRevenue: 10500, actualRevenue: 10420,
    planOpProfit: 750, actualOpProfit: 720, planOpMargin: 7.14, actualOpMargin: 6.91,
    planAdjOpProfit: 880, actualAdjOpProfit: 850, planAdjOpMargin: 8.38, actualAdjOpMargin: 8.16
  },
  {
    month: '2026-03', monthLabel: '3월', isActual: true,
    planRevenue: 11400, actualRevenue: 11600,
    planOpProfit: 850, actualOpProfit: 910, planOpMargin: 7.46, actualOpMargin: 7.84,
    planAdjOpProfit: 990, actualAdjOpProfit: 1060, planAdjOpMargin: 8.68, actualAdjOpMargin: 9.14
  },
  {
    month: '2026-04', monthLabel: '4월', isActual: true,
    planRevenue: 11600, actualRevenue: 11900,
    planOpProfit: 870, actualOpProfit: 950, planOpMargin: 7.50, actualOpMargin: 7.98,
    planAdjOpProfit: 1010, actualAdjOpProfit: 1100, planAdjOpMargin: 8.71, actualAdjOpMargin: 9.24
  },
  {
    month: '2026-05', monthLabel: '5월', isActual: true,
    planRevenue: 11800, actualRevenue: 12120,
    planOpProfit: 890, actualOpProfit: 1060, planOpMargin: 7.54, actualOpMargin: 8.75,
    planAdjOpProfit: 1030, actualAdjOpProfit: 1230, planAdjOpMargin: 8.73, actualAdjOpMargin: 10.15
  },
  {
    month: '2026-06', monthLabel: '6월 (당월)', isActual: true,
    planRevenue: 12000, actualRevenue: 12500,
    planOpProfit: 930, actualOpProfit: 1250, planOpMargin: 7.75, actualOpMargin: 10.00,
    planAdjOpProfit: 1080, actualAdjOpProfit: 1430, planAdjOpMargin: 9.00, actualAdjOpMargin: 11.44
  },
  {
    month: '2026-07', monthLabel: '7월 (추정)', isActual: false,
    planRevenue: 12200, forecastRevenue: 12650,
    planOpProfit: 950, forecastOpProfit: 1280, planOpMargin: 7.79, forecastOpMargin: 10.12,
    planAdjOpProfit: 1100, forecastAdjOpProfit: 1460, planAdjOpMargin: 9.02, forecastAdjOpMargin: 11.54
  },
  {
    month: '2026-08', monthLabel: '8월 (추정)', isActual: false,
    planRevenue: 12400, forecastRevenue: 12700,
    planOpProfit: 980, forecastOpProfit: 1290, planOpMargin: 7.90, forecastOpMargin: 10.16,
    planAdjOpProfit: 1130, forecastAdjOpProfit: 1470, planAdjOpMargin: 9.11, forecastAdjOpMargin: 11.57
  },
  {
    month: '2026-09', monthLabel: '9월 (추정)', isActual: false,
    planRevenue: 13000, forecastRevenue: 13400,
    planOpProfit: 1050, forecastOpProfit: 1380, planOpMargin: 8.08, forecastOpMargin: 10.30,
    planAdjOpProfit: 1200, forecastAdjOpProfit: 1560, planAdjOpMargin: 9.23, forecastAdjOpMargin: 11.64
  },
  {
    month: '2026-10', monthLabel: '10월 (추정)', isActual: false,
    planRevenue: 12800, forecastRevenue: 13100,
    planOpProfit: 1020, forecastOpProfit: 1320, planOpMargin: 7.97, forecastOpMargin: 10.08,
    planAdjOpProfit: 1170, forecastAdjOpProfit: 1500, planAdjOpMargin: 9.14, forecastAdjOpMargin: 11.45
  },
  {
    month: '2026-11', monthLabel: '11월 (추정)', isActual: false,
    planRevenue: 13500, forecastRevenue: 13900,
    planOpProfit: 1120, forecastOpProfit: 1450, planOpMargin: 8.30, forecastOpMargin: 10.43,
    planAdjOpProfit: 1270, forecastAdjOpProfit: 1640, planAdjOpMargin: 9.41, forecastAdjOpMargin: 11.80
  },
  {
    month: '2026-12', monthLabel: '12월 (추정)', isActual: false,
    planRevenue: 14000, forecastRevenue: 14400,
    planOpProfit: 1180, forecastOpProfit: 1510, planOpMargin: 8.43, forecastOpMargin: 10.49,
    planAdjOpProfit: 1330, forecastAdjOpProfit: 1710, planAdjOpMargin: 9.50, forecastAdjOpMargin: 11.88
  },
];

// Clean Korean P&L Statement hierarchical data (No redundant English in parens)
export const DUMMY_HIERARCHICAL_PNL: PnlLineItem[] = [
  {
    id: 'pnl_rev_root',
    code: '1000',
    name: 'Ⅰ. 매출액',
    level: 0,
    isHeader: true,
    plan: 12000,
    actual: 12500,
    variance: 500,
    varianceRate: 4.17,
    ytdPlan: 69700,
    ytdActual: 71490,
    ytdVariance: 1790,
    ytdVarianceRate: 2.57,
    ratioToRevenue: 100.0,
    children: [
      { id: 'rev_prod', code: '1100', name: '1. 제품 매출', level: 1, plan: 9700, actual: 10100, variance: 400, varianceRate: 4.12, ytdPlan: 56300, ytdActual: 57900, ytdVariance: 1600, ytdVarianceRate: 2.84, ratioToRevenue: 80.8 },
      { id: 'rev_semi', code: '1200', name: '2. 반제품 매출', level: 1, plan: 1400, actual: 1480, variance: 80, varianceRate: 5.71, ytdPlan: 8100, ytdActual: 8350, ytdVariance: 250, ytdVarianceRate: 3.09, ratioToRevenue: 11.84 },
      { id: 'rev_merch', code: '1300', name: '3. 상품 매출', level: 1, plan: 800, actual: 820, variance: 20, varianceRate: 2.50, ytdPlan: 4600, ytdActual: 4680, ytdVariance: 80, ytdVarianceRate: 1.74, ratioToRevenue: 6.56 },
      { id: 'rev_other', code: '1400', name: '4. 기타 매출', level: 1, plan: 300, actual: 310, variance: 10, varianceRate: 3.33, ytdPlan: 1800, ytdActual: 1820, ytdVariance: 20, ytdVarianceRate: 1.11, ratioToRevenue: 2.48 },
      { id: 'rev_rebate', code: '1500', name: '5. (-) 판매장려금/에누리', level: 1, plan: -200, actual: -210, variance: -10, varianceRate: 5.00, ytdPlan: -1100, ytdActual: -1260, ytdVariance: -160, ytdVarianceRate: 14.55, ratioToRevenue: -1.68 },
    ]
  },
  {
    id: 'pnl_vol_root',
    code: '1800',
    name: 'Ⅱ. 매출수량',
    level: 0,
    isHeader: true,
    unit: '-',
    plan: 575000,
    actual: 628000,
    variance: 53000,
    varianceRate: 9.22,
    ytdPlan: 3370000,
    ytdActual: 3555000,
    ytdVariance: 185000,
    ytdVarianceRate: 5.49,
    children: [
      { id: 'vol_sw', code: '1810', name: '8인치 SW', level: 1, unit: 'pcs', plan: 180000, actual: 205000, variance: 25000, varianceRate: 13.89, ytdPlan: 1050000, ytdActual: 1140000, ytdVariance: 90000, ytdVarianceRate: 8.57 },
      { id: 'vol_bw', code: '1820', name: '8인치 BW', level: 1, unit: 'pcs', plan: 220000, actual: 240000, variance: 20000, varianceRate: 9.09, ytdPlan: 1280000, ytdActual: 1350000, ytdVariance: 70000, ytdVarianceRate: 5.47 },
      { id: 'vol_lc', code: '1830', name: '4인치 LC', level: 1, unit: 'pcs', plan: 50000, actual: 48000, variance: -2000, varianceRate: -4.00, ytdPlan: 290000, ytdActual: 285000, ytdVariance: -5000, ytdVarianceRate: -1.72 },
      { id: 'vol_fs', code: '1840', name: '반제품 (FS)', level: 1, unit: 'm', plan: 125000, actual: 135000, variance: 10000, varianceRate: 8.00, ytdPlan: 750000, ytdActual: 780000, ytdVariance: 30000, ytdVarianceRate: 4.00 },
    ]
  },
  {
    id: 'pnl_cogs_root',
    code: '2000',
    name: 'Ⅲ. 매출원가',
    level: 0,
    isHeader: true,
    plan: 9680,
    actual: 9850,
    variance: 170,
    varianceRate: 1.76,
    ytdPlan: 56180,
    ytdActual: 56950,
    ytdVariance: 770,
    ytdVarianceRate: 1.37,
    ratioToRevenue: 78.80,
    children: [
      { id: 'cogs_prod', code: '2100', name: '1. 제품 매출원가', level: 1, plan: 7800, actual: 7920, variance: 120, varianceRate: 1.54, ytdPlan: 45200, ytdActual: 45800, ytdVariance: 600, ytdVarianceRate: 1.33, ratioToRevenue: 63.36 },
      { id: 'cogs_semi', code: '2200', name: '2. 반제품 매출원가', level: 1, plan: 1100, actual: 1140, variance: 40, varianceRate: 3.64, ytdPlan: 6400, ytdActual: 6550, ytdVariance: 150, ytdVarianceRate: 2.34, ratioToRevenue: 9.12 },
      { id: 'cogs_merch', code: '2300', name: '3. 상품 매출원가', level: 1, plan: 620, actual: 630, variance: 10, varianceRate: 1.61, ytdPlan: 3600, ytdActual: 3650, ytdVariance: 50, ytdVarianceRate: 1.39, ratioToRevenue: 5.04 },
      { id: 'cogs_other', code: '2400', name: '4. 기타 매출원가', level: 1, plan: 160, actual: 140, variance: -20, varianceRate: -12.50, ytdPlan: 980, ytdActual: 920, ytdVariance: -60, ytdVarianceRate: -6.12, ratioToRevenue: 1.12 },
      { id: 'cogs_inv_loss', code: '2600', name: '5. 재고자산 평가손실', level: 1, plan: 0, actual: 20, variance: 20, varianceRate: 0.00, ytdPlan: 0, ytdActual: 30, ytdVariance: 30, ytdVarianceRate: 0.00, ratioToRevenue: 0.16 },
    ]
  },
  {
    id: 'pnl_cogs_ratio',
    code: '2900',
    name: '매출원가율',
    level: 0,
    isRate: true,
    unit: '%',
    plan: 80.67,
    actual: 78.80,
    variance: -1.87,
    varianceRate: -1.87, // %p
    ytdPlan: 80.60,
    ytdActual: 79.66,
    ytdVariance: -0.94,
    ytdVarianceRate: -0.94,
    ratioToRevenue: 78.80,
  },
  {
    id: 'pnl_gp_total',
    code: '3000',
    name: 'Ⅳ. 매출총이익',
    level: 0,
    isTotal: true,
    plan: 2320,
    actual: 2650,
    variance: 330,
    varianceRate: 14.22,
    ytdPlan: 13520,
    ytdActual: 14540,
    ytdVariance: 1020,
    ytdVarianceRate: 7.54,
    ratioToRevenue: 21.20,
  },
  {
    id: 'pnl_gp_margin',
    code: '3900',
    name: '매출총이익률',
    level: 0,
    isRate: true,
    unit: '%',
    plan: 19.33,
    actual: 21.20,
    variance: 1.87,
    varianceRate: 1.87, // %p
    ytdPlan: 19.40,
    ytdActual: 20.34,
    ytdVariance: 0.94,
    ytdVarianceRate: 0.94,
    ratioToRevenue: 21.20,
  },
  {
    id: 'pnl_sga_root',
    code: '4000',
    name: 'Ⅴ. 판매비와 관리비',
    level: 0,
    isHeader: true,
    plan: 1390,
    actual: 1400,
    variance: 10,
    varianceRate: 0.72,
    ytdPlan: 8250,
    ytdActual: 9040,
    ytdVariance: 790,
    ytdVarianceRate: 9.58,
    ratioToRevenue: 11.20,
  },
  {
    id: 'pnl_op_total',
    code: '5000',
    name: 'Ⅵ. 영업이익',
    level: 0,
    isTotal: true,
    plan: 930,
    actual: 1250,
    variance: 320,
    varianceRate: 34.41,
    ytdPlan: 5270,
    ytdActual: 5500,
    ytdVariance: 230,
    ytdVarianceRate: 4.36,
    ratioToRevenue: 10.00,
  },
  {
    id: 'pnl_op_margin',
    code: '5900',
    name: '영업이익률',
    level: 0,
    isRate: true,
    unit: '%',
    plan: 7.75,
    actual: 10.00,
    variance: 2.25,
    varianceRate: 2.25, // %p
    ytdPlan: 7.56,
    ytdActual: 7.69,
    ytdVariance: 0.13,
    ytdVarianceRate: 0.13,
    ratioToRevenue: 10.00,
  },
  {
    id: 'pnl_adj_op_total',
    code: '6000',
    name: 'Ⅶ. 조정 영업이익',
    level: 0,
    isTotal: true,
    plan: 1080,
    actual: 1430,
    variance: 350,
    varianceRate: 32.41,
    ytdPlan: 5900,
    ytdActual: 6320,
    ytdVariance: 420,
    ytdVarianceRate: 7.12,
    ratioToRevenue: 11.44,
  },
  {
    id: 'pnl_adj_op_margin',
    code: '6900',
    name: '조정 영업이익률',
    level: 0,
    isRate: true,
    unit: '%',
    plan: 9.00,
    actual: 11.44,
    variance: 2.44,
    varianceRate: 2.44, // %p
    ytdPlan: 8.46,
    ytdActual: 8.84,
    ytdVariance: 0.38,
    ytdVarianceRate: 0.38,
    ratioToRevenue: 11.44,
  }
];

// Clean Korean Manufacturing Cost Breakdown (Section 5)
export const DUMMY_MFG_COST_BREAKDOWN: MfgCostBreakdownItem[] = [
  {
    id: 'mfg_raw',
    name: '원부재료비',
    planAmount: 5680,
    actualAmount: 5820,
    variance: 140,
    varianceRate: 2.46,
    planRatioToRevenue: 47.33,
    ratioToRevenue: 46.56,
    ratioDiff: -0.77,
    ytdPlanAmount: 32900,
    ytdActualAmount: 33700,
    ytdVariance: 800,
    note: '주요 수입 원부재료 매입 단가 인상분 반영'
  },
  {
    id: 'mfg_labor',
    name: '노무비',
    planAmount: 1450,
    actualAmount: 1470,
    variance: 20,
    varianceRate: 1.38,
    planRatioToRevenue: 12.08,
    ratioToRevenue: 11.76,
    ratioDiff: -0.32,
    ytdPlanAmount: 8410,
    ytdActualAmount: 8520,
    ytdVariance: 110,
    note: '생산라인 특근 및 야간 수당 소폭 증가'
  },
  {
    id: 'mfg_outsourcing',
    name: '외주가공비',
    planAmount: 840,
    actualAmount: 860,
    variance: 20,
    varianceRate: 2.38,
    planRatioToRevenue: 7.00,
    ratioToRevenue: 6.88,
    ratioDiff: -0.12,
    ytdPlanAmount: 4870,
    ytdActualAmount: 4980,
    ytdVariance: 110,
    note: 'SMT 표면실장 임가공 물량 증가'
  },
  {
    id: 'mfg_exp',
    name: '기타 제조경비',
    planAmount: 1090,
    actualAmount: 1070,
    variance: -20,
    varianceRate: -1.83,
    planRatioToRevenue: 9.08,
    ratioToRevenue: 8.56,
    ratioDiff: -0.52,
    ytdPlanAmount: 6320,
    ytdActualAmount: 6200,
    ytdVariance: -120,
    note: '공정 수율 개선(불량 0.6%p 감소) 및 전력비 절감'
  },
  {
    id: 'mfg_total',
    name: '합계',
    planAmount: 9060,
    actualAmount: 9220,
    variance: 160,
    varianceRate: 1.77,
    planRatioToRevenue: 75.50,
    ratioToRevenue: 73.76,
    ratioDiff: -1.74,
    ytdPlanAmount: 52500,
    ytdActualAmount: 53400,
    ytdVariance: 900,
    note: '손익계산서 제품+반제품 매출원가 합계(9,060 vs 9,220)와 100% 정합'
  }
];

// Clean Korean SG&A Breakdown (Section 6)
export const DUMMY_SGA_BREAKDOWN: SgaBreakdownItem[] = [
  // 일반관리비
  { id: 'sga_admin_hdr', category: '일반관리비', name: '일반관리비 소계', level: 0, plan: 690, actual: 680, variance: -10, varianceRate: -1.45, ytdPlan: 4100, ytdActual: 4050, ytdVariance: -50, ytdVarianceRate: -1.22, ratioToRevenue: 5.44 },
  { id: 'sga_adm_labor', category: '일반관리비', name: '1. 인건비', level: 1, plan: 290, actual: 280, variance: -10, varianceRate: -3.45, ytdPlan: 1720, ytdActual: 1690, ytdVariance: -30, ytdVarianceRate: -1.74, ratioToRevenue: 2.24 },
  { id: 'sga_adm_depr', category: '일반관리비', name: '2. 감가상각비', level: 1, plan: 120, actual: 120, variance: 0, varianceRate: 0.00, ytdPlan: 720, ytdActual: 720, ytdVariance: 0, ytdVarianceRate: 0.00, ratioToRevenue: 0.96 },
  { id: 'sga_adm_rnd', category: '일반관리비', name: '3. 경상개발비', level: 1, plan: 380, actual: 390, variance: 10, varianceRate: 2.63, ytdPlan: 2260, ytdActual: 2310, ytdVariance: 50, ytdVarianceRate: 2.21, ratioToRevenue: 3.12 },
  { id: 'sga_adm_fee', category: '일반관리비', name: '4. 수수료', level: 1, plan: 90, actual: 85, variance: -5, varianceRate: -5.56, ytdPlan: 540, ytdActual: 520, ytdVariance: -20, ytdVarianceRate: -3.70, ratioToRevenue: 0.68 },
  { id: 'sga_adm_other', category: '일반관리비', name: '5. 기타', level: 1, plan: 60, actual: 55, variance: -5, varianceRate: -8.33, ytdPlan: 360, ytdActual: 340, ytdVariance: -20, ytdVarianceRate: -5.56, ratioToRevenue: 0.44 },

  // 판매비
  { id: 'sga_sell_hdr', category: '판매비', name: '판매비 소계', level: 0, plan: 700, actual: 720, variance: 20, varianceRate: 2.86, ytdPlan: 4150, ytdActual: 4990, ytdVariance: 840, ytdVarianceRate: 20.24, ratioToRevenue: 5.76 },
  { id: 'sga_sell_freight', category: '판매비', name: '1. 운반비', level: 1, plan: 240, actual: 220, variance: -20, varianceRate: -8.33, ytdPlan: 1420, ytdActual: 1350, ytdVariance: -70, ytdVarianceRate: -4.93, ratioToRevenue: 1.76 },
  { id: 'sga_sell_comm', category: '판매비', name: '2. 수수료', level: 1, plan: 140, actual: 150, variance: 10, varianceRate: 7.14, ytdPlan: 830, ytdActual: 890, ytdVariance: 60, ytdVarianceRate: 7.23, ratioToRevenue: 1.20 },
  { id: 'sga_sell_brand', category: '판매비', name: '3. 브랜드사용료', level: 1, plan: 80, actual: 85, variance: 5, varianceRate: 6.25, ytdPlan: 470, ytdActual: 510, ytdVariance: 40, ytdVarianceRate: 8.51, ratioToRevenue: 0.68 },
  { id: 'sga_sell_labor', category: '판매비', name: '4. 인건비', level: 1, plan: 160, actual: 170, variance: 10, varianceRate: 6.25, ytdPlan: 950, ytdActual: 1020, ytdVariance: 70, ytdVarianceRate: 7.37, ratioToRevenue: 1.36 },
  { id: 'sga_sell_sample', category: '판매비', name: '5. 견본비', level: 1, plan: 40, actual: 45, variance: 5, varianceRate: 12.50, ytdPlan: 240, ytdActual: 270, ytdVariance: 30, ytdVarianceRate: 12.50, ratioToRevenue: 0.36 },
  { id: 'sga_sell_baddebt', category: '판매비', name: '6. 대손상각', level: 1, plan: 15, actual: 15, variance: 0, varianceRate: 0.00, ytdPlan: 90, ytdActual: 90, ytdVariance: 0, ytdVarianceRate: 0.00, ratioToRevenue: 0.12 },
  { id: 'sga_sell_sundry', category: '판매비', name: '7. 잡비', level: 1, plan: 25, actual: 25, variance: 0, varianceRate: 0.00, ytdPlan: 150, ytdActual: 160, ytdVariance: 10, ytdVarianceRate: 6.67, ratioToRevenue: 0.20 },
  { id: 'sga_sell_other', category: '판매비', name: '8. 기타', level: 1, plan: 30, actual: 30, variance: 0, varianceRate: 0.00, ytdPlan: 180, ytdActual: 180, ytdVariance: 0, ytdVarianceRate: 0.00, ratioToRevenue: 0.24 },

  // 총계
  { id: 'sga_grand_total', category: '총계', name: '판관비 총계', level: 2, plan: 1390, actual: 1400, variance: 10, varianceRate: 0.72, ytdPlan: 8250, ytdActual: 9040, ytdVariance: 790, ytdVarianceRate: 9.58, ratioToRevenue: 11.20 }
];

// Product Segmented P&L: 8인치 SW, 8인치 BW, 4인치 LC, 신사업
export const DUMMY_PRODUCT_SEGMENTS: ProductSegmentPnl[] = [
  {
    itemId: '8inch_sw',
    itemName: '8인치 SW',
    categoryName: '',
    volume: { plan: 180000, actual: 205000, variance: 25000, ytdPlan: 1050000, ytdActual: 1140000, unit: 'pcs' },
    asp: { plan: 29440, actual: 28290, variance: -1150, ytdPlan: 29400, ytdActual: 28420, unit: '원' },
    revenue: { plan: 5300, actual: 5800, variance: 500, ytdPlan: 30870, ytdActual: 32400 },
    cogs: { plan: 4100, actual: 4350, variance: 250, ytdPlan: 23880, ytdActual: 24300 },
    cogsRatio: { plan: 77.36, actual: 75.00, variance: -2.36 },
    grossProfit: { plan: 1200, actual: 1450, variance: 250, ytdPlan: 6990, ytdActual: 8100 },
    grossProfitMargin: { plan: 22.64, actual: 25.00, variance: 2.36 },
    sga: { plan: 650, actual: 670, variance: 20, ytdPlan: 3860, ytdActual: 4220 },
    opProfit: { plan: 550, actual: 780, variance: 230, ytdPlan: 3130, ytdActual: 3880 },
    opMargin: { plan: 10.38, actual: 13.45, variance: 3.07 },
  },
  {
    itemId: '8inch_bw',
    itemName: '8인치 BW',
    categoryName: '',
    volume: { plan: 220000, actual: 240000, variance: 20000, ytdPlan: 1280000, ytdActual: 1350000, unit: 'pcs' },
    asp: { plan: 20000, actual: 17920, variance: -2080, ytdPlan: 20000, ytdActual: 18220, unit: '원' },
    revenue: { plan: 4400, actual: 4300, variance: -100, ytdPlan: 25600, ytdActual: 24600 },
    cogs: { plan: 3620, actual: 3550, variance: -70, ytdPlan: 21060, ytdActual: 20300 },
    cogsRatio: { plan: 82.27, actual: 82.56, variance: 0.29 },
    grossProfit: { plan: 780, actual: 750, variance: -30, ytdPlan: 4540, ytdActual: 4300 },
    grossProfitMargin: { plan: 17.73, actual: 17.44, variance: -0.29 },
    sga: { plan: 500, actual: 430, variance: -70, ytdPlan: 2980, ytdActual: 2710 },
    opProfit: { plan: 280, actual: 320, variance: 40, ytdPlan: 1560, ytdActual: 1590 },
    opMargin: { plan: 6.36, actual: 7.44, variance: 1.08 },
  },
  {
    itemId: '4inch_lc',
    itemName: '4인치 LC',
    categoryName: '',
    volume: { plan: 80000, actual: 75000, variance: -5000, ytdPlan: 460000, ytdActual: 460000, unit: 'pcs' },
    asp: { plan: 28750, actual: 32000, variance: 3250, ytdPlan: 28700, ytdActual: 31500, unit: '원' },
    revenue: { plan: 2300, actual: 2400, variance: 100, ytdPlan: 13230, ytdActual: 14490 },
    cogs: { plan: 1960, actual: 1950, variance: -10, ytdPlan: 11240, ytdActual: 12350 },
    cogsRatio: { plan: 85.22, actual: 81.25, variance: -3.97 },
    grossProfit: { plan: 340, actual: 450, variance: 110, ytdPlan: 1990, ytdActual: 2140 },
    grossProfitMargin: { plan: 14.78, actual: 18.75, variance: 3.97 },
    sga: { plan: 240, actual: 300, variance: 60, ytdPlan: 1410, ytdActual: 2110 },
    opProfit: { plan: 100, actual: 150, variance: 50, ytdPlan: 580, ytdActual: 30 },
    opMargin: { plan: 4.35, actual: 6.25, variance: 1.90 },
  },
  {
    itemId: 'new_biz',
    itemName: '신사업',
    categoryName: '',
    volume: { plan: 0, actual: 0, variance: 0, ytdPlan: 0, ytdActual: 0, unit: '-' },
    asp: { plan: 0, actual: 0, variance: 0, ytdPlan: 0, ytdActual: 0, unit: '원' },
    revenue: { plan: 1000, actual: 1200, variance: 200, ytdPlan: 5940, ytdActual: 6760 },
    cogs: { plan: 850, actual: 980, variance: 130, ytdPlan: 5040, ytdActual: 5510 },
    cogsRatio: { plan: 85.00, actual: 81.67, variance: -3.33 },
    grossProfit: { plan: 150, actual: 220, variance: 70, ytdPlan: 900, ytdActual: 1250 },
    grossProfitMargin: { plan: 15.00, actual: 18.33, variance: 3.33 },
    sga: { plan: 120, actual: 150, variance: 30, ytdPlan: 710, ytdActual: 890 },
    opProfit: { plan: 30, actual: 70, variance: 40, ytdPlan: 190, ytdActual: 360 },
    opMargin: { plan: 3.00, actual: 5.83, variance: 2.83 },
  }
];

export const DUMMY_KEY_NOTES: KeyVarianceNote[] = [
  {
    id: 'note_1',
    category: 'REVENUE',
    title: '8인치 SW 판매량 증가 및 판가(ASP) 개선',
    impactType: 'POSITIVE',
    impactAmountText: '+420 백만원',
    description: '8인치 SW 제품의 계획 대비 판매수량 초과 달성 및 평균 판가(ASP) 상승에 따른 매출 증대 효과입니다.'
  },
  {
    id: 'note_2',
    category: 'COST',
    title: '주요 원부재료 구매단가 상승 영향',
    impactType: 'NEGATIVE',
    impactAmountText: '-120 백만원',
    description: '핵심 수입 원자재 매입 단가 상승으로 원재료비가 증가하여 손익 차감 요인으로 작용했습니다.'
  },
  {
    id: 'note_3',
    category: 'MARGIN',
    title: '조정 영업이익 1,430백만원 달성 (조정 이익률 11.4%)',
    impactType: 'POSITIVE',
    impactAmountText: '+350 백만원',
    description: '일회성 재고자산 평가손실 및 R&D 감가상각 조정분을 반영한 전사 조정 영업이익은 계획 대비 32.4% 초과 달성되었습니다.'
  },
  {
    id: 'note_4',
    category: 'MARKET',
    title: '원/달러 환율 상승에 따른 환산 손익 긍정 효과',
    impactType: 'POSITIVE',
    impactAmountText: '+40 백만원',
    description: '계획 환율(1,320원/$) 대비 당월 평균 실현 환율(1,338원/$)이 상승하여 해외 매출 환산액이 약 40백만원 개선되었습니다.'
  }
];
