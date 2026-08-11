import React from 'react';
import logoImg from '../../assets/nanoh2o-logo.png';

interface HeaderProps {
  currentDate?: string;
}

export const Header: React.FC<HeaderProps> = () => {
  return (
    <header className="app-header">
      <div className="header-left">
        <div className="system-logo-group" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {/* Exact original NANOH2O logo image directly displayed without any distortion */}
          <div
            style={{
              backgroundColor: '#ffffff',
              padding: '3px 8px',
              borderRadius: '4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            }}
          >
            <img
              src={logoImg}
              alt="NANOH2O"
              style={{
                height: '18px',
                width: 'auto',
                display: 'block',
                objectFit: 'contain',
              }}
            />
          </div>

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
    </header>
  );
};
