import type {
  ForecastAdjustmentMetadataDto,
  ForecastExcelPreviewDto,
  ForecastInputMetadataDto,
  ForecastMonthInputDto,
} from '../integration/types';

export type ForecastInputSection = 'sales' | 'production' | 'mcm';

export interface ForecastProductDefinition {
  code: string;
  category: 'SW' | 'BW' | 'LC' | 'FS' | '신사업' | 'OTHER';
  label: string;
  unit: 'PCS' | 'm' | 'L' | '—';
}

export interface ForecastBusinessProductionDefinition {
  key: string;
  process: '전공정' | '후공정';
  productGroup: 'SW' | 'BW' | 'TW' | 'LC';
  label: string;
  unit: 'PCS' | 'm';
}

export const SALES_PRODUCTS: readonly ForecastProductDefinition[] = [
  { code: 'SW400', category: 'SW', label: 'SW400', unit: 'PCS' },
  { code: 'SW440', category: 'SW', label: 'SW440', unit: 'PCS' },
  { code: 'BW400', category: 'BW', label: 'BW400', unit: 'PCS' },
  { code: 'BW440', category: 'BW', label: 'BW440', unit: 'PCS' },
  { code: 'LC', category: 'LC', label: 'LC(제품)', unit: 'PCS' },
  { code: 'LC_MERCHANDISE', category: 'LC', label: 'LC(상품)', unit: 'PCS' },
  { code: 'FS_SW', category: 'FS', label: 'FS SW', unit: 'm' },
  { code: 'FS_BW', category: 'FS', label: 'FS BW', unit: 'm' },
  { code: 'FS_TW', category: 'FS', label: 'FS TW', unit: 'm' },
  { code: 'UF_MBR', category: '신사업', label: 'UF/MBR', unit: '—' },
  { code: 'IX', category: '신사업', label: 'IX', unit: 'L' },
  { code: 'OTHER', category: 'OTHER', label: '기타매출', unit: '—' },
] as const;

// Legacy canonical product export retained for non-UI consumers. The Forecast
// form submits BUSINESS_PRODUCTION_ROWS and the backend performs allocation.
const PRODUCTION_PRODUCT_CODES = new Set([
  'SW400', 'SW440', 'BW400', 'BW440', 'LC', 'FS_SW', 'FS_BW', 'FS_TW',
]);
export const PRODUCTION_PRODUCTS: readonly ForecastProductDefinition[] = SALES_PRODUCTS.filter(
  ({ code }) => PRODUCTION_PRODUCT_CODES.has(code),
);

export const BUSINESS_PRODUCTION_ROWS: readonly ForecastBusinessProductionDefinition[] = [
  { key: 'front:SW', process: '전공정', productGroup: 'SW', label: 'SW', unit: 'm' },
  { key: 'front:BW', process: '전공정', productGroup: 'BW', label: 'BW', unit: 'm' },
  { key: 'front:TW', process: '전공정', productGroup: 'TW', label: 'TW', unit: 'm' },
  { key: 'back:SW', process: '후공정', productGroup: 'SW', label: 'SW', unit: 'PCS' },
  { key: 'back:BW', process: '후공정', productGroup: 'BW', label: 'BW', unit: 'PCS' },
  { key: 'back:LC', process: '후공정', productGroup: 'LC', label: 'LC (4인치)', unit: 'PCS' },
] as const;
export const MCM_PRODUCTS: readonly ForecastProductDefinition[] = SALES_PRODUCTS.slice(0, 4);

export interface ForecastAdjustmentFormValue {
  amount: string;
  reason: string;
}

export interface ForecastAdvancedFormState {
  manufacturingAdjustments: Record<string, ForecastAdjustmentFormValue>;
  sgaAdjustments: Record<string, ForecastAdjustmentFormValue>;
  disposalAdjustment: string;
  disposalReason: string;
  obsolescenceAdjustment: string;
  obsolescenceReason: string;
  newBusinessGoodsCogsMode: 'ACTUAL_YTD_DEFAULT' | 'MANUAL_OVERRIDE';
  newBusinessGoodsCogs: string;
  newBusinessGoodsCogsReason: string;
  ufMbrCogsRate: string;
  ixCogsRate: string;
  ufMbrTransportRate: string;
  ixTransportRate: string;
  ixPackLiters: string;
  ixPackCost: string;
  planNaSaSales: string;
  naSaSales: string;
  tariffApplicableRate: string;
  tariffRate: string;
  rawMaterialBasis: 'model' | 'direct';
  rawMaterialDirect: string;
  rawMaterialAdjustment: string;
  rawMaterialReason: string;
  refundRate: string;
}

interface SalesFormValue {
  quantity: string;
  amount: string;
}

interface QuantityFormValue {
  quantity: string;
}

export interface ForecastMonthFormState extends ForecastAdvancedFormState {
  month: number;
  sales: Record<string, SalesFormValue>;
  production: Record<string, QuantityFormValue>;
  mcm: Record<string, QuantityFormValue>;
}

export type ForecastInputState = Record<number, ForecastMonthFormState>;

export interface ForecastInputAdapterResult {
  value: ForecastMonthInputDto[] | null;
  error: string;
}

const salesValues = () => Object.fromEntries(
  SALES_PRODUCTS.map(({ code }) => [code, { quantity: '0', amount: '0' }]),
);

const quantityValues = (products: readonly { code: string }[]) => Object.fromEntries(
  products.map(({ code }) => [code, { quantity: '0' }]),
);

const businessProductionValues = () => Object.fromEntries(
  BUSINESS_PRODUCTION_ROWS.map(({ key }) => [key, { quantity: '0' }]),
);

const adjustmentValues = (items: readonly ForecastAdjustmentMetadataDto[]) => Object.fromEntries(
  items.map(({ adjustment_key }) => [adjustment_key, { amount: '0', reason: '' }]),
);

function advancedValues(metadata?: ForecastInputMetadataDto): ForecastAdvancedFormState {
  return {
    manufacturingAdjustments: adjustmentValues(metadata?.manufacturing ?? []),
    sgaAdjustments: adjustmentValues(metadata?.sga ?? []),
    disposalAdjustment: '0',
    disposalReason: '',
    obsolescenceAdjustment: '0',
    obsolescenceReason: '',
    newBusinessGoodsCogsMode: 'ACTUAL_YTD_DEFAULT',
    newBusinessGoodsCogs: '',
    newBusinessGoodsCogsReason: '',
    ufMbrCogsRate: '0.85',
    ixCogsRate: '0.85',
    ufMbrTransportRate: '0.10',
    ixTransportRate: '0.05',
    ixPackLiters: '25',
    ixPackCost: '380',
    planNaSaSales: '0',
    naSaSales: '0',
    tariffApplicableRate: '0.85',
    tariffRate: '0.10',
    rawMaterialBasis: 'model',
    rawMaterialDirect: '',
    rawMaterialAdjustment: '0',
    rawMaterialReason: '',
    refundRate: '0.013',
  };
}

export function createForecastMonthFormState(
  month: number,
  metadata?: ForecastInputMetadataDto,
): ForecastMonthFormState {
  return {
    month,
    sales: salesValues(),
    production: businessProductionValues(),
    mcm: quantityValues(MCM_PRODUCTS),
    ...advancedValues(metadata),
  };
}

function mergeAdjustmentValues(
  current: Record<string, ForecastAdjustmentFormValue>,
  items: readonly ForecastAdjustmentMetadataDto[],
): Record<string, ForecastAdjustmentFormValue> {
  const next = { ...current };
  items.forEach(({ adjustment_key }) => {
    if (!next[adjustment_key]) next[adjustment_key] = { amount: '0', reason: '' };
  });
  return next;
}

export function ensureForecastMonths(
  current: ForecastInputState,
  months: readonly number[],
  metadata?: ForecastInputMetadataDto,
): ForecastInputState {
  const next = { ...current };
  let changed = false;
  months.forEach((month) => {
    const existing = next[month];
    if (!existing) {
      next[month] = createForecastMonthFormState(month, metadata);
      changed = true;
      return;
    }
    const manufacturingAdjustments = mergeAdjustmentValues(existing.manufacturingAdjustments, metadata?.manufacturing ?? []);
    const sgaAdjustments = mergeAdjustmentValues(existing.sgaAdjustments, metadata?.sga ?? []);
    if (manufacturingAdjustments !== existing.manufacturingAdjustments || sgaAdjustments !== existing.sgaAdjustments) {
      next[month] = { ...existing, manufacturingAdjustments, sgaAdjustments };
      changed = true;
    }
  });
  return changed ? next : current;
}

export function hasForecastAdjustmentInput(
  value: ForecastMonthFormState | undefined,
  metadata?: ForecastInputMetadataDto,
): boolean {
  if (!value) return false;
  const defaults = createForecastMonthFormState(value.month, metadata);
  const hasAdjustmentRows = [
    ...Object.values(value.manufacturingAdjustments),
    ...Object.values(value.sgaAdjustments),
  ].some((entry) => (entry.amount.trim() !== '' && entry.amount.trim() !== '0') || entry.reason.trim() !== '');
  if (hasAdjustmentRows) return true;

  const fields: Array<keyof ForecastAdvancedFormState> = [
    'disposalAdjustment', 'disposalReason',
    'obsolescenceAdjustment', 'obsolescenceReason',
    'newBusinessGoodsCogsMode', 'newBusinessGoodsCogs', 'newBusinessGoodsCogsReason',
    'ufMbrCogsRate', 'ixCogsRate',
    'ufMbrTransportRate', 'ixTransportRate', 'ixPackLiters', 'ixPackCost',
    'planNaSaSales', 'naSaSales', 'tariffApplicableRate', 'tariffRate',
    'rawMaterialBasis', 'rawMaterialDirect', 'rawMaterialAdjustment', 'rawMaterialReason', 'refundRate',
  ];
  return fields.some((field) => value[field] !== defaults[field]);
}

export function findOutOfRangeForecastAdjustmentMonths(
  selectedMonths: readonly number[],
  state: ForecastInputState,
  metadata?: ForecastInputMetadataDto,
): number[] {
  const selected = new Set(selectedMonths);
  return Object.keys(state)
    .map(Number)
    .filter((month) => Number.isInteger(month) && !selected.has(month) && hasForecastAdjustmentInput(state[month], metadata))
    .sort((left, right) => left - right);
}

export function applyForecastExcelPreview(
  current: ForecastInputState,
  months: readonly number[],
  preview: ForecastExcelPreviewDto,
  metadata?: ForecastInputMetadataDto,
): ForecastInputState {
  if (!preview.valid || preview.blocking || preview.issues.some((issue) => issue.blocking)) {
    throw new Error('Blocking Excel preview cannot be applied');
  }
  const next = ensureForecastMonths(current, months, metadata);
  const monthSet = new Set(months);
  const salesCodes = new Set(SALES_PRODUCTS.map(({ code }) => code));
  const businessKeys = new Map(
    BUSINESS_PRODUCTION_ROWS.map((row) => [`${row.process}:${row.productGroup}:${row.unit}`, row.key]),
  );
  const replacement = Object.fromEntries(months.map((month) => [month, {
    sales: salesValues(),
    production: businessProductionValues(),
  }]));

  for (const row of preview.sales_rows) {
    if (!monthSet.has(row.month) || !salesCodes.has(row.product_code)) {
      throw new Error('Invalid sales preview row');
    }
    replacement[row.month].sales[row.product_code] = {
      quantity: String(row.quantity),
      amount: String(row.amount),
    };
  }
  for (const row of preview.business_production_rows) {
    const key = businessKeys.get(`${row.process}:${row.product_group}:${row.unit}`);
    if (!monthSet.has(row.month) || !key) {
      throw new Error('Invalid business production preview row');
    }
    replacement[row.month].production[key] = { quantity: String(row.quantity) };
  }

  return {
    ...next,
    ...Object.fromEntries(months.map((month) => [month, {
      ...next[month],
      sales: replacement[month].sales,
      production: replacement[month].production,
    }])),
  };
}

type ParsedValue = { value: number } | { error: string };
type ParsedReason = { value: string } | { error: string };

function parseNumber(
  value: string | undefined,
  label: string,
  options: { defaultValue: number; allowNegative?: boolean; max?: number; strictlyPositive?: boolean },
): ParsedValue {
  const trimmed = (value ?? '').trim();
  if (trimmed === '') return { value: options.defaultValue };
  const parsed = Number(trimmed);
  const valid = Number.isFinite(parsed)
    && (options.allowNegative || parsed >= 0)
    && (!options.strictlyPositive || parsed > 0)
    && (options.max === undefined || parsed <= options.max);
  return valid ? { value: parsed } : { error: `${label}을(를) ${options.allowNegative ? '유효한 숫자' : '0 이상의 숫자'}로 입력하세요.` };
}

function parseRequiredNumber(value: string | undefined, label: string, allowNegative = false): ParsedValue {
  const trimmed = (value ?? '').trim();
  if (trimmed === '') return { error: `${label}을(를) 입력하세요.` };
  return parseNumber(trimmed, label, { defaultValue: 0, allowNegative });
}

function parseReason(value: string | undefined, label: string): ParsedReason {
  const reason = value ?? '';
  return reason.length <= 500 ? { value: reason } : { error: `${label}은(는) 500자 이내로 입력하세요.` };
}

function invalidMessage(month: number, label: string, field: string): ForecastInputAdapterResult {
  return {
    value: null,
    error: `${month}월 ${label} ${field}`,
  };
}

export function adaptForecastInput(
  months: readonly number[],
  state: ForecastInputState,
  metadata?: ForecastInputMetadataDto,
): ForecastInputAdapterResult {
  const result: ForecastMonthInputDto[] = [];

  for (const month of months) {
    const form = state[month];
    if (!form || form.month !== month) {
      return { value: null, error: `${month}월 입력을 확인하세요.` };
    }

    const sales: ForecastMonthInputDto['sales'] = [];
    for (const product of SALES_PRODUCTS) {
      const row = form.sales[product.code];
      const quantity = parseRequiredNumber(row?.quantity, '판매수량');
      const amount = parseRequiredNumber(row?.amount, '매출액');
      if ('error' in quantity) return invalidMessage(month, product.label, quantity.error);
      if ('error' in amount) return invalidMessage(month, product.label, amount.error);
      sales.push({ product_code: product.code, quantity: quantity.value, amount: amount.value });
    }

    const businessProduction: NonNullable<ForecastMonthInputDto['business_production']> = [];
    for (const row of BUSINESS_PRODUCTION_ROWS) {
      const quantity = parseRequiredNumber(form.production[row.key]?.quantity, '생산수량');
      if ('error' in quantity) return invalidMessage(month, `${row.process} ${row.label}`, quantity.error);
      businessProduction.push({
        process: row.process,
        product_group: row.productGroup,
        quantity: quantity.value,
        unit: row.unit,
      });
    }

    const mcm: ForecastMonthInputDto['mcm'] = [];
    for (const product of MCM_PRODUCTS) {
      const quantity = parseRequiredNumber(form.mcm[product.code]?.quantity, 'MCM 수량');
      if ('error' in quantity) return invalidMessage(month, product.label, quantity.error);
      mcm.push({ product_code: product.code, quantity: quantity.value });
    }

    const manufacturingAdjustments: ForecastMonthInputDto['manufacturing_adjustments'] = [];
    for (const item of metadata?.manufacturing ?? []) {
      const entry = form.manufacturingAdjustments[item.adjustment_key] ?? { amount: '', reason: '' };
      const amount = parseNumber(entry.amount, `${item.display_name} 조정액`, { defaultValue: 0, allowNegative: true });
      const reason = parseReason(entry.reason, `${item.display_name} 사유`);
      if ('error' in amount) return { value: null, error: `${month}월 ${amount.error}` };
      if ('error' in reason) return { value: null, error: `${month}월 ${reason.error}` };
      if (amount.value !== 0 || reason.value.trim() !== '') {
        manufacturingAdjustments.push({ adjustment_key: item.adjustment_key, amount: amount.value, reason: reason.value });
      }
    }

    const sgaAdjustments: ForecastMonthInputDto['sga_adjustments'] = [];
    for (const item of metadata?.sga ?? []) {
      const entry = form.sgaAdjustments[item.adjustment_key] ?? { amount: '', reason: '' };
      const amount = parseNumber(entry.amount, `${item.display_name} 조정액`, { defaultValue: 0, allowNegative: true });
      const reason = parseReason(entry.reason, `${item.display_name} 사유`);
      if ('error' in amount) return { value: null, error: `${month}월 ${amount.error}` };
      if ('error' in reason) return { value: null, error: `${month}월 ${reason.error}` };
      if (amount.value !== 0 || reason.value.trim() !== '') {
        sgaAdjustments.push({ adjustment_key: item.adjustment_key, amount: amount.value, reason: reason.value });
      }
    }

    const disposalAdjustment = parseNumber(form.disposalAdjustment, '제품 폐기손실', { defaultValue: 0, allowNegative: true });
    const disposalReason = parseReason(form.disposalReason, '제품 폐기손실 사유');
    const obsolescenceAdjustment = parseNumber(form.obsolescenceAdjustment, '제품 진부화 평가손실', { defaultValue: 0, allowNegative: true });
    const obsolescenceReason = parseReason(form.obsolescenceReason, '제품 진부화 평가손실 사유');
    const goodsCogsReason = parseReason(form.newBusinessGoodsCogsReason, '신사업 매출원가 사유');
    if ('error' in disposalAdjustment || 'error' in disposalReason || 'error' in obsolescenceAdjustment || 'error' in obsolescenceReason
      || 'error' in goodsCogsReason) {
      const error = [disposalAdjustment, disposalReason, obsolescenceAdjustment, obsolescenceReason, goodsCogsReason]
        .find((item): item is { error: string } => 'error' in item);
      return { value: null, error: `${month}월 ${error?.error ?? '고급 입력을 확인하세요.'}` };
    }
    let manualGoodsCogs: number | undefined;
    let manualGoodsCogsReason: string | undefined;
    if (form.newBusinessGoodsCogsMode === 'MANUAL_OVERRIDE') {
      const goodsCogs = parseRequiredNumber(form.newBusinessGoodsCogs, '신사업 매출원가 직접 반영액');
      if ('error' in goodsCogs) return { value: null, error: `${month}월 ${goodsCogs.error}` };
      if (!goodsCogsReason.value.trim()) {
        return { value: null, error: `${month}월 신사업 매출원가 사유를 입력하세요.` };
      }
      manualGoodsCogs = goodsCogs.value;
      manualGoodsCogsReason = goodsCogsReason.value;
    } else if (form.newBusinessGoodsCogs.trim() || goodsCogsReason.value.trim()) {
      return {
        value: null,
        error: `${month}월 Actual YTD 자동 산출 모드에는 직접 반영액·사유를 함께 보낼 수 없습니다.`,
      };
    }

    const scalarFields: Array<[keyof ForecastAdvancedFormState, string, { defaultValue: number; allowNegative?: boolean; max?: number; strictlyPositive?: boolean }]> = [
      ['ufMbrCogsRate', 'UF/MBR 매출원가 비율', { defaultValue: 0.85, max: 1 }],
      ['ixCogsRate', 'IX 매출원가 비율', { defaultValue: 0.85, max: 1 }],
      ['ufMbrTransportRate', 'UF/MBR 운송비 비율', { defaultValue: 0.10, max: 1 }],
      ['ixTransportRate', 'IX 운송비 비율', { defaultValue: 0.05, max: 1 }],
      ['ixPackLiters', 'IX 포장 기준량', { defaultValue: 25, strictlyPositive: true }],
      ['ixPackCost', 'IX 포장 단가', { defaultValue: 380 }],
      ['planNaSaSales', '기준 북미·남미 매출', { defaultValue: 0 }],
      ['naSaSales', '추정 북미·남미 매출', { defaultValue: 0 }],
      ['tariffApplicableRate', '관세 적용 비율', { defaultValue: 0.85, max: 1 }],
      ['tariffRate', '관세율', { defaultValue: 0.10, max: 1 }],
      ['rawMaterialAdjustment', '원재료 조정액', { defaultValue: 0, allowNegative: true }],
      ['refundRate', '환급률', { defaultValue: 0.013, max: 1 }],
    ];
    const parsedScalars = scalarFields.map(([field, label, options]) => [field, parseNumber(form[field] as string, label, options)] as const);
    const scalarError = parsedScalars.find(([, parsed]) => 'error' in parsed)?.[1];
    if (scalarError && 'error' in scalarError) return { value: null, error: `${month}월 ${scalarError.error}` };
    const scalar = (field: keyof ForecastAdvancedFormState) => {
      const parsed = parsedScalars.find(([key]) => key === field)?.[1];
      return parsed && 'value' in parsed ? parsed.value : 0;
    };

    let rawMaterialDirect: number | null = null;
    if (form.rawMaterialBasis === 'direct') {
      const parsedDirect = parseRequiredNumber(form.rawMaterialDirect, '원재료 직접 입력액');
      if ('error' in parsedDirect) return { value: null, error: `${month}월 ${parsedDirect.error}` };
      rawMaterialDirect = parsedDirect.value;
    }
    const rawReason = parseReason(form.rawMaterialReason, '원재료 사유');
    if ('error' in rawReason) return { value: null, error: `${month}월 ${rawReason.error}` };

    result.push({
      month,
      sales,
      business_production: businessProduction,
      mcm,
      manufacturing_adjustments: manufacturingAdjustments,
      sga_adjustments: sgaAdjustments,
      disposal_adjustment: disposalAdjustment.value,
      disposal_reason: disposalReason.value,
      obsolescence_adjustment: obsolescenceAdjustment.value,
      obsolescence_reason: obsolescenceReason.value,
      new_business_goods_cogs_mode: form.newBusinessGoodsCogsMode,
      ...(form.newBusinessGoodsCogsMode === 'MANUAL_OVERRIDE' ? {
        new_business_goods_cogs: manualGoodsCogs,
        new_business_goods_cogs_reason: manualGoodsCogsReason,
      } : {}),
      uf_mbr_cogs_rate: scalar('ufMbrCogsRate'),
      ix_cogs_rate: scalar('ixCogsRate'),
      uf_mbr_transport_rate: scalar('ufMbrTransportRate'),
      ix_transport_rate: scalar('ixTransportRate'),
      ix_pack_liters: scalar('ixPackLiters'),
      ix_pack_cost: scalar('ixPackCost'),
      plan_na_sa_sales: scalar('planNaSaSales'),
      na_sa_sales: scalar('naSaSales'),
      tariff_applicable_rate: scalar('tariffApplicableRate'),
      tariff_rate: scalar('tariffRate'),
      raw_material_basis: form.rawMaterialBasis,
      raw_material_direct: rawMaterialDirect,
      raw_material_adjustment: scalar('rawMaterialAdjustment'),
      raw_material_reason: rawReason.value,
      refund_rate: scalar('refundRate'),
    });
  }

  return { value: result, error: '' };
}
