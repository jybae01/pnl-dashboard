import type { ForecastMonthInputDto } from '../integration/types';

export type ForecastInputSection = 'sales' | 'production' | 'mcm';

export interface ForecastProductDefinition {
  code: string;
  label: string;
  unit: 'PCS' | 'm' | 'L' | '—';
}

export const SALES_PRODUCTS: readonly ForecastProductDefinition[] = [
  { code: 'SW400', label: 'SW400', unit: 'PCS' },
  { code: 'SW440', label: 'SW440', unit: 'PCS' },
  { code: 'BW400', label: 'BW400', unit: 'PCS' },
  { code: 'BW440', label: 'BW440', unit: 'PCS' },
  { code: 'LC', label: 'LC (4인치)', unit: 'PCS' },
  { code: 'FS_SW', label: 'FS SW', unit: 'm' },
  { code: 'FS_BW', label: 'FS BW', unit: 'm' },
  { code: 'FS_TW', label: 'FS TW', unit: 'm' },
  { code: 'UF_MBR', label: 'UF/MBR', unit: '—' },
  { code: 'IX', label: 'IX', unit: 'L' },
  { code: 'OTHER', label: '기타매출', unit: '—' },
] as const;

export const PRODUCTION_PRODUCTS: readonly ForecastProductDefinition[] = SALES_PRODUCTS.slice(0, 8);
export const MCM_PRODUCTS: readonly ForecastProductDefinition[] = SALES_PRODUCTS.slice(0, 4);

interface SalesFormValue {
  quantity: string;
  amount: string;
}

interface QuantityFormValue {
  quantity: string;
}

export interface ForecastMonthFormState {
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

const quantityValues = (products: readonly ForecastProductDefinition[]) => Object.fromEntries(
  products.map(({ code }) => [code, { quantity: '0' }]),
);

export function createForecastMonthFormState(month: number): ForecastMonthFormState {
  return {
    month,
    sales: salesValues(),
    production: quantityValues(PRODUCTION_PRODUCTS),
    mcm: quantityValues(MCM_PRODUCTS),
  };
}

export function ensureForecastMonths(
  current: ForecastInputState,
  months: readonly number[],
): ForecastInputState {
  const next = { ...current };
  let changed = false;
  months.forEach((month) => {
    if (!next[month]) {
      next[month] = createForecastMonthFormState(month);
      changed = true;
    }
  });
  return changed ? next : current;
}

function nonnegativeNumber(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === '') return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function invalidMessage(month: number, label: string, field: string): ForecastInputAdapterResult {
  return {
    value: null,
    error: `${month}월 ${label} ${field}을(를) 0 이상의 숫자로 입력하세요.`,
  };
}

export function adaptForecastInput(
  months: readonly number[],
  state: ForecastInputState,
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
      const quantity = nonnegativeNumber(row?.quantity ?? '');
      const amount = nonnegativeNumber(row?.amount ?? '');
      if (quantity === null) return invalidMessage(month, product.label, '판매수량');
      if (amount === null) return invalidMessage(month, product.label, '매출액');
      sales.push({ product_code: product.code, quantity, amount });
    }

    const production: ForecastMonthInputDto['production'] = [];
    for (const product of PRODUCTION_PRODUCTS) {
      const quantity = nonnegativeNumber(form.production[product.code]?.quantity ?? '');
      if (quantity === null) return invalidMessage(month, product.label, '생산수량');
      production.push({ product_code: product.code, quantity });
    }

    const mcm: ForecastMonthInputDto['mcm'] = [];
    for (const product of MCM_PRODUCTS) {
      const quantity = nonnegativeNumber(form.mcm[product.code]?.quantity ?? '');
      if (quantity === null) return invalidMessage(month, product.label, 'MCM 수량');
      mcm.push({ product_code: product.code, quantity });
    }

    result.push({
      month,
      sales,
      production,
      mcm,
      manufacturing_adjustments: [],
      sga_adjustments: [],
    });
  }

  return { value: result, error: '' };
}
