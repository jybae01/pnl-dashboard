import { IModelService } from '../types/service';
import { DataModelItem, ModelFilterState } from '../types/model';
import { DUMMY_MODELS } from '../mocks/dummyModelData';

export class MockModelService implements IModelService {
  private models: DataModelItem[] = [...DUMMY_MODELS];

  async getModels(filter?: ModelFilterState): Promise<DataModelItem[]> {
    await new Promise(r => setTimeout(r, 100));
    let result = [...this.models];

    if (filter) {
      if (filter.modelType && filter.modelType !== 'ALL') {
        result = result.filter(m => m.modelType === filter.modelType);
      }
      if (filter.baseMonth) {
        result = result.filter(m => m.baseMonth === filter.baseMonth);
      }
      if (filter.publishedStatus && filter.publishedStatus !== 'ALL') {
        result = result.filter(m => m.publishedStatus === filter.publishedStatus);
      }
      if (filter.searchKeyword) {
        const kw = filter.searchKeyword.toLowerCase();
        result = result.filter(m =>
          m.modelName.toLowerCase().includes(kw) ||
          m.createdBy.toLowerCase().includes(kw) ||
          m.description.toLowerCase().includes(kw)
        );
      }
    }

    return result;
  }

  async getModelById(id: string): Promise<DataModelItem | null> {
    await new Promise(r => setTimeout(r, 50));
    return this.models.find(m => m.id === id) || null;
  }

  async createModel(data: Partial<DataModelItem>): Promise<DataModelItem> {
    await new Promise(r => setTimeout(r, 200));
    const newModel: DataModelItem = {
      id: `model_mock_${Date.now()}`,
      modelName: data.modelName || '새 데이터 모델',
      modelType: data.modelType || 'ACTUAL',
      baseMonth: data.baseMonth || '2026-06',
      version: data.version || 'V1.0',
      createdDate: new Date().toISOString().replace('T', ' ').substring(0, 16),
      createdBy: '경영기획팀 (사용자 등록)',
      publishedStatus: 'DRAFT',
      calculationStatus: 'NOT_STARTED',
      rowCount: data.rowCount || 15400,
      checksum: `sha256:${Math.random().toString(16).substring(2, 10)}...`,
      description: data.description || '신규 업로드 모델 (검증 대기)',
      isBaselineEligible: data.modelType === 'PLAN' || data.modelType === 'ACTUAL',
      isComparisonEligible: true,
    };
    this.models.unshift(newModel);
    return newModel;
  }

  async updateModelStatus(id: string, status: 'PUBLISHED' | 'DRAFT' | 'ARCHIVED'): Promise<boolean> {
    await new Promise(r => setTimeout(r, 100));
    const target = this.models.find(m => m.id === id);
    if (target) {
      target.publishedStatus = status;
      return true;
    }
    return false;
  }

  async deleteModels(ids: string[]): Promise<boolean> {
    await new Promise(r => setTimeout(r, 150));
    this.models = this.models.filter(m => !ids.includes(m.id));
    return true;
  }
}

export const modelService = new MockModelService();
