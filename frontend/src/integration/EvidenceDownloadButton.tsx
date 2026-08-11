import { useState } from 'react';
import { bffClient } from './client';
import { ApiClientError, Role } from './types';

type DownloadState = 'IDLE' | 'DOWNLOADING' | 'FAILED';

export function EvidenceDownloadButton({ resultId, role, onUnavailable }: {
  resultId: string;
  role: Role;
  onUnavailable?: () => void;
}) {
  const [state, setState] = useState<DownloadState>('IDLE');
  const [message, setMessage] = useState<string | null>(null);

  async function download() {
    if (state === 'DOWNLOADING') return;
    setState('DOWNLOADING'); setMessage(null);
    try {
      await bffClient.downloadEvidence(resultId, role);
      setState('IDLE');
    } catch (value) {
      if (value instanceof ApiClientError && value.code === 'RESULT_NOT_AVAILABLE') onUnavailable?.();
      setState('FAILED');
      setMessage(value instanceof ApiClientError ? value.message : '분석 근거 엑셀을 내려받을 수 없습니다.');
    }
  }

  return <span>
    <button type="button" className="btn btn-secondary" disabled={state === 'DOWNLOADING'} onClick={() => void download()}>
      {state === 'DOWNLOADING' ? '내려받는 중…' : '분석 근거 엑셀 내려받기'}
    </button>
    {state === 'FAILED' && message && <span role="alert" style={{ color: '#b91c1c', marginLeft: 8 }}>{message}</span>}
  </span>;
}
