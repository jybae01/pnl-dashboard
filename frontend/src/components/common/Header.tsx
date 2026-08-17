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
        <div className="system-logo-group" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <NanoH2oLogo height={16} alt="NANOH2O" />

          <div style={{ display: 'flex', alignItems: 'center' }}>
            <span className="system-title" style={{ fontSize: '14.5px', fontWeight: 700, letterSpacing: '-0.3px' }}>
              손익분석 업무 시스템
            </span>
            <span className="system-subtitle" style={{ fontSize: '11.5px', color: '#94a3b8' }}>
              Management Accounting & P&L Planning
            </span>
          </div>
        </div>
      </div>

      {session && (
        <div className="header-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="env-tag" aria-label="현재 권한">
            {session.role === 'admin' ? (
              <>
                <Shield size={13} aria-hidden="true" style={{ color: '#38bdf8' }} />
                <span>ADMIN · 업로드/공개/분석</span>
              </>
            ) : (
              <>
                <User size={13} aria-hidden="true" style={{ color: '#94a3b8' }} />
                <span>VIEWER · 공개 결과 조회</span>
              </>
            )}
          </div>
          {onLogout && (
            <button
              type="button"
              className="btn-header-logout"
              onClick={onLogout}
              aria-label="로그아웃"
            >
              <LogOut size={13} aria-hidden="true" />
              <span>로그아웃</span>
            </button>
          )}
        </div>
      )}
    </header>
  );
};
