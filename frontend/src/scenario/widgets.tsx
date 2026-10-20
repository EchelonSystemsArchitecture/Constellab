/**
 * Day 9: widget registry keyed by schema-derived widget kind.
 *
 * Adding a same-type parameter is a schema/config change only: the editor looks
 * the widget up here instead of branching on parameter names.
 */
import type { ComponentType } from "react";
import type { FieldSpec, WidgetKind } from "./schema";

export interface WidgetProps {
  field: FieldSpec;
  /** Current draft value (last valid value while the text box is invalid). */
  value: unknown;
  /** Raw text, so intermediate values like "" or "1." are not destroyed. */
  text: string;
  errors: string[];
  disabled: boolean;
  onChangeText: (text: string) => void;
}

function NumberWidget({ field, text, errors, disabled, onChangeText }: WidgetProps) {
  return (
    <input
      type="number"
      className={`param-input mono ${errors.length > 0 ? "param-input--invalid" : ""}`}
      value={text}
      step={field.step ?? "any"}
      min={field.minimum}
      max={field.maximum}
      disabled={disabled}
      aria-invalid={errors.length > 0}
      aria-label={field.label}
      onChange={(event) => onChangeText(event.target.value)}
      // Typing is the interaction; wheel changes would silently rewrite a draft.
      onWheel={(event) => event.currentTarget.blur()}
    />
  );
}

function TextWidget({ field, text, errors, disabled, onChangeText }: WidgetProps) {
  return (
    <input
      type="text"
      className={`param-input mono ${errors.length > 0 ? "param-input--invalid" : ""}`}
      value={text}
      disabled={disabled}
      aria-invalid={errors.length > 0}
      aria-label={field.label}
      onChange={(event) => onChangeText(event.target.value)}
    />
  );
}

function BooleanWidget({ field, text, disabled, onChangeText }: WidgetProps) {
  return (
    <label className="param-toggle">
      <input
        type="checkbox"
        checked={text === "true"}
        disabled={disabled}
        aria-label={field.label}
        onChange={(event) => onChangeText(event.target.checked ? "true" : "false")}
      />
      <span className="mono">{text === "true" ? "TRUE" : "FALSE"}</span>
    </label>
  );
}

function ReadOnlyWidget({ value }: WidgetProps) {
  return (
    <span className="param-readonly mono" title="Read-only contract field">
      {value === undefined || value === null ? "—" : String(value)}
      <span className="param-readonly__tag">RO</span>
    </span>
  );
}

function UnsupportedWidget({ field }: WidgetProps) {
  return (
    <span className="param-unsupported mono">
      {`STRUCTURED FIELD “${field.key.toUpperCase()}” — edit it through its dedicated selector`}
    </span>
  );
}

export const WIDGET_REGISTRY: Record<WidgetKind, ComponentType<WidgetProps>> = {
  number: NumberWidget,
  integer: NumberWidget,
  string: TextWidget,
  boolean: BooleanWidget,
  readonly: ReadOnlyWidget,
  unsupported: UnsupportedWidget,
};
