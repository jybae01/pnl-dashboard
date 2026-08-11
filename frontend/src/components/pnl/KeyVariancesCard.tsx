import React from 'react';
import { KeyVarianceNote } from '../../types/pnl';
import { AlertCircle, ArrowUpRight, ArrowDownRight, Info } from 'lucide-react';

interface KeyVariancesCardProps {
  notes: KeyVarianceNote[];
}

export const KeyVariancesCard: React.FC<KeyVariancesCardProps> = ({ notes }) => {
  return (
    <div className="content-card">
      <div className="section-header" style={{ marginBottom: 12 }}>
        <div className="section-title-wrap">
          <span className="section-title" style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
            <Info size={15} color="#2563eb" />
            주요 경영 손익 변동 사항
          </span>
        </div>
        <span className="unit-tag">경영기획팀 종합 코멘트</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {notes.map((n) => (
          <div
            key={n.id}
            style={{
              padding: '10px 12px',
              backgroundColor: '#f8fafc',
              border: '1px solid var(--border-subtle)',
              borderLeft: `4px solid ${
                n.impactType === 'POSITIVE'
                  ? 'var(--color-favorable)'
                  : n.impactType === 'NEGATIVE'
                  ? 'var(--color-unfavorable)'
                  : 'var(--color-plan)'
              }`,
              borderRadius: 'var(--radius-sm)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '12.5px' }}>
                {n.impactType === 'POSITIVE' ? (
                  <ArrowUpRight size={14} color="var(--color-favorable)" />
                ) : (
                  <ArrowDownRight size={14} color="var(--color-unfavorable)" />
                )}
                {n.title}
              </div>
              <span className={n.impactType === 'POSITIVE' ? 'badge-favorable' : 'badge-unfavorable'}>
                {n.impactAmountText}
              </span>
            </div>
            <div style={{ fontSize: '11.5px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {n.description}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
