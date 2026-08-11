import React, { FormEvent, useState } from 'react';
import { ApiClientError, SessionDto } from './types';
import { bffClient } from './client';

export function LoginView({ onAuthenticated }: { onAuthenticated: (session: SessionDto) => void }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const session = await bffClient.login(code);
      setCode('');
      onAuthenticated(session);
    } catch (value) {
      setError(value instanceof ApiClientError ? value.message : '로그인할 수 없습니다.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-content" style={{ maxWidth: 440, margin: '80px auto' }}>
      <form className="card" onSubmit={submit} style={{ padding: 28 }}>
        <h1 style={{ fontSize: 20, marginBottom: 8 }}>손익분석 로그인</h1>
        <p style={{ color: '#64748b', marginBottom: 20 }}>사내 Viewer 또는 Admin 접근 코드를 입력하세요.</p>
        <label className="filter-label" htmlFor="access-code">접근 코드</label>
        <input id="access-code" type="password" autoComplete="current-password" value={code}
          onChange={(event) => setCode(event.target.value)} className="filter-select" style={{ width: '100%' }} />
        {error && <div role="alert" style={{ color: '#b91c1c', marginTop: 10 }}>{error}</div>}
        <button className="btn btn-primary" disabled={loading || !code} style={{ marginTop: 18, width: '100%' }}>
          {loading ? '확인 중…' : '로그인'}
        </button>
      </form>
    </main>
  );
}
