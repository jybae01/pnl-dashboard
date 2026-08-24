import { PersistentDeleteBatchDto, PersistentDeleteItemDto } from './types';

export function persistentDeleteSummary(result: PersistentDeleteBatchDto): string {
  return `${result.requested_count}건 요청 / ${result.deleted_count}건 삭제 / ${result.cleanup_required_count}건 Storage 정리 필요 / ${result.blocked_count}건 차단 / ${result.uncertain_count}건 상태 확인 필요 / ${result.failed_count}건 실패`;
}

export function persistentDeleteReason(item: PersistentDeleteItemDto): string {
  switch (item.reason) {
    case 'MODEL_IN_USE': return '분석·Forecast 등에서 사용 중입니다.';
    case 'MODEL_ANALYSIS_STORAGE_CLEANUP_REQUIRED': return '완료된 분석 결과 Storage를 먼저 정리해야 모형을 삭제할 수 있습니다.';
    case 'NON_TERMINAL_ANALYSIS_DELETE_BLOCKED': return '실행 대기 또는 처리 중인 분석입니다.';
    case 'DELETE_PROTECTED_RESOURCE': return '기본 또는 공개 상태를 먼저 해제해야 삭제할 수 있습니다.';
    case 'RESOURCE_NOT_FOUND': return '이미 삭제되었거나 찾을 수 없습니다.';
    case 'DB_DELETED_STORAGE_CLEANUP_REQUIRED': return 'DB 삭제 후 Storage 정리가 필요합니다. 같은 ID로 재시도하세요.';
    case 'DELETE_COMPLETE_UNCERTAIN': return 'Storage는 정리됐지만 완료 receipt 확인을 재시도해야 합니다.';
    case 'DELETE_STORAGE_PROVENANCE_UNCERTAIN': return '삭제 receipt의 Storage 대상을 다시 확인해야 합니다. 복구 상태를 조회한 뒤 재시도하세요.';
    case 'DELETE_PREPARE_UNCERTAIN': return 'DB 반영 여부를 확인하지 못했습니다. 잠시 후 recovery 상태를 다시 확인하세요.';
    case 'DELETE_PREPARE_FAILED': return '삭제 전 참조 검증을 완료하지 못했습니다.';
    case 'DELETE_INTEGRITY_FAILED': return '삭제 무결성 검증을 통과하지 못했습니다.';
    default: return item.reason;
  }
}
