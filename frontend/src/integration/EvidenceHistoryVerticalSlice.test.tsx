import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CoreAnalysisView } from './CoreAnalysisView';
import { CalculationHistoryView } from './CalculationHistoryView';
import { presentationFixture } from './presentationTestFixture';

const RESULT = '44444444-4444-4444-8444-444444444444';
const JOB = '33333333-3333-4333-8333-333333333333';

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json' },
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe('Evidence and history vertical slice', () => {
  it('shows the exact action only for a READY stored Result and downloads through BFF', async () => {
    const revoke = vi.fn();
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: revoke });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (path.includes('/api/viewer/results/') && path.endsWith('/presentation')) return json(presentationFixture());
      if (path.endsWith('/evidence')) return Promise.resolve(new Response(new Blob(['xlsx']), {
        status: 200,
        headers: {
          'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'Content-Disposition': "attachment; filename*=utf-8''evidence.xlsx",
        },
      }));
      throw new Error(path);
    }));
    render(<CoreAnalysisView role="viewer" />);
    expect(screen.queryByRole('button', { name: '분석 근거 엑셀 내려받기' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Result ID'), { target: { value: RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    const action = await screen.findByRole('button', { name: '분석 근거 엑셀 내려받기' });
    fireEvent.click(action);
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:test'));
  });

  it('removes a stale READY Result action after Viewer availability denial', async () => {
    let evidenceDenied = false;
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input);
      if (!path.endsWith('/evidence')) return json(presentationFixture());
      evidenceDenied = true;
      return json({ error: { code: 'RESULT_NOT_AVAILABLE', message: 'Result not available' } }, 404);
    }));
    render(<CoreAnalysisView role="viewer" />);
    fireEvent.change(screen.getByLabelText('Result ID'), { target: { value: RESULT } });
    fireEvent.click(screen.getByRole('button', { name: '조회' }));
    fireEvent.click(await screen.findByRole('button', { name: '분석 근거 엑셀 내려받기' }));
    await waitFor(() => expect(evidenceDenied).toBe(true));
    await waitFor(() => expect(screen.queryByTestId('stored-result')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', { name: '분석 근거 엑셀 내려받기' })).not.toBeInTheDocument();
  });

  it('shows history action only on completed rows with a real result_id', async () => {
    vi.stubGlobal('fetch', vi.fn(() => json({
      items: [
        { job_id: JOB, result_id: RESULT, status: 'COMPLETED', baseline_model_name: 'Base', comparison_model_name: 'Comparison', start_month: 1, end_month: 12, created_at: '2026-08-11T00:00:00Z' },
        { job_id: '55555555-5555-4555-8555-555555555555', result_id: null, status: 'PENDING', baseline_model_name: 'Base', comparison_model_name: 'Comparison', start_month: 1, end_month: 12, created_at: '2026-08-11T00:00:01Z' },
      ], next_before_created_at: null, next_before_job_id: null, dto_version: '1',
    })));
    render(<CalculationHistoryView />);
    expect(await screen.findByText(RESULT)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '분석 근거 엑셀 내려받기' })).toHaveLength(1);
  });
});
