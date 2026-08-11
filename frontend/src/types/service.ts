import {
  PnlKpiSummary,
  MonthlyTrendItem,
  PnlLineItem,
  MfgCostBreakdownItem,
  SgaBreakdownItem,
  ProductSegmentPnl,
  KeyVarianceNote,
  PnlFilterState
} from './pnl';
import {
  VarianceAnalysisResult,
  VarianceFilterState,
  DrilldownDetailRow
} from './variance';
import {
  DataModelItem,
  CalculationJob,
  ModelFilterState
} from './model';

export interface IPnlService {
  getKpiSummary(filter: PnlFilterState): Promise<PnlKpiSummary>;
  getMonthlyTrends(year: number, productGroup: string): Promise<MonthlyTrendItem[]>;
  getPnlTable(filter: PnlFilterState): Promise<PnlLineItem[]>;
  getMfgCostBreakdown(filter: PnlFilterState): Promise<MfgCostBreakdownItem[]>;
  getSgaBreakdown(filter: PnlFilterState): Promise<SgaBreakdownItem[]>;
  getItemSegmentPnl(filter: PnlFilterState): Promise<ProductSegmentPnl[]>;
  getKeyNotes(filter: PnlFilterState): Promise<KeyVarianceNote[]>;
}

export interface IVarianceService {
  getVarianceAnalysis(filter: VarianceFilterState): Promise<VarianceAnalysisResult>;
  getEffectDrilldown(effectId: string, filter: VarianceFilterState): Promise<DrilldownDetailRow[]>;
}

export interface IModelService {
  getModels(filter?: ModelFilterState): Promise<DataModelItem[]>;
  getModelById(id: string): Promise<DataModelItem | null>;
  createModel(model: Partial<DataModelItem>): Promise<DataModelItem>;
  updateModelStatus(id: string, status: 'PUBLISHED' | 'DRAFT' | 'ARCHIVED'): Promise<boolean>;
  deleteModels(ids: string[]): Promise<boolean>;
}

export interface ICalculationService {
  startJob(baselineModelId: string, comparisonModelId: string, simulateError?: boolean): Promise<CalculationJob>;
  getJobStatus(jobId: string): Promise<CalculationJob | null>;
  cancelJob(jobId: string): Promise<boolean>;
  downloadAnalysisWorkbook(jobId?: string): Promise<boolean>;
}
