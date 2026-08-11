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
  description = '선택한 조건에 일치하는 손익 데이터 또는 모델이 존재하지 않습니다.',
  actionText,
  onAction
}) => {
  return (
    <div className="empty-state-box">
      <Database size={36} color="#94a3b8" style={{ marginBottom: 12 }} />
      <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginBottom: 4 }}>
        {title}
      </div>
      <div style={{ fontSize: '12px', color: '#64748b', maxWidth: 380, margin: '0 auto 16px auto' }}>
        {description}
      </div>
      {actionText && onAction && (
        <button className="btn btn-secondary btn-sm" onClick={onAction}>
          {actionText}
        </button>
      )}
    </div>
  );
};
