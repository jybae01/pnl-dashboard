import React from 'react';
import { CalculationHistoryView } from '../../integration/CalculationHistoryView';

interface CalculationHistoryTableProps {
  onGoToVariance?: (resultId?: string) => void;
}

/** Compatibility wrapper for the durable BFF-backed calculation history view.
 *
 * The canonical implementation is the durable BFF-backed integration view;
 * no dummy rows, timer, toast-only download, or fabricated result identity
 * remains in this path.
 */
export const CalculationHistoryTable: React.FC<CalculationHistoryTableProps> = () => (
  <CalculationHistoryView />
);
