import React, { FormEvent, useEffect, useState } from 'react';
import { AlertCircle, Loader2 } from 'lucide-react';
import darkLogo from '../assets/nanoh2o-logo-dark.png';
import { ApiClientError, SessionDto } from './types';
import { bffClient } from './client';

export function LoginBrandLogo() {
  return <img className="login-logo" src={darkLogo} alt="NANOH2O" />;
}

export function LoginView({ onAuthenticated }: { onAuthenticated: (session: SessionDto) => void }) {
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lockedUntil, setLockedUntil] = useState<number | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState(0);

  useEffect(() => {
    if (lockedUntil === null) return;
    const update = () => {
      const next = Math.max(0, Math.ceil((lockedUntil - Date.now()) / 1000));
      setRemainingSeconds(next);
      if (next === 0) setLockedUntil(null);
    };
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [lockedUntil]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const session = await bffClient.login(code);
      setCode('');
      onAuthenticated(session);
    } catch (value) {
      if (value instanceof ApiClientError && value.status === 429 && value.retryAfterSeconds) {
        setLockedUntil(Date.now() + value.retryAfterSeconds * 1000);
        setRemainingSeconds(value.retryAfterSeconds);
        setError('로그인 시도 횟수를 초과했습니다. 잠시 후 다시 시도해 주세요.');
      } else {
        setError(value instanceof ApiClientError ? value.message : '로그인할 수 없습니다.');
      }
    } finally {
      setLoading(false);
    }
  }

  const locked = remainingSeconds > 0;
  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <LoginBrandLogo />
        <div className="login-heading">
          <span className="login-heading-mark" aria-hidden="true" />
          <div>
            <h1 id="login-title">손익 데이터 모니터링</h1>
            <p>접속 코드를 입력하여 대시보드를 확인하세요.</p>
          </div>
        </div>
        <form className="login-form" onSubmit={submit}>
          <label className="login-label" htmlFor="access-code">Access Code</label>
          <input
            id="access-code"
            type="password"
            autoComplete="current-password"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            placeholder="접속 코드를 입력하세요"
            className="login-input"
            disabled={loading || locked}
          />
          {error && (
            <div className="login-error" role="alert">
              <AlertCircle size={15} aria-hidden="true" style={{ flexShrink: 0, marginTop: '2px' }} />
              <span>{error}</span>
            </div>
          )}
          {locked && <p className="login-lockout" role="status">남은 잠금시간: {remainingSeconds}초</p>}
          <button className="login-submit" disabled={loading || locked || !code}>
            {loading ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                <Loader2 size={16} className="login-spinner" aria-hidden="true" />
                <span>확인 중…</span>
              </span>
            ) : (
              '접속'
            )}
          </button>
        </form>
      </section>
    </main>
  );
}
