import React from 'react';
import { Database, AlertCircle } from 'lucide-react';

interface EmptyStateProps {
  title?: string;
  description?: string;
  actionText?: string;
  onAction?: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = '조회된 데이터가 없습니다',
  description = '선택한 조건에 일치하는 손익 데이터 또는 모형이 존재하지 않습니다.',
  actionText,
  onAction
}) => {
  return (
    <div className="empty-state-box">
      <div
        style={{
          width: '48px',
          height: '48px',
          borderRadius: '50%',
          backgroundColor: '#f1f5f9',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '14px',
        }}
      >
        <Database size={24} color="#64748b" />
      </div>
      <div className="empty-state-title" style={{ fontSize: '15px', fontWeight: 800, color: '#0f172a', marginBottom: '6px' }}>
        {title}
      </div>
      <div className="empty-state-desc" style={{ fontSize: '13px', color: '#64748b', maxWidth: 440, lineHeight: 1.5, margin: '0 auto 16px auto' }}>
        {description}
      </div>
      {actionText && onAction && (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onAction}
          style={{
            padding: '6px 16px',
            fontSize: '12.5px',
            fontWeight: 700,
          }}
        >
          {actionText}
        </button>
      )}
    </div>
  );
};
