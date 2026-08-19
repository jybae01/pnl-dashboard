// TEST-ONLY VISUAL FIXTURE.
// Values are inert rendering samples, not reporting truth and not a runtime fallback.
import type {
  PnlCogsRowSlot,
  PnlDisplayCell,
  PnlProductSegmentSlot,
  PnlReportingReadModel,
  PnlSgaRowSlot,
  PnlStatementRowSlot,
} from '../types/pnlReporting';

const PERIOD = '2026-06';
const RANGE = '1월:6월';

function cell(text: string, tone: PnlDisplayCell['tone'] = 'neutral', emphasis: PnlDisplayCell['emphasis'] = 'normal'): PnlDisplayCell {
  return { text, tone, emphasis };
}

function statementRow(
  key: string,
  label: string,
  unit: string,
  values: string[],
  options: Partial<Pick<PnlStatementRowSlot, 'level' | 'kind' | 'parentKey' | 'collapsible'>> = {},
): PnlStatementRowSlot {
  return {
    key,
    label,
    unit,
    level: options.level ?? 0,
    kind: options.kind ?? 'default',
    parentKey: options.parentKey,
    collapsible: options.collapsible,
    compareByPeriod: { [PERIOD]: values.slice(0, 8).map((value, index) => cell(value, [2, 3, 6, 7].includes(index) ? 'favorable' : 'neutral')) },
    actualOnly: ['101', '102', '103', '104', '105', '106', '621'].map((value) => cell(value)),
    customByRange: { [RANGE]: values.slice(0, 4).map((value) => cell(value)) },
  };
}

const pnlRows: PnlStatementRowSlot[] = [
  statementRow('revenue', 'Ⅰ. 매출액', '백만원', ['12,000', '12,500', '+500', '+4.17%', '69,700', '71,490', '+1,790', '+2.57%'], { kind: 'header', collapsible: true }),
  statementRow('rev_product', '1. 제품 매출', '백만원', ['9,700', '10,100', '+400', '+4.12%', '56,300', '57,900', '+1,600', '+2.84%'], { level: 1, parentKey: 'revenue' }),
  statementRow('rev_semi', '2. 반제품 매출', '백만원', ['1,400', '1,480', '+80', '+5.71%', '8,100', '8,350', '+250', '+3.09%'], { level: 1, parentKey: 'revenue' }),
  statementRow('rev_merch', '3. 상품 매출', '백만원', ['800', '820', '+20', '+2.50%', '4,600', '4,680', '+80', '+1.74%'], { level: 1, parentKey: 'revenue' }),
  statementRow('rev_other', '4. 기타 매출', '백만원', ['300', '310', '+10', '+3.33%', '1,800', '1,820', '+20', '+1.11%'], { level: 1, parentKey: 'revenue' }),
  statementRow('rev_rebate', '5. 판매장려금', '백만원', ['-200', '-210', '-10', '+5.00%', '-1,100', '-1,260', '-160', '+14.55%'], { level: 1, parentKey: 'revenue' }),
  statementRow('sales_volume', 'Ⅱ. 매출수량', '-', ['—', '—', '—', '—', '—', '—', '—', '—'], { kind: 'header', collapsible: true }),
  statementRow('volume_sw', '8인치 SW', 'PCS', ['180,000', '205,000', '+25,000', '+13.89%', '1,050,000', '1,140,000', '+90,000', '+8.57%'], { level: 1, parentKey: 'sales_volume' }),
  statementRow('volume_bw', '8인치 BW', 'PCS', ['220,000', '240,000', '+20,000', '+9.09%', '1,280,000', '1,350,000', '+70,000', '+5.47%'], { level: 1, parentKey: 'sales_volume' }),
  statementRow('volume_lc', '4인치 LC', 'PCS', ['50,000', '48,000', '-2,000', '-4.00%', '290,000', '285,000', '-5,000', '-1.72%'], { level: 1, parentKey: 'sales_volume' }),
  statementRow('volume_fs', '반제품 (FS)', 'm', ['125,000', '135,000', '+10,000', '+8.00%', '750,000', '780,000', '+30,000', '+4.00%'], { level: 1, parentKey: 'sales_volume' }),
  statementRow('cogs', 'Ⅲ. 매출원가', '백만원', ['9,680', '9,850', '+170', '+1.76%', '56,180', '56,950', '+770', '+1.37%'], { kind: 'header', collapsible: true }),
  statementRow('cogs_product', '1. 제품 매출원가', '백만원', ['7,800', '7,920', '+120', '+1.54%', '45,200', '45,800', '+600', '+1.33%'], { level: 1, parentKey: 'cogs' }),
  statementRow('cogs_semi', '2. 반제품 매출원가', '백만원', ['1,100', '1,140', '+40', '+3.64%', '6,400', '6,550', '+150', '+2.34%'], { level: 1, parentKey: 'cogs' }),
  statementRow('cogs_merch', '3. 상품 매출원가', '백만원', ['620', '630', '+10', '+1.61%', '3,600', '3,650', '+50', '+1.39%'], { level: 1, parentKey: 'cogs' }),
  statementRow('cogs_other', '4. 기타 매출원가', '백만원', ['160', '140', '-20', '-12.50%', '980', '920', '-60', '-6.12%'], { level: 1, parentKey: 'cogs' }),
  statementRow('cogs_inventory_loss', '5. 재고자산 평가손실', '백만원', ['0', '20', '+20', '—', '0', '30', '+30', '—'], { level: 1, parentKey: 'cogs' }),
  statementRow('cogs_ratio', '매출원가율', '%', ['80.67%', '78.80%', '-1.87%p', '-1.87%p', '80.60%', '79.66%', '-0.94%p', '-0.94%p']),
  statementRow('gross_profit', 'Ⅳ. 매출총이익', '백만원', ['2,320', '2,650', '+330', '+14.22%', '13,520', '14,540', '+1,020', '+7.54%'], { kind: 'total' }),
  statementRow('gross_margin', '매출총이익률', '%', ['19.33%', '21.20%', '+1.87%p', '+1.87%p', '19.40%', '20.34%', '+0.94%p', '+0.94%p']),
  statementRow('sga', 'Ⅴ. 판매비와 관리비', '백만원', ['1,390', '1,400', '+10', '+0.72%', '8,250', '9,040', '+790', '+9.58%'], { kind: 'header' }),
  statementRow('operating_profit', 'Ⅵ. 영업이익', '백만원', ['930', '1,250', '+320', '+34.41%', '5,270', '5,500', '+230', '+4.36%'], { kind: 'total' }),
  statementRow('operating_margin', '영업이익률', '%', ['7.75%', '10.00%', '+2.25%p', '+2.25%p', '7.56%', '7.69%', '+0.13%p', '+0.13%p']),
  statementRow('adjusted_operating_profit', 'Ⅶ. 조정 영업이익', '백만원', ['1,080', '1,430', '+350', '+32.41%', '5,900', '6,320', '+420', '+7.12%'], { kind: 'total' }),
  statementRow('adjusted_operating_margin', '조정 영업이익률', '%', ['9.00%', '11.44%', '+2.44%p', '+2.44%p', '8.46%', '8.84%', '+0.38%p', '+0.38%p']),
];

const sgaRows: PnlSgaRowSlot[] = [
  ...[
    ['admin', '일반관리비 소계', '일반관리비', 0, 'header'], ['admin_labor', '1. 인건비', '일반관리비', 1, 'default'], ['admin_depr', '2. 감가상각비', '일반관리비', 1, 'default'], ['admin_rnd', '3. 경상개발비', '일반관리비', 1, 'default'], ['admin_fee', '4. 수수료', '일반관리비', 1, 'default'], ['admin_other', '5. 기타', '일반관리비', 1, 'default'],
    ['sales', '판매비 소계', '판매비', 0, 'header'], ['sales_freight', '1. 운반비', '판매비', 1, 'default'], ['sales_commission', '2. 수수료', '판매비', 1, 'default'], ['sales_brand', '3. 브랜드사용료', '판매비', 1, 'default'], ['sales_labor', '4. 인건비', '판매비', 1, 'default'], ['sales_sample', '5. 견본비', '판매비', 1, 'default'], ['sales_bad_debt', '6. 대손상각', '판매비', 1, 'default'], ['sales_sundry', '7. 잡비', '판매비', 1, 'default'], ['sales_other', '8. 기타', '판매비', 1, 'default'], ['sga_total', '판관비 총계', '총계', 2, 'total'],
  ].map(([key, label, category, level, kind]) => ({ ...statementRow(String(key), String(label), '백만원', ['60', '55', '-5', '-8.33%', '360', '340', '-20', '-5.56%'], { level: level as 0 | 1 | 2, kind: kind as 'default' | 'header' | 'total', collapsible: key === 'admin_other' || key === 'sales_other' }), category: String(category) })),
  ...['• 통신비', '• 소모품비', '• 도서인쇄비', '• 기타 잡비'].map((label, index) => ({ ...statementRow(`admin_other_${index + 1}`, label, '백만원', ['15', '14', '-1', '-6.67%', '90', '85', '-5', '-5.56%'], { level: 2, parentKey: 'admin_other' }), category: '세부항목' })),
  ...['• 포장재료비', '• 보관료/창고료', '• 기타 판매부대비'].map((label, index) => ({ ...statementRow(`sales_other_${index + 1}`, label, '백만원', ['12', '12', '0', '0.00%', '72', '72', '0', '0.00%'], { level: 2, parentKey: 'sales_other' }), category: '세부항목' })),
];

function productSegment(key: string, label: string, businessUnit: 'PCS' | 'm', dimensionLabel: string, newBusiness = false): PnlProductSegmentSlot {
  const volumeRows = newBusiness ? [] : [
    statementRow(`${key}_volume`, '2. 매출수량', businessUnit, ['120', '126', '+6', '+5.0%', '680', '710', '+30', '+4.4%']),
    statementRow(`${key}_asp`, '3. 평균 판매 단가(ASP)', '원', ['9,800', '9,920', '+120', '+1.2%', '9,750', '9,860', '+110', '+1.1%']),
  ];
  const rows = [
    statementRow(`${key}_revenue`, '1. 매출액', '백만원', ['340', '355', '+15', '+4.4%', '1,940', '2,030', '+90', '+4.6%'], { kind: 'header' }),
    ...volumeRows,
    statementRow(`${key}_cogs`, `${newBusiness ? '2' : '4'}. 매출원가`, '백만원', ['220', '225', '+5', '+2.3%', '1,260', '1,285', '+25', '+2.0%']),
    statementRow(`${key}_cogs_ratio`, '• 매출원가율', '%', ['64.7%', '63.4%', '-1.3%p', '-1.3%p', '64.9%', '63.3%', '-1.6%p', '-1.6%p'], { level: 1 }),
    statementRow(`${key}_gp`, `${newBusiness ? '3' : '5'}. 매출총이익`, '백만원', ['120', '130', '+10', '+8.3%', '680', '745', '+65', '+9.6%'], { kind: 'total' }),
    statementRow(`${key}_gp_margin`, '• 매출총이익률', '%', ['35.3%', '36.6%', '+1.3%p', '+1.3%p', '35.1%', '36.7%', '+1.6%p', '+1.6%p'], { level: 1 }),
    statementRow(`${key}_sga`, `${newBusiness ? '4' : '6'}. 판매관리비`, '백만원', ['56', '58', '+2', '+3.6%', '320', '340', '+20', '+6.3%']),
    statementRow(`${key}_op`, `${newBusiness ? '5' : '7'}. 영업이익`, '백만원', ['64', '72', '+8', '+12.5%', '360', '405', '+45', '+12.5%'], { kind: 'total' }),
    statementRow(`${key}_op_margin`, '• 영업이익률', '%', ['18.8%', '20.3%', '+1.5%p', '+1.5%p', '18.6%', '20.0%', '+1.4%p', '+1.4%p'], { level: 1 }),
  ].map((row) => ({ ...row, customByRange: { [RANGE]: row.customByRange[RANGE].slice(0, 3) } }));
  return {
    key,
    label,
    businessUnit,
    dimensionLabel,
    rows,
  };
}

const cogsRows: PnlCogsRowSlot[] = ['원부재료비', '노무비', '외주가공비', '기타 제조경비', '합계'].map((label, index) => ({
  key: `cogs_${index}`,
  label,
  kind: index === 4 ? 'total' : 'default',
  cells: ['72', '5.8%', '75', '5.7%', '77', '5.9%', '74', '5.6%', '79', '5.8%', '81', '5.9%', '458', '34.9%'].map((value) => cell(value)),
}));

export const pnlReportingVisualFixture: PnlReportingReadModel = {
  reportKey: 'test-only-visual-fixture',
  year: 2026,
  availableYears: [2026, 2025],
  periods: Array.from({ length: 6 }, (_, index) => ({ key: `2026-0${index + 1}`, label: `${index + 1}월`, isActual: true })),
  selectedPeriodKey: PERIOD,
  actualPeriodKeys: ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05', PERIOD],
  defaultCustomRangeKey: RANGE,
  kpis: [
    { key: 'revenue', label: '매출액', amountText: '7,420', unitText: '백만원', progressText: '61.8%', achievementText: '104.5%', tone: 'favorable' },
    { key: 'operating_profit', label: '영업이익', amountText: '1,090', unitText: '백만원', progressText: '58.2%', achievementText: '121.1%', tone: 'favorable' },
    { key: 'adjusted_operating_profit', label: '조정 영업이익', amountText: '1,140', unitText: '백만원', progressText: '60.4%', achievementText: '118.7%', tone: 'favorable' },
  ],
  monthlyTrends: Array.from({ length: 6 }, (_, index) => ({
    periodKey: `2026-0${index + 1}`, label: `${index + 1}월`, isActual: true,
    planRevenue: 10800 + index * 240, actualRevenue: 10950 + index * 310, planRevenueText: String(10800 + index * 240), actualRevenueText: String(10950 + index * 310),
    planOperatingProfit: 780 + index * 30, actualOperatingProfit: 810 + index * 88, actualOperatingMargin: 7.4 + index * .52, planOperatingProfitText: String(780 + index * 30), actualOperatingProfitText: String(810 + index * 88), actualOperatingMarginText: `${(7.4 + index * .52).toFixed(1)}%`,
    planAdjustedOperatingProfit: 890 + index * 42, actualAdjustedOperatingProfit: 940 + index * 86, actualAdjustedOperatingMargin: 8.6 + index * .48, planAdjustedOperatingProfitText: String(890 + index * 42), actualAdjustedOperatingProfitText: String(940 + index * 86), actualAdjustedOperatingMarginText: `${(8.6 + index * .48).toFixed(1)}%`,
  })),
  monthlyDataRows: [
    ['매출액 계획', 'revenue-plan'],
    ['매출액 실적', 'revenue-actual'],
    ['영업이익 계획', 'operating-plan'],
    ['영업이익 실적', 'operating-actual'],
    ['영업이익률', 'operating-margin'],
    ['조정 영업이익 계획', 'adjusted-plan'],
    ['조정 영업이익 실적', 'adjusted-actual'],
    ['조정 영업이익률', 'adjusted-margin'],
  ].map(([label, tone], index) => ({ key: `monthly_${index}`, label, tone: tone as PnlReportingReadModel['monthlyDataRows'][number]['tone'], cells: Array.from({ length: 6 }, (_, cellIndex) => cell(`${100 + index * 10 + cellIndex}`)) })),
  pnlRows,
  cogsRows,
  sgaRows,
  productSegments: [
    productSegment('SW', '8인치 SW', 'PCS', '8-inch'),
    productSegment('BW', '8인치 BW', 'PCS', '8-inch'),
    productSegment('LC', '4인치 LC', 'PCS', '4-inch'),
    productSegment('new_business', '신사업', 'PCS', 'item', true),
  ],
};
