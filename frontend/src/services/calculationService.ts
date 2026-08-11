import { ICalculationService } from '../types/service';
import { CalculationJob, CalculationStage } from '../types/model';
import { CALCULATION_STAGES_TEMPLATE } from '../mocks/dummyModelData';
import { DUMMY_MODELS } from '../mocks/dummyModelData';

export class MockCalculationService implements ICalculationService {
  private activeJobs: Map<string, CalculationJob> = new Map();

  async startJob(baselineModelId: string, comparisonModelId: string, simulateError: boolean = false): Promise<CalculationJob> {
    const baseModel = DUMMY_MODELS.find(m => m.id === baselineModelId) || { modelName: '기준 모델' };
    const compModel = DUMMY_MODELS.find(m => m.id === comparisonModelId) || { modelName: '비교 모델' };

    const stages: CalculationStage[] = CALCULATION_STAGES_TEMPLATE.map(s => ({
      ...s,
      status: 'WAITING' as const
    }));

    const jobId = `job_${Date.now()}`;
    const job: CalculationJob = {
      id: jobId,
      baselineModelId,
      baselineModelName: baseModel.modelName,
      comparisonModelId,
      comparisonModelName: compModel.modelName,
      status: 'PENDING',
      progressPercent: 0,
      currentStageIndex: 0,
      stages,
      startedAt: new Date().toISOString().replace('T', ' ').substring(0, 19),
    };

    this.activeJobs.set(jobId, job);
    return { ...job };
  }

  async getJobStatus(jobId: string): Promise<CalculationJob | null> {
    const job = this.activeJobs.get(jobId);
    if (!job) return null;
    return { ...job, stages: job.stages.map(s => ({ ...s })) };
  }

  async cancelJob(jobId: string): Promise<boolean> {
    const job = this.activeJobs.get(jobId);
    if (job && (job.status === 'PENDING' || job.status === 'PROCESSING')) {
      job.status = 'IDLE';
      return true;
    }
    return false;
  }

  async downloadAnalysisWorkbook(jobId?: string): Promise<boolean> {
    await new Promise(r => setTimeout(r, 100));
    // In Mock mode, simply acknowledge the action (Real backend PR will handle binary stream/download URL)
    return true;
  }

  // Helper method for UI simulation runner to step through
  updateJobProgress(
    jobId: string,
    status: CalculationJob['status'],
    progress: number,
    stageIndex: number,
    stageStatus: CalculationStage['status'],
    error?: { code: CalculationJob['errorCode']; message: string; detail: string }
  ) {
    const job = this.activeJobs.get(jobId);
    if (!job) return;

    job.status = status;
    job.progressPercent = progress;
    job.currentStageIndex = stageIndex;

    if (stageIndex >= 0 && stageIndex < job.stages.length) {
      job.stages[stageIndex].status = stageStatus;
    }

    if (error) {
      job.errorCode = error.code;
      job.errorMessage = error.message;
      job.errorDetail = error.detail;
      job.status = 'FAILED';
    }

    if (status === 'COMPLETED') {
      job.completedAt = new Date().toISOString().replace('T', ' ').substring(0, 19);
      job.stages.forEach(s => s.status = 'COMPLETED');
    }
  }
}

export const calculationService = new MockCalculationService();
