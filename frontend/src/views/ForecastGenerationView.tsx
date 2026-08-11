import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Calculator, CheckCircle2, Database, ShieldCheck } from 'lucide-react';
import { bffClient } from '../integration/client';
import { AnalysisModelDto, ApiClientError, ForecastGenerateResponseDto, ForecastMonthInputDto } from '../integration/types';

type State = 'IDLE' | 'EDITING' | 'SUBMITTING' | 'VALIDATION_ERROR' | 'SUCCESS' | 'ERROR';

const blankMonth = (month: number): ForecastMonthInputDto => ({
  month,
  sales: ['SW400', 'SW440', 'BW400', 'BW440', 'LC', 'FS_SW', 'FS_BW', 'FS_TW', 'UF_MBR', 'IX', 'OTHER']
    .map((product_code) => ({ product_code, quantity: 0, amount: 0 })),
  production: ['SW400', 'SW440', 'BW400', 'BW440', 'LC', 'FS_SW', 'FS_BW', 'FS_TW']
    .map((product_code) => ({ product_code, quantity: 0 })),
  mcm: ['SW400', 'SW440', 'BW400', 'BW440'].map((product_code) => ({ product_code, quantity: 0 })),
  manufacturing_adjustments: [], sga_adjustments: [],
});

export const ForecastGenerationView: React.FC = () => {
  const [models, setModels] = useState<AnalysisModelDto[]>([]);
  const [baseModelId, setBaseModelId] = useState('');
  const [startMonth, setStartMonth] = useState(7);
  const [endMonth, setEndMonth] = useState(7);
  const [name, setName] = useState('Forecast Model');
  const [version, setVersion] = useState('V1');
  const [inputs, setInputs] = useState<Record<number, string>>({ 7: JSON.stringify(blankMonth(7), null, 2) });
  const [state, setState] = useState<State>('IDLE');
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<ForecastGenerateResponseDto | null>(null);
  const idempotencyKey = useRef(crypto.randomUUID());
  const requestSequence = useRef(0);

  useEffect(() => {
    let active = true;
    bffClient.models().then((values) => {
      if (!active) return;
      setModels(values); setBaseModelId(values[0]?.model_id || '');
    }).catch(() => { if (active) { setState('ERROR'); setMessage('기준 Model 목록을 불러올 수 없습니다.'); } });
    return () => { active = false; requestSequence.current += 1; };
  }, []);

  const months = useMemo(() => Array.from({ length: endMonth - startMonth + 1 }, (_, i) => startMonth + i), [startMonth, endMonth]);
  useEffect(() => {
    setInputs((old) => Object.fromEntries(months.map((month) => [month, old[month] || JSON.stringify(blankMonth(month), null, 2)])));
    requestSequence.current += 1; setState('EDITING'); setResult(null); idempotencyKey.current = crypto.randomUUID();
  }, [startMonth, endMonth]);

  const submit = async () => {
    setMessage(''); setResult(null);
    let parsed: ForecastMonthInputDto[];
    try {
      parsed = months.map((month) => {
        const value = JSON.parse(inputs[month]);
        if (value.month !== month) throw new Error('month');
        return value;
      });
    } catch {
      setState('VALIDATION_ERROR'); setMessage('월별 입력 JSON과 선택 기간을 확인하세요.'); return;
    }
    const base = models.find((item) => item.model_id === baseModelId);
    if (!base) { setState('VALIDATION_ERROR'); setMessage('공개된 기준 Model을 선택하세요.'); return; }
    setState('SUBMITTING');
    const sequence = ++requestSequence.current;
    try {
      const saved = await bffClient.generateForecast({
        base_model_id: baseModelId, name, model_year: base.model_year, version,
        start_month: startMonth, end_month: endMonth, months: parsed,
        idempotency_key: idempotencyKey.current,
      });
      if (sequence !== requestSequence.current) return;
      setResult(saved); setState('SUCCESS');
    } catch (error) {
      if (sequence !== requestSequence.current) return;
      if (error instanceof ApiClientError && ['VALIDATION_ERROR', 'IDEMPOTENCY_CONFLICT'].includes(error.code)) {
        setState('VALIDATION_ERROR'); setMessage(error.message);
      } else { setState('ERROR'); setMessage('Forecast 생성에 실패했습니다. 잠시 후 다시 시도하세요.'); }
    }
  };

  return <div style={{ maxWidth: 1080, margin: '0 auto', padding: '24px 0' }}>
    <div className="content-card" style={{ padding: 28 }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 20 }}>
        <div style={{ width: 48, height: 48, borderRadius: 24, background: '#fff7ed', display: 'grid', placeItems: 'center' }}><Calculator color="#ea580c" /></div>
        <div><h2 style={{ margin: 0 }}>추정 산출</h2><p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 13 }}>기존 Python ForecastEngine으로 비공개 Forecast Model을 생성합니다.</p></div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12 }}>
        <label>기준 Model<select disabled={state === 'SUBMITTING'} value={baseModelId} onChange={(e) => { requestSequence.current += 1; setBaseModelId(e.target.value); idempotencyKey.current = crypto.randomUUID(); }} style={{ width: '100%' }}>
          {models.map((m) => <option key={m.model_id} value={m.model_id}>{m.display_name} ({m.model_year})</option>)}
        </select></label>
        <label>시작 월<input disabled={state === 'SUBMITTING'} type="number" min={1} max={12} value={startMonth} onChange={(e) => setStartMonth(Math.min(Number(e.target.value), endMonth))} /></label>
        <label>종료 월<input disabled={state === 'SUBMITTING'} type="number" min={startMonth} max={12} value={endMonth} onChange={(e) => setEndMonth(Math.max(Number(e.target.value), startMonth))} /></label>
        <label>Model 표시명<input disabled={state === 'SUBMITTING'} value={name} onChange={(e) => { requestSequence.current += 1; setName(e.target.value); idempotencyKey.current = crypto.randomUUID(); }} /></label>
        <label>버전<input disabled={state === 'SUBMITTING'} value={version} onChange={(e) => { requestSequence.current += 1; setVersion(e.target.value); idempotencyKey.current = crypto.randomUUID(); }} /></label>
      </div>
      <div style={{ marginTop: 20 }}>
        <h3 style={{ fontSize: 14 }}>월별 Forecast 입력</h3>
        <p style={{ color: '#64748b', fontSize: 12 }}>제품코드는 서버 mapping으로 검증됩니다. LC는 4인치/PCS, FS는 LENGTH(m)이며 React는 금액을 계산하지 않습니다.</p>
        {months.map((month) => <label key={month} style={{ display: 'block', marginBottom: 14 }}>{month}월
          <textarea disabled={state === 'SUBMITTING'} aria-label={`${month}월 Forecast 입력`} value={inputs[month] || ''} onChange={(e) => { requestSequence.current += 1; setInputs({ ...inputs, [month]: e.target.value }); setState('EDITING'); idempotencyKey.current = crypto.randomUUID(); }} rows={9} style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }} />
        </label>)}
      </div>
      <button type="button" className="primary-button" disabled={state === 'SUBMITTING' || !baseModelId} onClick={submit}>
        {state === 'SUBMITTING' ? 'Forecast 생성 중…' : 'Forecast Model 생성'}
      </button>
      {message && <p role="alert" style={{ color: state === 'VALIDATION_ERROR' ? '#b45309' : '#b91c1c' }}>{message}</p>}
      {result && state === 'SUCCESS' && <div style={{ marginTop: 18, padding: 16, border: '1px solid #86efac', borderRadius: 10, background: '#f0fdf4' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontWeight: 700 }}><CheckCircle2 size={18} />Forecast 생성 완료</div>
        <p>{result.display_name} · {result.model_year}년 {result.start_month}~{result.end_month}월</p>
        <p><ShieldCheck size={14} /> 현재 상태: {result.is_published ? '공개' : '비공개'} / {result.is_default ? 'default' : 'non-default'}</p>
        <p style={{ fontSize: 12, color: '#64748b' }}><Database size={14} /> Model Management에서 공개하면 Analysis Base/Comparison 목록에 나타납니다.</p>
      </div>}
    </div>
  </div>;
};
