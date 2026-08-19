import { readFileSync } from 'node:fs';
import { dirname, extname, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

function productionImportGraph(entry: string): string[] {
  const visited = new Set<string>();
  const visit = (file: string) => {
    if (visited.has(file)) return;
    visited.add(file);
    const source = readFileSync(file, 'utf8');
    for (const match of source.matchAll(/from\s+['"](\.[^'"]+)['"]/g)) {
      const base = resolve(dirname(file), match[1]);
      const candidates = extname(base) ? [base] : [`${base}.ts`, `${base}.tsx`];
      const target = candidates.find((candidate) => {
        try { readFileSync(candidate); return true; } catch { return false; }
      });
      if (target) visit(target);
    }
  };
  visit(entry);
  return [...visited];
}

describe('P&L Reporting production graph guards', () => {
  it('contains the real graph and zero legacy endpoint, dummy, or test-fixture production imports', () => {
    const graph = productionImportGraph(resolve(process.cwd(), 'src/App.tsx'));
    const source = graph.map((file) => readFileSync(file, 'utf8')).join('\n');
    expect(source).toContain('/api/viewer/pnl-reporting');
    expect(source).toContain('/api/admin/pnl-reporting/');
    expect(source).not.toContain('/api/viewer/pnl-dashboard');
    expect(source).not.toMatch(/PnlDashboardPanel|MockPnlService|dummyPnlData|dummyPnl|from\s+['"][^'"]*pnlService/);
    expect(graph.filter((file) => /test-support|fixtures|\.test\./i.test(file))).toEqual([]);
  });

  it('keeps reporting adaptation and state owners free of business arithmetic', () => {
    const files = [
      'src/integration/pnlReportingSource.ts',
      'src/views/PnlStatusView.tsx',
      'src/components/pnl/PnlTable.tsx',
      'src/components/pnl/MfgCostTable.tsx',
      'src/components/pnl/SgaTable.tsx',
      'src/components/pnl/ProductSegmentPnlTable.tsx',
    ];
    const source = files.map((file) => readFileSync(resolve(process.cwd(), file), 'utf8')).join('\n');
    const formulaPatterns = [
      /actual\s*[-/]\s*plan/i,
      /operatingProfit\s*\/\s*revenue/i,
      /grossProfit\s*\/\s*revenue/i,
      /\b(?:achievement|variance|margin|asp|subtotal|ytd)\s*=/i,
      /\.reduce\s*\(/,
    ];
    expect(formulaPatterns.filter((pattern) => pattern.test(source))).toEqual([]);
  });
});
