import React, { useEffect, useRef } from 'react';

export type NumericInputMode = 'month' | 'decimal';

interface EditableNumericInputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type' | 'inputMode' | 'value' | 'onChange' | 'onBlur'> {
  value: string;
  mode: NumericInputMode;
  onChange: (value: string) => void;
  onValueBlur?: (value: string) => void;
}

/**
 * A text-backed numeric editor. The text value is intentionally kept raw while
 * the user edits it; callers parse it only at their domain/submit boundary.
 * The first focus of each focus session selects the whole value, while a
 * subsequent click on an already-focused field is left to the browser so the
 * caret can be placed normally.
 */
export function EditableNumericInput({
  value,
  mode,
  onChange,
  onValueBlur,
  ...inputProps
}: EditableNumericInputProps) {
  const focusedRef = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const element = inputRef.current;
    if (!element) return undefined;

    const handleNativeBlur = () => {
      focusedRef.current = false;
      onValueBlur?.(element.value);
    };

    element.addEventListener('blur', handleNativeBlur);
    return () => element.removeEventListener('blur', handleNativeBlur);
  }, [onValueBlur]);

  const selectOnFirstFocus = (element: HTMLInputElement) => {
    if (focusedRef.current) return;
    focusedRef.current = true;
    element.select();
  };

  const handleFocus = (event: React.FocusEvent<HTMLInputElement>) => {
    selectOnFirstFocus(event.currentTarget);
  };

  const handlePointerFocus = (event: React.PointerEvent<HTMLInputElement>) => {
    if (focusedRef.current) return;
    // Prevent the browser's default pointer placement from collapsing the
    // selection that the first-focus contract establishes.
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.select();
  };

  const handleMouseFocus = (event: React.MouseEvent<HTMLInputElement>) => {
    if (focusedRef.current) return;
    // Older/test environments may dispatch mouse events without PointerEvent.
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.select();
  };

  return (
    <input
      ref={inputRef}
      {...inputProps}
      type="text"
      inputMode={mode === 'month' ? 'numeric' : 'decimal'}
      value={value}
      onFocus={handleFocus}
      onPointerDown={handlePointerFocus}
      onMouseDown={handleMouseFocus}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

export function parseMonthInput(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 12 ? parsed : null;
}

export function normalizeMonthInput(value: string): string {
  const parsed = parseMonthInput(value);
  return parsed === null ? value : String(parsed).padStart(2, '0');
}

export function parseDecimalInput(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === '') return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}
