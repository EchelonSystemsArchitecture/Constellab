/**
 * Day 9: schema-driven parameter editor.
 *
 * The running scenario is never mutated in place. Edits accumulate in a draft,
 * the contract validator checks the whole draft, and Apply submits it through the
 * core's validated load transaction (which restarts at epoch). Labels, units,
 * steps and bounds all come from the JSON Schema `x-ui` metadata.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { SimulationConfig } from "../contract";
import { SCHEMA_VERSION } from "../contract";
import { CoreError, fetchActiveConfig, loadConfig } from "./api";
import {
  definitionFields,
  getAtPath,
  issuesByPath,
  issuesForField,
  updateAtPath,
  validateDraft,
  type FieldSpec,
} from "./schema";
import { WIDGET_REGISTRY } from "./widgets";

interface ParameterEditorProps {
  activeScenarioId: string | null;
  onClose: () => void;
  onApplied?: (config: SimulationConfig) => void;
}

type TextMap = Record<string, string>;

function formatValue(value: unknown): string {
  if (value === undefined || value === null) return "";
  return String(value);
}

function initTexts(config: SimulationConfig): TextMap {
  const texts: TextMap = {};
  for (const field of definitionFields("SimulationConfig")) {
    texts[field.path] = formatValue(getAtPath(config, field.path));
  }
  config.satellites.forEach((_, index) => {
    for (const field of definitionFields("OrbitElements", { pathPrefix: `satellites[${index}].orbit` })) {
      texts[field.path] = formatValue(getAtPath(config, field.path));
    }
  });
  return texts;
}

function parseFieldValue(field: FieldSpec, text: string): { ok: true; value: unknown } | { ok: false; message: string } {
  const trimmed = text.trim();
  if (field.type === "number" || field.type === "integer") {
    if (trimmed === "") return { ok: false, message: "must not be empty" };
    const value = Number(trimmed);
    if (!Number.isFinite(value)) return { ok: false, message: "must be a number" };
    if (field.type === "integer" && !Number.isInteger(value)) return { ok: false, message: "must be an integer" };
    return { ok: true, value };
  }
  if (field.type === "boolean") return { ok: true, value: text === "true" };
  if (field.type === "string") return { ok: true, value: text };
  return { ok: false, message: `unsupported parameter type ${field.type}` };
}

export function ParameterEditor({ activeScenarioId, onClose, onApplied }: ParameterEditorProps) {
  const [baseline, setBaseline] = useState<SimulationConfig | null>(null);
  const [draft, setDraft] = useState<SimulationConfig | null>(null);
  const [texts, setTexts] = useState<TextMap>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [satelliteIndex, setSatelliteIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    setStatus(null);
    setApplyError([]);
    try {
      const config = await fetchActiveConfig();
      setBaseline(config);
      setDraft(config);
      setTexts(initTexts(config));
      setFieldErrors({});
      setSatelliteIndex((current) => (current < config.satellites.length ? current : 0));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, activeScenarioId, reloadToken]);

  const scenarioFields = useMemo(() => definitionFields("SimulationConfig"), []);
  const orbitFields = useMemo(
    () => definitionFields("OrbitElements", { pathPrefix: `satellites[${satelliteIndex}].orbit` }),
    [satelliteIndex],
  );

  const issues = useMemo(() => (draft ? validateDraft(draft) : []), [draft]);
  const issuesByField = useMemo(() => issuesByPath(issues), [issues]);
  const hasTextErrors = Object.values(fieldErrors).some((messages) => messages.length > 0);

  const handleText = (field: FieldSpec, text: string) => {
    setTexts((current) => ({ ...current, [field.path]: text }));
    setStatus(null);
    if (field.readOnly) return;
    const parsed = parseFieldValue(field, text);
    if (!parsed.ok) {
      setFieldErrors((current) => ({ ...current, [field.path]: [parsed.message] }));
      return;
    }
    setFieldErrors((current) => {
      if (!current[field.path]) return current;
      const next = { ...current };
      delete next[field.path];
      return next;
    });
    setDraft((current) => (current ? updateAtPath(current, field.path, parsed.value) : current));
  };

  const revertField = (field: FieldSpec) => {
    if (!baseline) return;
    const fallback = field.defaultValue !== undefined
      ? field.defaultValue
      : getAtPath(baseline, field.path);
    setTexts((current) => ({ ...current, [field.path]: formatValue(fallback) }));
    setFieldErrors((current) => {
      const next = { ...current };
      delete next[field.path];
      return next;
    });
    setDraft((current) => (current ? updateAtPath(current, field.path, fallback) : current));
    setStatus(null);
  };

  const resetAll = () => {
    if (!baseline) return;
    setDraft(baseline);
    setTexts(initTexts(baseline));
    setFieldErrors({});
    setApplyError([]);
    setStatus("DRAFT RESET TO THE CONFIGURED VALUES");
  };

  const apply = async () => {
    if (!draft) return;
    setStatus(null);
    setApplyError([]);
    if (hasTextErrors) {
      setStatus("FIX THE HIGHLIGHTED FIELDS BEFORE APPLYING");
      return;
    }
    if (issues.length > 0) {
      setStatus("DRAFT VIOLATES THE CONTRACT — APPLY BLOCKED");
      return;
    }
    setSaving(true);
    try {
      const loaded = await loadConfig(draft);
      setBaseline(loaded.scenario);
      setDraft(loaded.scenario);
      setTexts(initTexts(loaded.scenario));
      setFieldErrors({});
      setStatus("APPLIED — CORE RESTARTED THE SCENARIO AT EPOCH");
      onApplied?.(loaded.scenario);
    } catch (err) {
      if (err instanceof CoreError && err.errors.length > 0) {
        setApplyError(err.errors.map((e) => `${e.path}: ${e.message}`));
      } else {
        setApplyError([err instanceof Error ? err.message : String(err)]);
      }
      setStatus("CORE REJECTED THE CONFIGURATION");
    } finally {
      setSaving(false);
    }
  };

  const renderField = (field: FieldSpec) => {
    const Widget = WIDGET_REGISTRY[field.widget] ?? WIDGET_REGISTRY.unsupported;
    const value = draft ? getAtPath(draft, field.path) : undefined;
    const errors = [...(fieldErrors[field.path] ?? []), ...issuesForField(issuesByField, field.path)];
    const configurable = !field.readOnly && field.type !== "unsupported";
    return (
      <div className={`param-row ${errors.length > 0 ? "param-row--invalid" : ""}`} key={field.path} data-field={field.path}>
        <div className="param-row__head">
          <span className="param-label">
            {field.label}
            {field.unit ? <span className="param-unit">{field.unit}</span> : null}
            {field.required ? <span className="param-required" title="Required by the contract">*</span> : null}
          </span>
          {configurable && (
            <button
              type="button"
              className="param-revert"
              onClick={() => revertField(field)}
              title={field.defaultValue !== undefined ? "Restore the schema default" : "Revert to the loaded value"}
              aria-label={`Revert ${field.label}`}
            >
              ↺
            </button>
          )}
        </div>
        <div className="param-row__control">
          <Widget
            field={field}
            value={value}
            text={texts[field.path] ?? formatValue(value)}
            errors={errors}
            disabled={saving}
            onChangeText={(text) => handleText(field, text)}
          />
        </div>
        {errors.map((message) => (
          <div className="param-error mono" key={message}>{message}</div>
        ))}
        {field.description && field.type === "unsupported" && (
          <div className="param-hint mono">{field.description}</div>
        )}
      </div>
    );
  };

  return (
    <aside className="inspector param-editor" data-testid="parameter-editor" aria-label="Mission parameters">
      <div className="inspector__header">
        <div className="inspector__title">
          <span className="drawer-dot" />
          <span>MISSION PARAMETERS</span>
        </div>
        <div className="inspector__header-actions">
          <button type="button" className="inspector__icon-btn" onClick={onClose} aria-label="Close parameters">
            ✕
          </button>
        </div>
      </div>

      {loading && (
        <div className="inspector__body--muted">
          <span className="loading-screen__spinner" /> reading validated config from core…
        </div>
      )}

      {loadError && (
        <div className="inspector__body--missing" role="alert">
          <div className="inspector__missing-title">CONFIG UNAVAILABLE</div>
          <p className="mono">{loadError}</p>
          <button type="button" className="inspector__link-btn" onClick={() => setReloadToken((n) => n + 1)}>
            RETRY
          </button>
        </div>
      )}

      {!loading && draft && baseline && (
        <div className="param-editor__body">
          <div className="param-editor__meta mono">
            {`${draft.scenario_id} · contract v${SCHEMA_VERSION} · ${draft.satellites.length} satellites · edits apply as a validated restart`}
          </div>

          <div className="param-editor__scroll">
            <section className="param-section">
              <h3 className="inspector__section-title">SIMULATION</h3>
              {scenarioFields.map(renderField)}
            </section>

            <section className="param-section">
              <h3 className="inspector__section-title">ORBIT ELEMENTS</h3>
              {draft.satellites.length > 0 ? (
                <>
                  <div className="param-row">
                    <div className="param-row__head">
                      <span className="param-label">ENTITY</span>
                    </div>
                    <div className="param-row__control">
                      <select
                        id="param-satellite"
                        className="param-input mono"
                        value={satelliteIndex}
                        onChange={(event) => {
                          setSatelliteIndex(Number(event.target.value));
                          setStatus(null);
                        }}
                      >
                        {draft.satellites.map((sat, index) => (
                          <option key={sat.id} value={index}>{`${index + 1}. ${sat.id}`}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  {orbitFields.map(renderField)}
                </>
              ) : (
                <div className="inspector__body--muted">
                  This scenario has no satellites. Add entities by loading a different scenario or an
                  inline configuration.
                </div>
              )}
            </section>
          </div>

          <div className="param-editor__footer">
            {status && <div className="param-status mono">{status}</div>}
            {applyError.length > 0 && (
              <ul className="param-apply-errors mono">
                {applyError.map((message) => <li key={message}>{message}</li>)}
              </ul>
            )}
            <div className="param-editor__actions">
              <button type="button" className="inspector__action-btn" onClick={resetAll} disabled={saving}>
                RESET DRAFT
              </button>
              <button
                type="button"
                className="inspector__action-btn param-apply"
                onClick={() => void apply()}
                disabled={saving || hasTextErrors || issues.length > 0}
                title={issues.length > 0 ? "The draft does not satisfy the contract" : "Validate and restart the scenario"}
              >
                {saving ? "APPLYING…" : "APPLY & RESTART"}
              </button>
            </div>
            {issues.length > 0 && (
              <div className="param-status param-status--invalid mono">
                {`${issues.length} contract issue${issues.length === 1 ? "" : "s"} block apply`}
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
