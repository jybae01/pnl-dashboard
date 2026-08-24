import { describe, expect, it } from 'vitest';
import { persistentDeleteReason, persistentDeleteSummary } from './persistentDeleteUi';


describe('persistent delete UI messaging', () => {
  it('distinguishes terminal result Storage cleanup from active model use', () => {
    expect(persistentDeleteReason({
      resource_id: 'model-1',
      status: 'BLOCKED_IN_USE',
      reason: 'MODEL_ANALYSIS_STORAGE_CLEANUP_REQUIRED',
      reference_counts: { analysis_storage_cleanup_required: 1 },
      idempotent_replayed: false,
    })).toBe('완료된 분석 결과 Storage를 먼저 정리해야 모형을 삭제할 수 있습니다.');
  });

  it('keeps batch counts aligned with item statuses', () => {
    expect(persistentDeleteSummary({
      resource_type: 'model',
      requested_count: 1,
      deleted_count: 0,
      cleanup_required_count: 0,
      blocked_count: 1,
      uncertain_count: 0,
      failed_count: 0,
      items: [{
        resource_id: 'model-1',
        status: 'BLOCKED_IN_USE',
        reason: 'MODEL_ANALYSIS_STORAGE_CLEANUP_REQUIRED',
        reference_counts: { analysis_storage_cleanup_required: 1 },
        idempotent_replayed: false,
      }],
      dto_version: '1',
    })).toBe('1건 요청 / 0건 삭제 / 0건 Storage 정리 필요 / 1건 차단 / 0건 상태 확인 필요 / 0건 실패');
  });
});
