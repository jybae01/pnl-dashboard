import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AnalysisPresentationPanel } from './AnalysisPresentationPanel';
import { CoreAnalysisView } from './CoreAnalysisView';
import { presentationFixture, TEST_RESULT } from './presentationTestFixture';
import { CANONICAL_EFFECT_ORDER, mapAnalysisPresentation } from './analysisPresentation';

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe('analysis presentation vertical slice', () => {
  it('renders canonical UI labels, residual, LC and separate activity units', () => {
    const value = presentationFixture();
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    expect(screen.getByText('영업이익 증감')).toBeInTheDocument();
    expect(screen.getByText('4인치 LC')).toBeInTheDocument();
    expect(screen.queryByText('미설명 잔여차이')).not.toBeInTheDocument();
    for (const label of ['판매수량', '제품 Mix', '판가', '매출환율', '원재료', '제조', '변동 판매관리비', '고정 판매관리비', '관세', '기타 요인']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.queryByText('판매단가')).not.toBeInTheDocument();
    expect(screen.queryByText('제조경비 손익실현')).not.toBeInTheDocument();
    expect(screen.queryByText('고정비')).not.toBeInTheDocument();
    expect(screen.queryByText('UNEXPLAINED')).not.toBeInTheDocument();
    for (const category of ['내부', '외부', '비용']) {
      expect(screen.getAllByText(category).length).toBeGreaterThan(0);
    }
    expect(screen.getByText('Effect 총액 (서버)')).toBeInTheDocument();
    expect(screen.getByText('persisted detail unavailable')).toBeInTheDocument();
    expect(screen.getAllByText('PCS').length).toBeGreaterThan(0);
    expect(screen.getAllByText('m').length).toBeGreaterThan(0);
    expect(screen.queryByText(/MCM.*Effect/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '분석 근거 엑셀 내려받기' })).toHaveLength(1);
    expect(screen.getAllByText('+20 KRW').length).toBeGreaterThan(0);
  });

  it('maps canonical order and labels without deriving totals', () => {
    const value = presentationFixture();
    value.effects = [...value.effects].reverse();
    const mapping = mapAnalysisPresentation(value);
    expect(mapping.effects.map((effect) => effect.code)).toEqual([...CANONICAL_EFFECT_ORDER]);
    expect(mapping.effects.map((effect) => effect.uiLabel)).toEqual([
      '판매수량', '제품 Mix', '판가', '매출환율', '원재료', '제조', '재고·원가 반영시차', '변동 판매관리비', '고정 판매관리비', '관세',
    ]);
    expect(mapping.effects.map((effect) => effect.uiCategoryLabel)).toEqual([
      '내부', '내부', '내부', '외부', '비용', '비용', '비용', '비용', '비용', '외부',
    ]);
    expect(mapping.residual.uiLabel).toBe('기타 요인');
    expect(mapping.residual.amount).toBe(value.residual.amount);
    expect(mapping.waterfallBars.find((bar) => bar.id === 'residual')?.delta).toBe(value.residual.amount);
  });

  it('keeps selection synchronized between Effect table and Waterfall, including residual', () => {
    render(<AnalysisPresentationPanel value={presentationFixture()} role="admin" />);
    const mixBar = screen.getByTestId('waterfall-bar-sales_mix');
    fireEvent.click(mixBar);
    expect(screen.getByTestId('effect-select-sales_mix')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('effect-row-sales_mix')).toHaveClass('row-active');

    fireEvent.click(screen.getByTestId('effect-select-residual'));
    expect(screen.getByTestId('waterfall-bar-residual')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('effect-row-residual')).toHaveClass('row-active');
  });

  it('uses profit-effect sign classes for positive, negative and zero values', () => {
    const value = presentationFixture();
    value.effects[0] = { ...value.effects[0], profit_effect: 0 };
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    expect(screen.getByTestId('effect-tone-sales_quantity')).toHaveClass('variance-analysis__tone--zero');
    expect(screen.getByTestId('effect-tone-sales_mix')).toHaveClass('variance-analysis__tone--positive');
    expect(screen.getByTestId('effect-tone-sales_fx')).toHaveClass('variance-analysis__tone--negative');
    expect(screen.getByTestId('effect-tone-residual')).toHaveClass('variance-analysis__tone--positive');
  });

  it('uses the same unfavorable tone for a negative residual', () => {
    const value = presentationFixture();
    value.residual.amount = -20;
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    expect(screen.getByTestId('effect-tone-residual')).toHaveClass('variance-analysis__tone--negative');
    expect(screen.getByTestId('waterfall-bar-residual')).toHaveClass('variance-analysis__waterfall-bar--negative');
  });

  it('rejects an identity mismatch without correcting the payload or showing Evidence', async () => {
    const malformed = presentationFixture();
    malformed.kpis.effects_total += 1;
    vi.stubGlobal('fetch', vi.fn(() => json(malformed)));
    render(<CoreAnalysisView role="viewer" />);
    fireEvent.change(screen.getByLabelText('Result ID'), { target: { value: TEST_RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByText('서버 응답 형식이 올바르지 않습니다.')).toBeInTheDocument();
    expect(screen.queryByTestId('analysis-presentation')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '분석 근거 엑셀 내려받기' })).not.toBeInTheDocument();
  });

  it('clears READY presentation and Evidence together when Viewer availability changes', async () => {
    let reads = 0;
    vi.stubGlobal('fetch', vi.fn(() => {
      reads += 1;
      return reads === 1
        ? json(presentationFixture())
        : json({ error: { code: 'RESULT_NOT_AVAILABLE', message: 'Result not available' } }, 404);
    }));
    render(<CoreAnalysisView role="viewer" />);
    fireEvent.change(screen.getByLabelText('Result ID'), { target: { value: TEST_RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByTestId('analysis-presentation')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '분석 근거 엑셀 내려받기' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    await waitFor(() => expect(screen.queryByTestId('analysis-presentation')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '분석 근거 엑셀 내려받기' })).not.toBeInTheDocument();
    expect(screen.getByTestId('viewer-empty')).toBeInTheDocument();
  });

  it('does not let an older Viewer response overwrite the latest Result', async () => {
    let resolveFirst!: (response: Response) => void;
    const first = new Promise<Response>((resolve) => { resolveFirst = resolve; });
    let calls = 0;
    vi.stubGlobal('fetch', vi.fn(() => {
      calls += 1;
      if (calls === 1) return first;
      const current = presentationFixture();
      current.identity.baseline_model_name = 'Latest Base';
      return json(current);
    }));
    render(<CoreAnalysisView role="viewer" />);
    const input = screen.getByLabelText('Result ID');
    fireEvent.change(input, { target: { value: '55555555-5555-4555-8555-555555555555' } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    fireEvent.change(input, { target: { value: TEST_RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    expect(await screen.findByText(/Latest Base/)).toBeInTheDocument();
    const old = presentationFixture();
    old.identity.baseline_model_name = 'Old Base';
    resolveFirst(new Response(JSON.stringify(old), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await waitFor(() => expect(screen.queryByText(/Old Base/)).not.toBeInTheDocument());
    expect(screen.getByText(/Latest Base/)).toBeInTheDocument();
  });
});
