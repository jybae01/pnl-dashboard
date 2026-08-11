import { ChangeEvent, FormEvent, useCallback, useEffect, useState } from 'react';
import { ApiClientError, AdminModelDto } from './types';
import { bffClient } from './client';
import { CoreAnalysisView } from './CoreAnalysisView';

type UploadState = 'IDLE' | 'SELECTED' | 'VALIDATING' | 'UPLOADING' | 'SUCCESS' | 'VALIDATION_ERROR' | 'ERROR';
const MAX_BYTES = 50 * 1024 * 1024;

export function ModelManagementView() {
  const [models, setModels] = useState<AdminModelDto[]>([]);
  const [listState, setListState] = useState<'LOADING' | 'READY' | 'EMPTY' | 'ERROR'>('LOADING');
  const [uploadState, setUploadState] = useState<UploadState>('IDLE');
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [modelType, setModelType] = useState<'PLAN' | 'ACTUAL' | 'FORECAST'>('ACTUAL');
  const [modelYear, setModelYear] = useState(new Date().getFullYear());
  const [version, setVersion] = useState('V1');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [analysisRefreshKey, setAnalysisRefreshKey] = useState(0);

  const refresh = useCallback(async () => {
    setListState('LOADING');
    try {
      const rows = await bffClient.adminModels();
      setModels(rows);
      setListState(rows.length ? 'READY' : 'EMPTY');
    } catch (value) {
      setModels([]);
      setListState('ERROR');
      setMessage(safeMessage(value));
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  function beginNewLogicalUpload() {
    setIdempotencyKey(crypto.randomUUID());
    setMessage(null);
    setUploadState(file ? 'SELECTED' : 'IDLE');
  }

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] || null;
    setFile(next);
    setIdempotencyKey(next ? crypto.randomUUID() : '');
    setMessage(null);
    setUploadState(next ? 'SELECTED' : 'IDLE');
    if (next && !name) setName(next.name.replace(/\.xlsx$/i, ''));
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    setUploadState('VALIDATING');
    if (!file) {
      setUploadState('VALIDATION_ERROR'); setMessage('업로드할 .xlsx 파일을 선택하세요.'); return;
    }
    if (!/\.xlsx$/i.test(file.name)) {
      setUploadState('VALIDATION_ERROR'); setMessage('.xlsx 파일만 등록할 수 있습니다.'); return;
    }
    if (file.size > MAX_BYTES) {
      setUploadState('VALIDATION_ERROR'); setMessage('파일이 50MB 제한을 초과했습니다.'); return;
    }
    const key = idempotencyKey || crypto.randomUUID();
    if (!idempotencyKey) setIdempotencyKey(key);
    setUploadState('UPLOADING');
    try {
      const response = await bffClient.uploadModel({
        name, modelType, modelYear, version, idempotencyKey: key, file,
      });
      setUploadState('SUCCESS');
      setMessage(`${response.model.display_name} 등록 완료 · 현재 비공개`);
      setFile(null);
      await refresh();
    } catch (value) {
      const validation = value instanceof ApiClientError && value.code === 'VALIDATION_ERROR';
      setUploadState(validation ? 'VALIDATION_ERROR' : 'ERROR');
      setMessage(safeMessage(value));
    }
  }

  async function publish(model: AdminModelDto, isDefault: boolean) {
    setMessage(null);
    try {
      await bffClient.publishModel(model.model_id, isDefault);
      setMessage(`${model.display_name} 공개 완료`);
      await refresh();
      setAnalysisRefreshKey((value) => value + 1);
    } catch (value) {
      setMessage(safeMessage(value));
    }
  }

  return <div>
    <section className="content-card" aria-labelledby="model-upload-heading" style={{ marginBottom: 16 }}>
      <div className="section-header"><h1 id="model-upload-heading" className="section-title">손익 데이터 모델 등록</h1></div>
      <form onSubmit={upload} style={{ display: 'grid', gap: 12 }}>
        <div className="filter-group">
          <label className="filter-item"><span className="filter-label">모델명</span>
            <input aria-label="모델명" className="filter-select" value={name} onChange={(e) => { setName(e.target.value); beginNewLogicalUpload(); }} required />
          </label>
          <label className="filter-item"><span className="filter-label">유형</span>
            <select aria-label="모델 유형" className="filter-select" value={modelType} onChange={(e) => { setModelType(e.target.value as typeof modelType); beginNewLogicalUpload(); }}>
              <option value="PLAN">계획</option><option value="ACTUAL">실적</option><option value="FORECAST">추정</option>
            </select>
          </label>
          <label className="filter-item"><span className="filter-label">연도</span>
            <input aria-label="모델 연도" type="number" min="2000" max="2200" className="filter-select" value={modelYear} onChange={(e) => { setModelYear(Number(e.target.value)); beginNewLogicalUpload(); }} required />
          </label>
          <label className="filter-item"><span className="filter-label">버전</span>
            <input aria-label="모델 버전" className="filter-select" value={version} onChange={(e) => { setVersion(e.target.value); beginNewLogicalUpload(); }} required />
          </label>
        </div>
        <label className="upload-dropzone" style={{ padding: 22, cursor: 'pointer' }}>
          <strong>{file ? file.name : '.xlsx 파일 선택'}</strong>
          <span className="upload-subtitle">지원 형식: .xlsx · 최대 50MB</span>
          <input aria-label="워크북 파일" type="file" accept=".xlsx" onChange={selectFile} style={{ marginTop: 8 }} />
        </label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-primary" disabled={!file || uploadState === 'UPLOADING'}>모형 등록</button>
          <span role="status" data-testid="upload-state">{uploadState}</span>
        </div>
        {message && <div role={uploadState === 'ERROR' || uploadState === 'VALIDATION_ERROR' ? 'alert' : 'status'}>{message}</div>}
      </form>
    </section>

    <section className="content-card" aria-labelledby="management-list-heading" style={{ marginBottom: 16 }}>
      <div className="section-header"><h2 id="management-list-heading" className="section-title">모델 관리</h2></div>
      {listState === 'LOADING' && <p role="status">모델 목록 확인 중…</p>}
      {listState === 'EMPTY' && <p>등록된 모델이 없습니다.</p>}
      {listState === 'ERROR' && <p role="alert">모델 목록을 불러올 수 없습니다.</p>}
      {listState === 'READY' && <table className="data-table"><thead><tr><th>모델</th><th>유형/연도</th><th>SHA-256</th><th>상태</th><th>작업</th></tr></thead>
        <tbody>{models.map((model) => <tr key={model.model_id}>
          <td>{model.display_name}<div className="text-muted">{model.file_name}</div></td>
          <td>{model.model_type} / {model.model_year}</td>
          <td><code>{model.workbook_sha256 ? `${model.workbook_sha256.slice(0, 12)}…` : '미해결'}</code></td>
          <td>{model.is_published ? (model.is_default ? '공개 · 기본' : '공개') : '비공개'}</td>
          <td>{!model.is_published && <>
            <button className="btn btn-primary" onClick={() => void publish(model, false)}>공개</button>{' '}
            <button className="btn" onClick={() => void publish(model, true)}>공개 + 기본</button>
          </>}</td>
        </tr>)}</tbody></table>}
    </section>

    <CoreAnalysisView role="admin" modelRefreshKey={analysisRefreshKey} />
  </div>;
}

function safeMessage(value: unknown): string {
  return value instanceof ApiClientError ? value.message : '요청을 처리할 수 없습니다.';
}
