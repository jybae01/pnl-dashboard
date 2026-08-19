import { bffClient } from './client';
import { ApiClientError } from './types';
import {
  parsePnlReportingLoadResult,
  PnlReportingSourceError,
  type PnlReportingLoadResult,
  type PnlReportingSource,
} from '../types/pnlReporting';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function adaptViewerDto(value: unknown): PnlReportingLoadResult {
  if (!isRecord(value)
    || value.dtoVersion !== '1'
    || !['DATA_READY', 'REPORTING_GAP'].includes(String(value.state))
    || !['MISSING_BOTH', 'MISSING_PLAN', 'MISSING_ACTUAL', 'READY'].includes(String(value.reportingState))) {
    throw new PnlReportingSourceError('INVALID_PAYLOAD', 'P&L Reporting response envelope is invalid');
  }
  const ready = value.reportingState === 'READY';
  if ((ready && value.state !== 'DATA_READY') || (!ready && value.state !== 'REPORTING_GAP')) {
    throw new PnlReportingSourceError('INVALID_PAYLOAD', 'P&L Reporting response state is inconsistent');
  }

  let report: unknown = null;
  if (ready) {
    if (!isRecord(value.report) || !isRecord(value.report.identity) || !Array.isArray(value.report.identity.periods)) {
      throw new PnlReportingSourceError('INVALID_PAYLOAD', 'P&L Reporting report identity is invalid');
    }
    const periods = value.report.identity.periods.map((period) => {
      if (!isRecord(period)
        || typeof period.periodKey !== 'string'
        || typeof period.label !== 'string'
        || typeof period.actualAvailable !== 'boolean') {
        throw new PnlReportingSourceError('INVALID_PAYLOAD', 'P&L Reporting period identity is invalid');
      }
      return { key: period.periodKey, label: period.label, isActual: period.actualAvailable };
    });
    report = {
      ...value.report,
      ...value.report.identity,
      periods,
    };
  } else if (value.report !== null) {
    throw new PnlReportingSourceError('INVALID_PAYLOAD', 'P&L Reporting gap response included a report');
  }

  const parsed = parsePnlReportingLoadResult({
    reportingState: value.reportingState,
    metadata: value.metadata,
    report,
  });
  if (!parsed) throw new PnlReportingSourceError('INVALID_PAYLOAD', 'P&L Reporting response validation failed');
  return deepFreeze(parsed);
}

function deepFreeze<T>(value: T): T {
  if (typeof value !== 'object' || value === null || Object.isFrozen(value)) return value;
  Object.freeze(value);
  Object.values(value as Record<string, unknown>).forEach(deepFreeze);
  return value;
}

export const pnlReportingSource: PnlReportingSource = {
  async load(year, signal) {
    try {
      return adaptViewerDto(await bffClient.pnlReporting(year, signal));
    } catch (error) {
      if (signal.aborted) throw error;
      if (error instanceof PnlReportingSourceError) throw error;
      if (error instanceof ApiClientError && (error.status === 403 || error.code === 'FORBIDDEN')) {
        throw new PnlReportingSourceError('FORBIDDEN', 'P&L Reporting access is forbidden');
      }
      if (error instanceof ApiClientError && error.code === 'INPUT_INTEGRITY_MISMATCH') {
        throw new PnlReportingSourceError('INVALID_PAYLOAD', 'P&L Reporting integrity validation failed');
      }
      throw new PnlReportingSourceError('ERROR', 'P&L Reporting request failed');
    }
  },
};

export const __testOnlyAdaptPnlReportingViewerDto = adaptViewerDto;
