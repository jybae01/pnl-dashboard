import {
  VarianceAnalysisResult,
  VarianceEffectItem,
  WaterfallBarData,
  VarianceFilterState
} from '../types/variance';
import { ProductGroup } from '../types/common';

export const DUMMY_EFFECTS_ALL: VarianceEffectItem[] = [
  {
    id: 'eff_vol',
    name: '판매수량',
    category: 'INTERNAL',
    categoryLabel: '내부효과',
    unit: 'pcs',
    planValue: 575000,
    actualValue: 628000,
    diffValue: 53000,
    diffRate: 9.22,
    profitEffect: 250,
    contributionRate: 78.13,
    impactDirection: 'FAVORABLE',
    description: '8인치 SW 및 BW 등 주요 제품군 판매 물량 증가에 따른 손익 개선 효과',
    drilldownRows: [
      { id: 'vol_sw', subItemName: '8인치 SW 판매량', unit: 'pcs', planValue: 180000, actualValue: 205000, diffValue: 25000, diffRate: 13.89, profitEffect: 180, note: '계획 대비 출하량 증가' },
      { id: 'vol_bw', subItemName: '8인치 BW 판매량', unit: 'pcs', planValue: 220000, actualValue: 240000, diffValue: 20000, diffRate: 9.09, profitEffect: 90, note: '계획 대비 출하량 증가' },
      { id: 'vol_lc', subItemName: '4인치 LC 판매량', unit: 'pcs', planValue: 80000, actualValue: 75000, diffValue: -5000, diffRate: -6.25, profitEffect: -20, note: '계획 대비 출하량 감소' },
    ]
  },
  {
    id: 'eff_price',
    name: '판가',
    category: 'INTERNAL',
    categoryLabel: '내부효과',
    unit: '원/EA',
    planValue: 25000,
    actualValue: 25360,
    diffValue: 360,
    diffRate: 1.44,
    profitEffect: 90, // 판가(+170) + Mix(-80) = +90
    contributionRate: 28.13,
    impactDirection: 'FAVORABLE',
    description: '주요 제품군 평균 판매단가(ASP) 변동 및 제품 믹스(Mix) 영향을 통합 반영한 순 판가 효과',
    drilldownRows: [
      { id: 'price_sw', subItemName: '8인치 SW 평균 판매단가 (ASP)', unit: '원', planValue: 29440, actualValue: 30820, diffValue: 1380, diffRate: 4.69, profitEffect: 130, note: '평균 판매단가 상승' },
      { id: 'price_bw', subItemName: '8인치 BW 평균 판매단가 (ASP)', unit: '원', planValue: 20000, actualValue: 20200, diffValue: 200, diffRate: 1.00, profitEffect: 25, note: '평균 판매단가 소폭 상승' },
      { id: 'price_lc', subItemName: '4인치 LC 평균 판매단가 (ASP)', unit: '원', planValue: 28750, actualValue: 29200, diffValue: 450, diffRate: 1.57, profitEffect: 15, note: '평균 판매단가 상승' },
      { id: 'price_mix', subItemName: '제품 믹스(Mix) 변동 영향', unit: '%p', planValue: 37.5, actualValue: 34.6, diffValue: -2.9, diffRate: -7.73, profitEffect: -80, note: '제품별 판매 구성비 차이 흡수' },
    ]
  },
  {
    id: 'eff_fx_sales',
    name: '매출환율',
    category: 'EXTERNAL',
    categoryLabel: '외부효과',
    unit: '원/$',
    planValue: 1320.0,
    actualValue: 1338.0,
    diffValue: 18.0,
    diffRate: 1.36,
    profitEffect: 40,
    contributionRate: 12.50,
    impactDirection: 'FAVORABLE',
    description: '외화 결제 기준 환율 상승에 따른 원화 환산 매출 증가 효과',
    drilldownRows: [
      { id: 'fx_usd_sales', subItemName: 'USD 외화 매출 결제분', unit: '원/$', planValue: 1320, actualValue: 1338, diffValue: 18, diffRate: 1.36, profitEffect: 35, note: '달러 환율 상승 효과' },
      { id: 'fx_eur_sales', subItemName: 'EUR 외화 매출 결제분', unit: '원/€', planValue: 1430, actualValue: 1442, diffValue: 12, diffRate: 0.84, profitEffect: 5, note: '유로 환율 상승 효과' },
    ]
  },
  {
    id: 'eff_raw_cost',
    name: '원재료',
    category: 'COST',
    categoryLabel: '비용효과',
    unit: '백만원',
    planValue: 6300.0,
    actualValue: 6420.0,
    diffValue: 120.0,
    diffRate: 1.90,
    profitEffect: -120,
    contributionRate: -37.50,
    impactDirection: 'UNFAVORABLE',
    description: '주요 원부재료 매입 단가 변동에 따른 제조원가 영향',
    drilldownRows: [
      { id: 'raw_item_a', subItemName: '주요 원재료 A 매입비', unit: '백만원', planValue: 2800, actualValue: 2870, diffValue: 70, diffRate: 2.50, profitEffect: -70, note: '매입단가 상승' },
      { id: 'raw_item_b', subItemName: '주요 원재료 B 매입비', unit: '백만원', planValue: 1200, actualValue: 1235, diffValue: 35, diffRate: 2.92, profitEffect: -35, note: '매입단가 상승' },
      { id: 'raw_item_c', subItemName: '기타 원부자재 매입비', unit: '백만원', planValue: 1300, actualValue: 1315, diffValue: 15, diffRate: 1.15, profitEffect: -15, note: '매입단가 변동분' },
    ]
  },
  {
    id: 'eff_fx_mat',
    name: '원재료환율',
    category: 'EXTERNAL',
    categoryLabel: '외부효과',
    unit: '원/$',
    planValue: 1320.0,
    actualValue: 1338.0,
    diffValue: 18.0,
    diffRate: 1.36,
    profitEffect: -30,
    contributionRate: -9.38,
    impactDirection: 'UNFAVORABLE',
    description: '수입 원자재 결제 환율 상승에 따른 원화 매입단가 상승 영향',
    drilldownRows: [
      { id: 'fx_usd_buy', subItemName: 'USD 결제 수입 원자재', unit: '원/$', planValue: 1320, actualValue: 1338, diffValue: 18, diffRate: 1.36, profitEffect: -20, note: '수입 결제 환율 상승' },
      { id: 'fx_other_buy', subItemName: '기타 외화 결제 원자재', unit: '원/$', planValue: 1320, actualValue: 1338, diffValue: 18, diffRate: 1.36, profitEffect: -10, note: '외화 환율 변동분' },
    ]
  },
  {
    id: 'eff_var_cost',
    name: '변동비',
    category: 'COST',
    categoryLabel: '비용효과',
    unit: '백만원',
    planValue: 1500.0,
    actualValue: 1440.0,
    diffValue: -60.0,
    diffRate: -4.00,
    profitEffect: 60, // 변동비(+20) + 제조변동경비(+40) = +60
    contributionRate: 18.75,
    impactDirection: 'FAVORABLE',
    description: '생산 및 판매 활동에 연동되는 변동비용 절감 효과',
    drilldownRows: [
      { id: 'var_item_1', subItemName: '변동 제조경비 절감분', unit: '백만원', planValue: 850, actualValue: 810, diffValue: -40, diffRate: -4.71, profitEffect: 40, note: '단위당 변동제조비 절감' },
      { id: 'var_item_2', subItemName: '변동 판매관리비 절감분', unit: '백만원', planValue: 650, actualValue: 630, diffValue: -20, diffRate: -3.08, profitEffect: 20, note: '변동 판관비 절감' },
    ]
  },
  {
    id: 'eff_fixed_cost',
    name: '고정비',
    category: 'COST',
    categoryLabel: '비용효과',
    unit: '백만원',
    planValue: 2060.0,
    actualValue: 2030.0,
    diffValue: -30.0,
    diffRate: -1.46,
    profitEffect: 30, // 고정비(+10) + 제조고정경비(+20) = +30
    contributionRate: 9.38,
    impactDirection: 'FAVORABLE',
    description: '공통 고정비용 예산 집행 통제에 따른 절감 효과',
    drilldownRows: [
      { id: 'fix_item_1', subItemName: '고정 제조경비 절감분', unit: '백만원', planValue: 620, actualValue: 605, diffValue: -15, diffRate: -2.42, profitEffect: 15, note: '고정 제조비 절감' },
      { id: 'fix_item_2', subItemName: '고정 판매관리비 절감분', unit: '백만원', planValue: 1440, actualValue: 1425, diffValue: -15, diffRate: -1.04, profitEffect: 15, note: '일반관리비 예산 절감' },
    ]
  },
  {
    id: 'eff_lag',
    name: '재고·원가 반영시차 추정효과',
    category: 'LAG',
    categoryLabel: '시차효과',
    unit: '백만원',
    planValue: 0.0,
    actualValue: 0.0,
    diffValue: 0.0,
    diffRate: 0.0,
    profitEffect: 0,
    contributionRate: 0.0,
    impactDirection: 'NEUTRAL',
    description: '재고 회전 주기에 따른 원가 변동분 반영 시차 효과 (당월 중립)',
    drilldownRows: [
      { id: 'lag_item_1', subItemName: '원가 반영 시차분', unit: '백만원', planValue: 0, actualValue: 0, diffValue: 0, diffRate: 0, profitEffect: 0, note: '당월 반영시차 영향 중립' },
    ]
  }
];

export function buildWaterfallBars(planOpProfit: number, effects: VarianceEffectItem[]): WaterfallBarData[] {
  const bars: WaterfallBarData[] = [];

  // 1. Starting Bar: 계획 영업이익
  bars.push({
    id: 'start_plan',
    name: '계획 영업이익',
    category: 'START_TOTAL',
    startValue: 0,
    endValue: planOpProfit,
    delta: planOpProfit,
    isTotal: true,
    isStart: true,
    isEnd: false,
    colorType: 'start'
  });

  let runningTotal = planOpProfit;

  // 2. Incremental Effect Bars
  effects.forEach(eff => {
    if (eff.profitEffect === 0 && eff.category === 'LAG') return; // Skip 0 neutral in basic chart
    const start = runningTotal;
    const end = runningTotal + eff.profitEffect;
    runningTotal = end;

    bars.push({
      id: eff.id,
      name: eff.name,
      category: eff.category,
      startValue: start,
      endValue: end,
      delta: eff.profitEffect,
      isTotal: false,
      isStart: false,
      isEnd: false,
      colorType: eff.profitEffect >= 0 ? 'favorable' : 'unfavorable'
    });
  });

  // 3. Ending Bar: 실적 영업이익
  bars.push({
    id: 'end_actual',
    name: '실적 영업이익',
    category: 'END_TOTAL',
    startValue: 0,
    endValue: runningTotal,
    delta: runningTotal,
    isTotal: true,
    isStart: false,
    isEnd: true,
    colorType: 'end'
  });

  return bars;
}

export function getMockVarianceAnalysis(filter: VarianceFilterState): VarianceAnalysisResult {
  const isActual = filter.comparisonType === 'PLAN_VS_ACTUAL';
  const group = filter.productGroup;

  let planOp = 930;
  let actualOp = 1250;
  let effects = [...DUMMY_EFFECTS_ALL];

  if (group === 'SW') {
    planOp = 550;
    actualOp = 780;
    effects = DUMMY_EFFECTS_ALL.map(e => ({
      ...e,
      profitEffect: Math.round(e.profitEffect * 0.72),
      contributionRate: Math.round(e.contributionRate * 1.0)
    }));
  } else if (group === 'BW') {
    planOp = 280;
    actualOp = 320;
    effects = DUMMY_EFFECTS_ALL.map(e => ({
      ...e,
      profitEffect: Math.round(e.profitEffect * 0.18),
      contributionRate: Math.round(e.contributionRate * 1.0)
    }));
  } else if (group === 'LC') {
    planOp = 100;
    actualOp = 150;
    effects = DUMMY_EFFECTS_ALL.map(e => ({
      ...e,
      profitEffect: Math.round(e.profitEffect * 0.10),
      contributionRate: Math.round(e.contributionRate * 1.0)
    }));
  }

  const totalVariance = actualOp - planOp;
  const varianceRate = (totalVariance / planOp) * 100;
  const waterfallBars = buildWaterfallBars(planOp, effects);

  const groupLabel = group === 'ALL' ? '전사' : `${group} 제품군`;

  const executiveSummary = `${filter.baseMonth} ${groupLabel} 영업이익은 계획(${planOp.toLocaleString()}백만원) 대비 ${totalVariance > 0 ? '+' : ''}${totalVariance.toLocaleString()}백만원(${varianceRate.toFixed(1)}%) 증가한 ${actualOp.toLocaleString()}백만원을 기록하였습니다.\n` +
    `주요 긍정 요인은 판매수량 증가(+250백만원), 판가 개선(+90백만원), 변동비 절감(+60백만원), 매출환율 상승(+40백만원), 고정비 절감(+30백만원)이 견인하였습니다.\n` +
    `반면, 주요 원재료 매입단가 상승(-120백만원) 및 원재료 수입환율 상승(-30백만원)이 이익 증가분을 일부 상쇄하였습니다.`;

  return {
    baselineModelName: `${filter.baseMonth} Plan V2.1 (경영계획 확정본)`,
    comparisonModelName: isActual ? `${filter.baseMonth} Actual V1.0 (마감 실적)` : `${filter.baseMonth} Forecast V1.2 (최신 추정)`,
    baseMonth: filter.baseMonth,
    periodType: filter.periodType,
    comparisonType: filter.comparisonType,
    productGroup: filter.productGroup,
    planOpProfit: planOp,
    actualOpProfit: actualOp,
    totalVariance,
    varianceRate,
    effects,
    waterfallBars,
    executiveSummary,
    keyPositiveFactors: [
      '판매수량 증가 (+250 백만원, 기여율 78.1%)',
      '판가 개선 (+90 백만원, 기여율 28.1%)',
      '변동비 절감 (+60 백만원, 기여율 18.8%)',
      '매출환율 상승 효과 (+40 백만원, 기여율 12.5%)',
      '고정비 절감 (+30 백만원, 기여율 9.4%)'
    ],
    keyNegativeFactors: [
      '원재료 구매단가 상승 (-120 백만원, 기여율 -37.5%)',
      '원재료 수입환율 상승 (-30 백만원, 기여율 -9.4%)'
    ]
  };
}
