import { ScenarioType } from './common';

export type ModelType = 'PLAN' | 'ACTUAL' | 'FORECAST';
export type PublishedStatus = 'PUBLISHED' | 'DRAFT' | 'ARCHIVED';
export type CalculationJobStatus = 'IDLE' | 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';

export type ErrorCode =
  | 'INPUT_INTEGRITY_MISMATCH'
  | 'MISSING_FX_RATE'
  | 'UNBALANCED_COST_ALLOCATION'
  | 'SCHEMA_VERSION_MISMATCH';

export interface DataModelItem {
  id: string;
  modelName: string;
  modelType: ModelType;
  baseMonth: string;          // '2026-06'
  version: string;            // 'V2.1', 'V1.0'
  createdDate: string;        // '2026-06-05 14:32'
  createdBy: string;          // '경영기획팀 박준영 과장'
  publishedStatus: PublishedStatus;
  calculationStatus: 'COMPLETED' | 'PROCESSING' | 'PENDING' | 'FAILED' | 'NOT_STARTED';
  rowCount: number;
  checksum: string;           // 'sha256:7f9a...8b1c'
  description: string;
  isBaselineEligible: boolean;
  isComparisonEligible: boolean;
}

export interface CalculationStage {
  id: string;
  title: string;
  status: 'WAITING' | 'ACTIVE' | 'COMPLETED' | 'ERROR';
  detail: string;
}

export interface CalculationJob {
  id: string;
  baselineModelId: string;
  baselineModelName: string;
  comparisonModelId: string;
  comparisonModelName: string;
  status: CalculationJobStatus;
  progressPercent: number;
  currentStageIndex: number;
  stages: CalculationStage[];
  startedAt?: string;
  completedAt?: string;
  errorCode?: ErrorCode;
  errorMessage?: string;
  errorDetail?: string;
}

export interface ModelFilterState {
  modelType?: ModelType | 'ALL';
  baseMonth?: string;
  publishedStatus?: PublishedStatus | 'ALL';
  searchKeyword?: string;
}
