import React from 'react';
import { CalculationHistoryView } from '../../integration/CalculationHistoryView';

interface CalculationHistoryTableProps {
  onGoToVariance: () => void;
}

/** Compatibility wrapper for the legacy handoff view.
 *
 * The canonical implementation is the durable BFF-backed integration view;
 * no dummy rows, timer, toast-only download, or fabricated result identity
 * remains in this path.
 */
export const CalculationHistoryTable: React.FC<CalculationHistoryTableProps> = () => (
  <CalculationHistoryView />
);
