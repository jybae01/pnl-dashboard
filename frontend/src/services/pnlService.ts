import { IPnlService } from '../types/service';
import {
  PnlKpiSummary,
  MonthlyTrendItem,
  PnlLineItem,
  MfgCostBreakdownItem,
  SgaBreakdownItem,
  ProductSegmentPnl,
  KeyVarianceNote,
  PnlFilterState
} from '../types/pnl';
import {
  DUMMY_KPI_SUMMARY,
  DUMMY_MONTHLY_TRENDS,
  DUMMY_HIERARCHICAL_PNL,
  DUMMY_MFG_COST_BREAKDOWN,
  DUMMY_SGA_BREAKDOWN,
  DUMMY_PRODUCT_SEGMENTS,
  DUMMY_KEY_NOTES
} from '../mocks/dummyPnlData';

export class MockPnlService implements IPnlService {
  async getKpiSummary(filter: PnlFilterState): Promise<PnlKpiSummary> {
    await new Promise(r => setTimeout(r, 100));
    const group = filter.productGroup || 'ALL';

    if (group === 'ALL') {
      return DUMMY_KPI_SUMMARY;
    }

    const scale = group === 'SW' ? 0.464 : group === 'BW' ? 0.344 : 0.192;
    return {
      revenue: {
        ...DUMMY_KPI_SUMMARY.revenue,
        monthlyActual: Math.round(DUMMY_KPI_SUMMARY.revenue.monthlyActual * scale),
        monthlyPlan: Math.round(DUMMY_KPI_SUMMARY.revenue.monthlyPlan * scale),
        monthlyVariance: Math.round(DUMMY_KPI_SUMMARY.revenue.monthlyVariance * scale),
        ytdActual: Math.round(DUMMY_KPI_SUMMARY.revenue.ytdActual * scale),
        ytdPlan: Math.round(DUMMY_KPI_SUMMARY.revenue.ytdPlan * scale),
        annualPlan: Math.round(DUMMY_KPI_SUMMARY.revenue.annualPlan * scale),
      },
      operatingProfit: {
        ...DUMMY_KPI_SUMMARY.operatingProfit,
        monthlyActual: Math.round(DUMMY_KPI_SUMMARY.operatingProfit.monthlyActual * (group === 'SW' ? 0.624 : group === 'BW' ? 0.256 : 0.12)),
        monthlyPlan: Math.round(DUMMY_KPI_SUMMARY.operatingProfit.monthlyPlan * (group === 'SW' ? 0.591 : group === 'BW' ? 0.301 : 0.108)),
        monthlyVariance: Math.round(DUMMY_KPI_SUMMARY.operatingProfit.monthlyVariance * scale),
        ytdActual: Math.round(DUMMY_KPI_SUMMARY.operatingProfit.ytdActual * scale),
        ytdPlan: Math.round(DUMMY_KPI_SUMMARY.operatingProfit.ytdPlan * scale),
        annualPlan: Math.round(DUMMY_KPI_SUMMARY.operatingProfit.annualPlan * scale),
      },
      adjustedOperatingProfit: {
        ...DUMMY_KPI_SUMMARY.adjustedOperatingProfit,
        monthlyActual: Math.round(DUMMY_KPI_SUMMARY.adjustedOperatingProfit.monthlyActual * scale),
        monthlyPlan: Math.round(DUMMY_KPI_SUMMARY.adjustedOperatingProfit.monthlyPlan * scale),
        monthlyVariance: Math.round(DUMMY_KPI_SUMMARY.adjustedOperatingProfit.monthlyVariance * scale),
        ytdActual: Math.round(DUMMY_KPI_SUMMARY.adjustedOperatingProfit.ytdActual * scale),
        ytdPlan: Math.round(DUMMY_KPI_SUMMARY.adjustedOperatingProfit.ytdPlan * scale),
        annualPlan: Math.round(DUMMY_KPI_SUMMARY.adjustedOperatingProfit.annualPlan * scale),
      },
      operatingMargin: group === 'SW' ? 13.45 : group === 'BW' ? 7.44 : 6.25,
      planOperatingMargin: group === 'SW' ? 10.38 : group === 'BW' ? 6.36 : 4.35,
      operatingMarginGap: group === 'SW' ? 3.07 : group === 'BW' ? 1.08 : 1.90,
      adjustedOperatingMargin: group === 'SW' ? 15.34 : group === 'BW' ? 8.84 : 6.67,
      planAdjustedOperatingMargin: group === 'SW' ? 11.89 : group === 'BW' ? 7.50 : 5.22,
      adjustedOperatingMarginGap: group === 'SW' ? 3.45 : group === 'BW' ? 1.34 : 1.45,
    };
  }

  async getMonthlyTrends(year: number, productGroup: string): Promise<MonthlyTrendItem[]> {
    await new Promise(r => setTimeout(r, 90));
    if (productGroup === 'ALL') {
      return DUMMY_MONTHLY_TRENDS;
    }
    const scale = productGroup === 'SW' ? 0.46 : productGroup === 'BW' ? 0.34 : 0.20;
    return DUMMY_MONTHLY_TRENDS.map(item => ({
      ...item,
      planRevenue: Math.round(item.planRevenue * scale),
      actualRevenue: item.actualRevenue ? Math.round(item.actualRevenue * scale) : undefined,
      forecastRevenue: item.forecastRevenue ? Math.round(item.forecastRevenue * scale) : undefined,
      planOpProfit: Math.round(item.planOpProfit * scale),
      actualOpProfit: item.actualOpProfit ? Math.round(item.actualOpProfit * scale) : undefined,
      forecastOpProfit: item.forecastOpProfit ? Math.round(item.forecastOpProfit * scale) : undefined,
      planAdjOpProfit: Math.round(item.planAdjOpProfit * scale),
      actualAdjOpProfit: item.actualAdjOpProfit ? Math.round(item.actualAdjOpProfit * scale) : undefined,
      forecastAdjOpProfit: item.forecastAdjOpProfit ? Math.round(item.forecastAdjOpProfit * scale) : undefined,
    }));
  }

  async getPnlTable(filter: PnlFilterState): Promise<PnlLineItem[]> {
    await new Promise(r => setTimeout(r, 120));
    return DUMMY_HIERARCHICAL_PNL;
  }

  async getMfgCostBreakdown(filter: PnlFilterState): Promise<MfgCostBreakdownItem[]> {
    await new Promise(r => setTimeout(r, 100));
    return DUMMY_MFG_COST_BREAKDOWN;
  }

  async getSgaBreakdown(filter: PnlFilterState): Promise<SgaBreakdownItem[]> {
    await new Promise(r => setTimeout(r, 100));
    return DUMMY_SGA_BREAKDOWN;
  }

  async getItemSegmentPnl(filter: PnlFilterState): Promise<ProductSegmentPnl[]> {
    await new Promise(r => setTimeout(r, 110));
    return DUMMY_PRODUCT_SEGMENTS;
  }

  async getKeyNotes(filter: PnlFilterState): Promise<KeyVarianceNote[]> {
    await new Promise(r => setTimeout(r, 60));
    return DUMMY_KEY_NOTES;
  }
}

export const pnlService = new MockPnlService();
