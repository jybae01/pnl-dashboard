import { IVarianceService } from '../types/service';
import {
  VarianceAnalysisResult,
  VarianceFilterState,
  DrilldownDetailRow
} from '../types/variance';
import { getMockVarianceAnalysis } from '../mocks/dummyVarianceData';

export class MockVarianceService implements IVarianceService {
  async getVarianceAnalysis(filter: VarianceFilterState): Promise<VarianceAnalysisResult> {
    await new Promise(r => setTimeout(r, 160)); // Simulated async latency
    return getMockVarianceAnalysis(filter);
  }

  async getEffectDrilldown(effectId: string, filter: VarianceFilterState): Promise<DrilldownDetailRow[]> {
    await new Promise(r => setTimeout(r, 100));
    const analysis = getMockVarianceAnalysis(filter);
    const target = analysis.effects.find(e => e.id === effectId);
    return target ? target.drilldownRows : [];
  }
}

export const varianceService = new MockVarianceService();
