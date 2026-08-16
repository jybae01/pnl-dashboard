import React, { useState, useRef } from 'react';
import { UploadCloud, FileSpreadsheet, Download, CheckCircle, AlertCircle } from 'lucide-react';

export interface UploadModelPayload {
  modelType: 'PLAN' | 'ACTUAL' | 'FORECAST';
  baseYear: number;
  actualLatestMonth?: string;     // e.g. '06'
  forecastStartMonth?: string;    // e.g. '07'
  forecastEndMonth?: string;      // e.g. '12'
  fileName: string;
}

interface ModelUploadAreaProps {
  onUploadSuccess?: (payload: UploadModelPayload) => void;
}

export const ModelUploadArea: React.FC<ModelUploadAreaProps> = ({ onUploadSuccess }) => {
  const [modelType, setModelType] = useState<'PLAN' | 'ACTUAL' | 'FORECAST'>('ACTUAL');
  const [baseYear, setBaseYear] = useState<number>(2026);
  const [actualLatestMonth, setActualLatestMonth] = useState<string>('06');

  // Forecast Range: default 7월 ~ 12월
  const [forecastStartMonth, setForecastStartMonth] = useState<string>('07');
  const [forecastEndMonth, setForecastEndMonth] = useState<string>('12');

  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadSuccessNotice, setUploadSuccessNotice] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Validation: Forecast start month > end month
  const isForecastRangeInvalid = modelType === 'FORECAST' && Number(forecastStartMonth) > Number(forecastEndMonth);
  const rangeError = isForecastRangeInvalid ? '추정 시작월이 종료월보다 이후일 수 없습니다.' : null;

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    setUploadSuccessNotice(null);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleSubmitUpload = () => {
    if (isForecastRangeInvalid) return;

    setIsUploading(true);
    setUploadSuccessNotice(null);

    let defaultName = `${baseYear}_경영계획.xlsx`;
    if (modelType === 'ACTUAL') {
      defaultName = `${baseYear}_${actualLatestMonth}_실적.xlsx`;
    } else if (modelType === 'FORECAST') {
      defaultName = `${baseYear}_${forecastStartMonth}-${forecastEndMonth}_추정.xlsx`;
    }

    const fileName = selectedFile ? selectedFile.name : defaultName;

    setTimeout(() => {
      setIsUploading(false);
      const payload: UploadModelPayload = {
        modelType,
        baseYear,
        actualLatestMonth: modelType === 'ACTUAL' ? actualLatestMonth : undefined,
        forecastStartMonth: modelType === 'FORECAST' ? forecastStartMonth : undefined,
        forecastEndMonth: modelType === 'FORECAST' ? forecastEndMonth : undefined,
        fileName,
      };

      const typeLabel = modelType === 'PLAN' ? '계획' : modelType === 'ACTUAL' ? '실적' : '추정';
      setUploadSuccessNotice(`[${typeLabel}] ${fileName} 모형이 성공적으로 등록되었습니다.`);
      setSelectedFile(null);
      if (onUploadSuccess) onUploadSuccess(payload);
    }, 900);
  };

  return (
    <div className="content-card" style={{ marginBottom: 16 }}>
      {/* Header */}
      <div className="section-header" style={{ marginBottom: 12 }}>
        <div className="section-title-wrap">
          <span className="section-title" style={{ fontSize: '14.5px', fontWeight: 800, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 8 }}>
            <UploadCloud size={16} color="#2563eb" />
            손익 데이터 모형 등록
          </span>
        </div>
        <div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => alert('표준 엑셀 템플릿(손익계산서/원가배부/환율테이블) 다운로드가 시뮬레이션되었습니다.')}
          >
            <Download size={12} />
            표준 템플릿 다운로드 (.xlsx)
          </button>
        </div>
      </div>

      {/* Model Type & Period Selectors */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        marginBottom: rangeError ? 6 : 12,
        padding: '10px 14px',
        backgroundColor: '#f8fafc',
        borderRadius: 'var(--radius-sm)',
        border: '1px solid var(--border-subtle)',
        flexWrap: 'wrap'
      }}>
        {/* 1. Model Type: 3 Segments (계획 / 실적 / 추정) */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: '11.5px', fontWeight: 700, color: 'var(--text-secondary)' }}>모형 구분:</span>
          <div className="segmented-control">
            <button
              type="button"
              className={`segmented-btn ${modelType === 'PLAN' ? 'active' : ''}`}
              onClick={() => setModelType('PLAN')}
              disabled={isUploading}
              style={{ minWidth: '42px' }}
            >
              계획
            </button>
            <button
              type="button"
              className={`segmented-btn ${modelType === 'ACTUAL' ? 'active' : ''}`}
              onClick={() => setModelType('ACTUAL')}
              disabled={isUploading}
              style={{ minWidth: '42px' }}
            >
              실적
            </button>
            <button
              type="button"
              className={`segmented-btn ${modelType === 'FORECAST' ? 'active' : ''}`}
              onClick={() => setModelType('FORECAST')}
              disabled={isUploading}
              style={{ minWidth: '42px' }}
            >
              추정
            </button>
          </div>
        </div>

        {/* 2. Base Year */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: '11.5px', fontWeight: 700, color: 'var(--text-secondary)' }}>기준년도:</span>
          <select
            className="filter-select"
            value={baseYear}
            onChange={(e) => setBaseYear(Number(e.target.value))}
            disabled={isUploading}
            style={{ minWidth: '90px', fontSize: '11.5px', padding: '3px 8px' }}
          >
            <option value={2026}>2026년</option>
            <option value={2025}>2025년</option>
          </select>
        </div>

        {/* 3. Actual: 최신 실적월 */}
        {modelType === 'ACTUAL' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: '11.5px', fontWeight: 700, color: 'var(--text-secondary)' }}>최신 실적월:</span>
            <select
              className="filter-select"
              value={actualLatestMonth}
              onChange={(e) => setActualLatestMonth(e.target.value)}
              disabled={isUploading}
              style={{ minWidth: '85px', fontSize: '11.5px', padding: '3px 8px' }}
            >
              {Array.from({ length: 12 }, (_, i) => {
                const m = String(i + 1).padStart(2, '0');
                return <option key={m} value={m}>{i + 1}월</option>;
              })}
            </select>
            <span style={{ fontSize: '11px', color: '#64748b' }}>
              (1월 ~ {parseInt(actualLatestMonth, 10)}월 실적 반영)
            </span>
          </div>
        )}

        {/* 4. Forecast: 추정기간 (시작월 ~ 종료월 Dropdowns without inner text labels) */}
        {modelType === 'FORECAST' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: '11.5px', fontWeight: 700, color: 'var(--text-secondary)' }}>추정기간:</span>
            <select
              className="filter-select"
              value={forecastStartMonth}
              onChange={(e) => setForecastStartMonth(e.target.value)}
              disabled={isUploading}
              style={{
                minWidth: '80px',
                fontSize: '11.5px',
                padding: '3px 6px',
                borderColor: isForecastRangeInvalid ? '#ef4444' : undefined,
              }}
            >
              {Array.from({ length: 12 }, (_, i) => {
                const m = String(i + 1).padStart(2, '0');
                return <option key={m} value={m}>{i + 1}월</option>;
              })}
            </select>

            <span style={{ color: '#94a3b8', fontWeight: 600 }}>~</span>

            <select
              className="filter-select"
              value={forecastEndMonth}
              onChange={(e) => setForecastEndMonth(e.target.value)}
              disabled={isUploading}
              style={{
                minWidth: '80px',
                fontSize: '11.5px',
                padding: '3px 6px',
                borderColor: isForecastRangeInvalid ? '#ef4444' : undefined,
              }}
            >
              {Array.from({ length: 12 }, (_, i) => {
                const m = String(i + 1).padStart(2, '0');
                return <option key={m} value={m}>{i + 1}월</option>;
              })}
            </select>
          </div>
        )}
      </div>

      {/* Validation Error Message */}
      {rangeError && (
        <div style={{
          marginBottom: 10,
          padding: '6px 12px',
          backgroundColor: '#fef2f2',
          border: '1px solid #fca5a5',
          borderRadius: 'var(--radius-sm)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: '11.5px',
          color: '#b91c1c',
          fontWeight: 600,
        }}>
          <AlertCircle size={14} color="#dc2626" />
          <span>{rangeError}</span>
        </div>
      )}

      {/* Dropzone Area */}
      <div
        className={`upload-dropzone ${isDragging ? 'drag-over' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        style={{
          border: isDragging ? '2px dashed #2563eb' : '1px dashed #cbd5e1',
          backgroundColor: isDragging ? '#eff6ff' : '#ffffff',
          cursor: isUploading ? 'not-allowed' : 'pointer',
          padding: '20px 16px',
        }}
      >
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          accept=".xlsx,.xls,.csv"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFileSelect(e.target.files[0]);
            }
          }}
        />

        <FileSpreadsheet size={28} className="upload-icon" color="#2563eb" />

        <div className="upload-title" style={{ fontSize: '13px', fontWeight: 700, marginTop: 4 }}>
          {selectedFile ? (
            <span style={{ color: '#1e40af' }}>선택된 파일: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)</span>
          ) : (
            '파일을 선택하거나 이 영역으로 끌어 놓으세요.'
          )}
        </div>

        <div className="upload-subtitle" style={{ fontSize: '11px', color: '#64748b', marginTop: 2 }}>
          지원 형식: .xlsx, .csv (최대 50MB) ·{' '}
          {modelType === 'PLAN'
            ? `${baseYear}년 경영계획 데이터`
            : modelType === 'ACTUAL'
            ? `${baseYear}년 1~${parseInt(actualLatestMonth, 10)}월 누계 실적 데이터`
            : `${baseYear}년 ${parseInt(forecastStartMonth, 10)}~${parseInt(forecastEndMonth, 10)}월 추정 데이터`}
        </div>

        {isUploading && (
          <div style={{ marginTop: 10, display: 'flex', justifyContent: 'center' }}>
            <div className="spinner" style={{ width: 18, height: 18 }} />
          </div>
        )}
      </div>

      {/* Action Row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
        <div>
          {uploadSuccessNotice && (
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              backgroundColor: '#ecfdf5',
              color: '#047857',
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11.5px',
              fontWeight: 600
            }}>
              <CheckCircle size={14} />
              {uploadSuccessNotice}
            </div>
          )}
        </div>

        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSubmitUpload}
          disabled={isUploading || isForecastRangeInvalid}
          style={{
            padding: '6px 16px',
            fontSize: '12px',
            fontWeight: 700,
            opacity: isUploading || isForecastRangeInvalid ? 0.5 : 1,
            cursor: isUploading || isForecastRangeInvalid ? 'not-allowed' : 'pointer',
          }}
        >
          {isUploading ? '모형 등록 처리 중...' : '모형 등록'}
        </button>
      </div>
    </div>
  );
};
