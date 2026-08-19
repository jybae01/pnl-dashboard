import React from 'react';
import { LogOut, Shield, User } from 'lucide-react';
import { NanoH2oLogo } from './NanoH2oLogo';
import { SessionDto } from '../../integration/types';

interface HeaderProps {
  currentDate?: string;
  session?: SessionDto | null;
  onLogout?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ session, onLogout }) => {
  return (
    <header className="app-header">
      <div className="header-left">
        <div className="system-logo-group">
          <NanoH2oLogo height={18} alt="NANOH2O" className="system-logo-mark" />

          <div className="system-title-group">
            <span className="system-title">
              손익분석 업무 시스템
            </span>
            <span className="system-subtitle">
              Management Accounting & P&L Planning
            </span>
          </div>
        </div>
      </div>

      {session && (
        <div className="header-right">
          <div className="env-tag" aria-label={`현재 권한: ${session.role === 'admin' ? 'ADMIN' : 'VIEWER'}`}>
            {session.role === 'admin' ? (
              <>
                <Shield size={13} aria-hidden="true" style={{ color: '#38bdf8' }} />
                <span className="env-tag__full" aria-hidden="true">ADMIN · 업로드/공개/분석</span>
                <span className="env-tag__compact" aria-hidden="true">ADMIN</span>
              </>
            ) : (
              <>
                <User size={13} aria-hidden="true" style={{ color: '#94a3b8' }} />
                <span className="env-tag__full" aria-hidden="true">VIEWER · 공개 결과 조회</span>
                <span className="env-tag__compact" aria-hidden="true">VIEWER</span>
              </>
            )}
          </div>
          {onLogout && (
            <button
              type="button"
              className="btn-header-logout"
              onClick={onLogout}
              aria-label="로그아웃"
              title="로그아웃"
            >
              <LogOut size={13} aria-hidden="true" />
              <span className="btn-header-logout__label">로그아웃</span>
            </button>
          )}
        </div>
      )}
    </header>
  );
};
