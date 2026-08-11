import React from 'react';
import { Calculator, Info, ShieldAlert, Sparkles, Database, FileSpreadsheet } from 'lucide-react';

export const ForecastGenerationView: React.FC = () => {
  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', padding: '24px 0' }}>
      {/* Hero Card */}
      <div className="content-card" style={{ padding: '32px 28px', textAlign: 'center', backgroundColor: '#f8fafc', border: '1px solid #cbd5e1' }}>
        <div style={{
          width: 56,
          height: 56,
          borderRadius: 28,
          backgroundColor: '#eff6ff',
          border: '1px solid #bfdbfe',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 16,
        }}>
          <Calculator size={28} color="#2563eb" />
        </div>

        <h2 style={{ fontSize: '18px', fontWeight: 800, color: '#0f172a', marginBottom: 8 }}>
          추정 산출 (Forecast Generation)
        </h2>

        <p style={{ fontSize: '13px', color: '#475569', maxWidth: '600px', margin: '0 auto 24px', lineHeight: 1.6 }}>
          월별 판매계획, 확정 수주잔고, 원가 변동 예측 파라미터를 기반으로 향후 손익 추정 모형을 산출하는 전용 워크플로우입니다.
        </p>

        {/* Protection / Status Alert Box */}
        <div style={{
          maxWidth: '680px',
          margin: '0 auto 20px',
          backgroundColor: '#ffffff',
          border: '1px solid #93c5fd',
          borderRadius: 'var(--radius-md)',
          padding: '16px 20px',
          textAlign: 'left',
          display: 'flex',
          gap: 12,
        }}>
          <Info size={18} color="#2563eb" style={{ flexShrink: 0, marginTop: 2 }} />
          <div style={{ fontSize: '12px', color: '#1e3a8a', lineHeight: 1.6 }}>
            <strong>[시스템 연계 안내]</strong> 본 화면의 실제 추정 계산엔진 및 산출 파이프라인은 기존 실제 프로젝트의 안정적인 모듈(Source of Truth)을 그대로 활용합니다.
            현재 프로토타입에서는 독립된 UI 자리(Placeholder)로 유지되며, 통합 단계에서 백엔드 어댑터와 직접 연결됩니다.
          </div>
        </div>

        {/* Planned Integration Features List */}
        <div style={{
          maxWidth: '680px',
          margin: '0 auto',
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 12,
          textAlign: 'left'
        }}>
          <div style={{ backgroundColor: '#ffffff', border: '1px solid var(--border-default)', padding: '12px 14px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '12px', color: '#0f172a', marginBottom: 4 }}>
              <Sparkles size={14} color="#2563eb" />
              1. 추정 파라미터 입력
            </div>
            <div style={{ fontSize: '11px', color: '#64748b', lineHeight: 1.4 }}>
              환율 전망치, 원재료 단가 변동률, 출하량 시나리오 설정
            </div>
          </div>

          <div style={{ backgroundColor: '#ffffff', border: '1px solid var(--border-default)', padding: '12px 14px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '12px', color: '#0f172a', marginBottom: 4 }}>
              <Calculator size={14} color="#0f766e" />
              2. 손익 추정 엔진 연산
            </div>
            <div style={{ fontSize: '11px', color: '#64748b', lineHeight: 1.4 }}>
              월별 매출원가 및 판관비 배부 로직 기반 Forward 손익 계산
            </div>
          </div>

          <div style={{ backgroundColor: '#ffffff', border: '1px solid var(--border-default)', padding: '12px 14px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700, fontSize: '12px', color: '#0f172a', marginBottom: 4 }}>
              <FileSpreadsheet size={14} color="#7c3aed" />
              3. 추정 모형 생성 & 등록
            </div>
            <div style={{ fontSize: '11px', color: '#64748b', lineHeight: 1.4 }}>
              산출된 추정치를 신규 모형 버전(Forecast V1.x)으로 게시
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
