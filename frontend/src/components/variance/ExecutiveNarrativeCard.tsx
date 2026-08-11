import React, { useState } from 'react';
import { Sparkles, Copy, Check, TrendingUp, TrendingDown } from 'lucide-react';

interface ExecutiveNarrativeCardProps {
  summary: string;
  positiveFactors: string[];
  negativeFactors: string[];
}

export const ExecutiveNarrativeCard: React.FC<ExecutiveNarrativeCardProps> = ({
  summary,
  positiveFactors,
  negativeFactors,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="narrative-card">
      <div className="narrative-header">
        <div className="narrative-title">
          <Sparkles size={16} color="#2563eb" />
          경영진 분석 요약 (Executive Variance Narrative)
          <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>
            · 자동 생성 분석 브리핑
          </span>
        </div>

        <button className="btn btn-secondary btn-sm" onClick={handleCopy} title="요약문 복사">
          {copied ? (
            <>
              <Check size={12} color="var(--color-favorable)" /> 복사됨
            </>
          ) : (
            <>
              <Copy size={12} /> 보고서용 복사
            </>
          )}
        </button>
      </div>

      <div className="narrative-text">
        {summary}
      </div>

      <div className="factor-tags-grid">
        <div>
          <div className="factor-col-title" style={{ color: 'var(--color-favorable)' }}>
            ▲ 주요 긍정 요인 (Key Positive Drivers)
          </div>
          {positiveFactors.map((f, i) => (
            <div key={i} className="factor-item" style={{ color: 'var(--color-favorable)' }}>
              <TrendingUp size={13} style={{ flexShrink: 0 }} />
              <span>{f}</span>
            </div>
          ))}
        </div>

        <div>
          <div className="factor-col-title" style={{ color: 'var(--color-unfavorable)' }}>
            ▼ 주요 부정/감소 요인 (Key Headwinds)
          </div>
          {negativeFactors.map((f, i) => (
            <div key={i} className="factor-item" style={{ color: 'var(--color-unfavorable)' }}>
              <TrendingDown size={13} style={{ flexShrink: 0 }} />
              <span>{f}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
