import React from 'react';
import { ModelType, PublishedStatus, CalculationJobStatus } from '../../types/model';
import { CheckCircle2, Clock, AlertTriangle, XCircle, FileText } from 'lucide-react';

interface ModelTypeBadgeProps {
  type: ModelType;
}

export const ModelTypeBadge: React.FC<ModelTypeBadgeProps> = ({ type }) => {
  switch (type) {
    case 'PLAN':
      return <span className="model-pill model-pill-plan">PLAN (계획)</span>;
    case 'ACTUAL':
      return <span className="model-pill model-pill-actual">ACTUAL (실적)</span>;
    case 'FORECAST':
      return <span className="model-pill model-pill-forecast">FORECAST (추정)</span>;
    default:
      return <span className="model-pill">{type}</span>;
  }
};

interface PublishedBadgeProps {
  status: PublishedStatus;
}

export const PublishedBadge: React.FC<PublishedBadgeProps> = ({ status }) => {
  switch (status) {
    case 'PUBLISHED':
      return <span className="status-pill status-published">● 게시완료</span>;
    case 'DRAFT':
      return <span className="status-pill status-draft">○ 작성중</span>;
    case 'ARCHIVED':
      return <span className="status-pill status-draft">✕ 보관됨</span>;
    default:
      return <span className="status-pill">{status}</span>;
  }
};

interface CalcStatusBadgeProps {
  status: 'COMPLETED' | 'PROCESSING' | 'PENDING' | 'FAILED' | 'NOT_STARTED';
}

export const CalcStatusBadge: React.FC<CalcStatusBadgeProps> = ({ status }) => {
  switch (status) {
    case 'COMPLETED':
      return (
        <span className="status-pill status-completed">
          <CheckCircle2 size={11} /> 계산완료
        </span>
      );
    case 'PROCESSING':
      return (
        <span className="status-pill status-processing">
          <Clock size={11} /> 처리중...
        </span>
      );
    case 'PENDING':
      return (
        <span className="status-pill status-pending">
          <Clock size={11} /> 대기중
        </span>
      );
    case 'FAILED':
      return (
        <span className="status-pill status-failed">
          <XCircle size={11} /> 계산실패
        </span>
      );
    case 'NOT_STARTED':
    default:
      return <span className="status-pill status-draft">- 미수행</span>;
  }
};
