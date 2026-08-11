import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AnalysisPresentationPanel } from './AnalysisPresentationPanel';
import { CoreAnalysisView } from './CoreAnalysisView';
import { presentationFixture, TEST_RESULT } from './presentationTestFixture';

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe('analysis presentation vertical slice', () => {
  it('renders backend KPI, canonical effects, residual, LC and separate activity units', () => {
    const value = presentationFixture();
    render(<AnalysisPresentationPanel value={value} role="admin" />);
    expect(screen.getByText('영업이익 증감')).toBeInTheDocument();
    expect(screen.getByText('4인치 LC')).toBeInTheDocument();
    expect(screen.getByText('UNEXPLAINED')).toBeInTheDocument();
    for (const label of ['판매수량', '제품 Mix', '판매단가', '매출환율', '원재료', '제조경비 손익실현', '변동 판관비', '고정 판관비', '관세']) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getByText(/Effects .* Residual .* OP Delta/)).toBeInTheDocument();
    expect(screen.getByText('persisted detail unavailable')).toBeInTheDocument();
    expect(screen.getAllByText('PCS').length).toBeGreaterThan(0);
    expect(screen.getAllByText('m').length).toBeGreaterThan(0);
    expect(screen.queryByText(/MCM.*Effect/i)).not.toBeInTheDocument();
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
