/**
 * Day 22: the registry-scale parameter editor.
 *
 * A thin shell over `registry.ts`: the payload comes from `GET /api/registry`,
 * the draft survives filtering/page switches, at most `PAGE_SIZE` rows render
 * at once (10,000 fields never become 10,000 components), validation is local
 * against the spec metadata and its summary is always visible before applying,
 * and export/import keep a schema-hash guard. Applying POSTs a validated
 * scenario restart through the same channel as the Day 9 editor.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { CORE_URL, CoreError, fetchActiveConfig, loadConfig } from "./api";
import {
  formatValue,
  importDraft,
  parseRegistryPayload,
  paginateSpecs,
  validateEdits,
  validateValue,
  exportDraft,
  type EditMap,
  type EditValue,
  type ParameterSpecView,
  type RegistryView,
} from "./registry";

const PAGE_SIZE = 50;
const DEFAULT_TAB = "all";

interface RegistryEditorProps {
  activeScenarioId: string | null;
  onClose: () => void;
  onApplied?: (config: unknown) => void;
}

export function RegistryEditor({ activeScenarioId, onClose, onApplied }: RegistryEditorProps) {
  const [view, setView] = useState<RegistryView | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadMs, setLoadMs] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [owner, setOwner] = useState<string | null>(DEFAULT_TAB);
  const [editedOnly, setEditedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [edits, setEdits] = useState<EditMap>({});
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [applyMessage, setApplyMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const started = performance.now();
    fetch(`${CORE_URL}/api/registry`)
      .then(async (res) => {
        if (!res.ok) throw new CoreError(`core returned HTTP ${res.status}`, res.status);
        const parsed = parseRegistryPayload(await res.json());
        if (cancelled) return;
        setView(parsed);
        setLoadMs(Math.round(performance.now() - started));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const editedKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const [ownerName, values] of Object.entries(edits)) {
      for (const shortKey of Object.keys(values)) keys.add(`${ownerName}.${shortKey}`);
    }
    return keys;
  }, [edits]);

  const issues = useMemo(() => (view ? validateEdits(view, edits) : []), [view, edits]);

  const pageResult = useMemo(() => {
    if (!view) return null;
    return paginateSpecs(
      view.specs,
      { query, owner, editedOnly, page, pageSize: PAGE_SIZE },
      editedKeys,
    );
  }, [view, query, owner, editedOnly, page, editedKeys]);

  const setDraft = useCallback(
    (spec: ParameterSpecView, raw: string) => {
      let value: EditValue = raw;
      if (spec.kind === "number" || spec.kind === "integer") {
        if (raw.trim() === "") return;
        const parsed = Number(raw);
        if (Number.isNaN(parsed)) {
          // Non-numeric input stays local; the validator reports it.
          value = raw;
        } else {
          value = parsed;
        }
      } else if (spec.kind === "boolean") {
        value = raw === "true";
      }
      setEdits((prev) => ({ ...prev, [spec.owner]: { ...(prev[spec.owner] ?? {}), [spec.shortKey]: value } }));
    },
    [],
  );

  const touchDefault = useCallback(
    (spec: ParameterSpecView) =>
      setEdits((prev) => ({
        ...prev,
        [spec.owner]: { ...(prev[spec.owner] ?? {}), [spec.shortKey]: spec.default as EditValue },
      })),
    [],
  );

  const revertField = useCallback((spec: ParameterSpecView) => {
    setEdits((prev) => {
      const ownerValues = { ...(prev[spec.owner] ?? {}) };
      delete ownerValues[spec.shortKey];
      const next = { ...prev, [spec.owner]: ownerValues };
      if (Object.keys(ownerValues).length === 0) delete next[spec.owner];
      return next;
    });
  }, []);

  const revertAll = useCallback(() => setEdits({}), []);

  const exportFile = useCallback(() => {
    if (!view) return;
    const text = exportDraft(view, edits, CORE_URL);
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "constellab-parameters.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }, [view, edits]);

  const importFile = useCallback(
    (file: File) => {
      if (!view) return;
      void file.text().then((text) => {
        const result = importDraft(text, view);
        if (result.ok) {
          setEdits(result.edits);
          setPage(1);
          setEditedOnly(true);
          setQuery("");
          setOwner(null);
          setImportMessage(`imported ${result.imported} values (schema ${result.schemaHash.slice(0, 12)})`);
        } else {
          setImportMessage(result.error);
        }
      });
    },
    [view],
  );

  const apply = useCallback(async () => {
    if (!view || issues.length || !activeScenarioId) return;
    setApplying(true);
    setApplyMessage(null);
    try {
      // Fleet-wide parameter presets ride the scenario's fleet default
      // components; owners with no component in the scenario are refused.
      const config = await fetchActiveConfig();
      const componentList = (config.components as { type: string; parameters?: Record<string, EditValue> }[] | undefined) ?? [];
      const byType = new Map(componentList.map((component) => [component.type, component]));
      const skipped: string[] = [];
      for (const [ownerName, values] of Object.entries(edits)) {
        const component = byType.get(ownerName);
        if (!component) {
          skipped.push(ownerName);
          continue;
        }
        component.parameters = { ...(component.parameters ?? {}), ...values };
      }
      const wanted = Object.keys(edits);
      if (skipped.length && skipped.length === wanted.length) {
        setApplyMessage({
          kind: "error",
          text: `this scenario declares none of: ${skipped.join(", ")}`,
        });
        return;
      }
      const loaded = await loadConfig(config);
      setApplyMessage({
        kind: "ok",
        text: `applied ${Object.entries(edits).reduce((n, [, values]) => n + Object.keys(values).length, 0)} values into fleet defaults; core restarted at epoch`,
      });
      setEdits({});
      onApplied?.(loaded.scenario);
    } catch (err) {
      setApplyMessage({
        kind: "error",
        text: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setApplying(false);
    }
  }, [view, edits, issues.length, activeScenarioId, onApplied]);

  const editedCount = Object.values(edits).reduce(
    (sum, values) => sum + Object.keys(values).length,
    0,
  );

  return (
    <section aria-label="Registry editor" className="registry-editor">
      <header className="registry-editor__header">
        <div>
          <h2 className="registry-editor__title">Parameter Registry</h2>
          {view && (
            <p className="registry-editor__meta mono">
              {view.specs.length} fields · {view.owners.length} owners · schema {view.schemaHash.slice(0, 12)}
              {loadMs !== null && ` · loaded in ${loadMs} ms`}
            </p>
          )}
          {loadError && <p className="registry-editor__error">{loadError}</p>}
        </div>
        <button type="button" className="registry-editor__close" onClick={onClose} aria-label="Close registry editor">
          ✕
        </button>
      </header>

      <div className="registry-editor__controls">
        <input
          type="search"
          value={query}
          placeholder="Search key, label or unit…"
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
          aria-label="Search parameters"
        />
        <select
          value={owner ?? ""}
          onChange={(event) => {
            setOwner(event.target.value === "" ? null : event.target.value);
            setPage(1);
          }}
          aria-label="Filter by owner"
        >
          <option value="">All owners</option>
          {view?.owners.map((ownerName) => (
            <option key={ownerName} value={ownerName}>
              {ownerName}
            </option>
          ))}
        </select>
        <label className="registry-editor__toggle">
          <input
            type="checkbox"
            checked={editedOnly}
            onChange={(event) => {
              setEditedOnly(event.target.checked);
              setPage(1);
            }}
          />
          Edited only ({editedKeys.size})
        </label>
      </div>

      {issues.length > 0 && (
        <div className="registry-editor__issues" role="alert">
          <strong>{issues.length} validation issue{issues.length === 1 ? "" : "s"}:</strong>
          <ul>
            {issues.slice(0, 5).map((issue) => (
              <li key={issue.path} className="mono">
                {issue.path}: {issue.message}
              </li>
            ))}
          </ul>
          {issues.length > 5 && <span>… and {issues.length - 5} more</span>}
        </div>
      )}

      {pageResult && (
        <div className="registry-editor__body">
          <table className="registry-editor__table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Value</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pageResult.slice.map((spec) => {
                const current = edits[spec.owner]?.[spec.shortKey];
                const isEdited = current !== undefined;
                const problem = isEdited ? validateValue(spec, current) : null;
                return (
                  <tr key={spec.key} className={isEdited ? "is-edited" : undefined}>
                    <td>
                      <div className="registry-editor__field-label">{spec.label || spec.shortKey}</div>
                      <div className="registry-editor__field-key mono">{spec.key}</div>
                      <div className="registry-editor__field-help">{spec.description}</div>
                      <div className="registry-editor__field-meta mono">
                        {spec.kind}
                        {spec.unit !== "1" ? ` · ${spec.unit}` : ""}
                        {spec.minimum !== null ? ` · min ${spec.minimum}` : ""}
                        {spec.maximum !== null ? ` · max ${spec.maximum}` : ""}
                        {spec.distribution !== "constant" ? ` · ${spec.distribution}` : ""}
                        {spec.mutability === "run" ? " · run" : ""}
                        {spec.modelVisible ? "" : " · metadata-only"}
                      </div>
                    </td>
                    <td>
                      {spec.options ? (
                        <select
                          value={isEdited ? `${current}` : `${spec.default}`}
                          onChange={(event) => setDraft(spec, event.target.value)}
                          aria-label={`${spec.key} (enum)`}
                        >
                          {!isEdited && <option value={`${spec.default}`}>{`${spec.default}`} (default)</option>}
                          {spec.options.map((option) => (
                            <option key={`${option}`} value={`${option}`}>
                              {`${option}`}
                            </option>
                          ))}
                        </select>
                      ) : spec.kind === "boolean" ? (
                        <select
                          value={isEdited ? (current ? "true" : "false") : spec.default ? "true" : "false"}
                          onChange={(event) => setDraft(spec, event.target.value)}
                          aria-label={`${spec.key} (boolean)`}
                        >
                          <option value="true">true</option>
                          <option value="false">false</option>
                        </select>
                      ) : (
                        <input
                          type={isEdited && typeof current === "number" ? "number" : "text"}
                          inputMode={spec.kind === "number" || spec.kind === "integer" ? "decimal" : "text"}
                          value={isEdited ? `${current}` : `${spec.default}`}
                          step="any"
                          onChange={(event) => setDraft(spec, event.target.value)}
                          aria-label={spec.key}
                          placeholder={formatValue(spec, spec.default as EditValue)}
                        />
                      )}
                      {problem && <div className="registry-editor__field-error">{problem}</div>}
                    </td>
                    <td>
                      <button type="button" onClick={() => touchDefault(spec)} title="Set to the registry default">
                        default
                      </button>
                      {isEdited && (
                        <button type="button" onClick={() => revertField(spec)} title="Revert this field">
                          ⏎
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="registry-editor__pager mono">
            <button
              type="button"
              disabled={pageResult.page <= 1}
              onClick={() => setPage(pageResult.page - 1)}
            >
              ‹
            </button>
            <span>
              page {pageResult.page} / {pageResult.pageCount} · {pageResult.total} fields shown
            </span>
            <button
              type="button"
              disabled={pageResult.page >= pageResult.pageCount}
              onClick={() => setPage(pageResult.page + 1)}
            >
              ›
            </button>
            {pageResult.hiddenEdits > 0 && (
              <span className="registry-editor__hidden-edits">
                {pageResult.hiddenEdits} edited field{pageResult.hiddenEdits === 1 ? "" : "s"} hidden by this filter
              </span>
            )}
          </div>
        </div>
      )}

      <footer className="registry-editor__footer">
        <div className="registry-editor__io">
          <button type="button" onClick={exportFile} disabled={!view}>
            Export draft
          </button>
          <label className="registry-editor__import">
            Import draft
            <input
              type="file"
              accept="application/json,.json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) importFile(file);
                event.target.value = "";
              }}
            />
          </label>
          {importMessage && <span className="mono">{importMessage}</span>}
        </div>
        <div className="registry-editor__actions">
          <span className="mono">{editedCount} edited · {issues.length} issue{issues.length === 1 ? "" : "s"}</span>
          <button type="button" onClick={revertAll} disabled={editedCount === 0}>
            Discard all
          </button>
          <button
            type="button"
            className="registry-editor__apply"
            onClick={() => void apply()}
            disabled={applying || issues.length > 0 || editedCount === 0 || !activeScenarioId}
            title={activeScenarioId ? undefined : "no scenario loaded"}
          >
            {applying ? "Applying…" : "Apply"}
          </button>
        </div>
        {applyMessage && <div className={`registry-editor__apply-message registry-editor__apply-message--${applyMessage.kind}`}>{applyMessage.text}</div>}
      </footer>
    </section>
  );
}
