import React from 'react';

interface LoadingSpinnerProps {
  message?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = '손익 분석 데이터를 불러오는 중입니다...'
}) => {
  return (
    <div className="loading-state-box">
      <div className="spinner" />
      <div>{message}</div>
    </div>
  );
};
