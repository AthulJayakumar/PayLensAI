"use client";

import { ChangeEvent, FormEvent, useRef, useState } from "react";
import { AnalysisSummary, uploadAnalysis } from "../lib/api";

type UploadPanelProps = {
  onComplete: (analysisId: string) => void;
  uploader?: (file: File) => Promise<AnalysisSummary>;
};

function fileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadPanel({ onComplete, uploader = uploadAnalysis }: UploadPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "analysing" | "error">("idle");
  const [error, setError] = useState("");

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setFile(selected);
    setError("");
    setStatus("idle");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Choose a canonical PayLens CSV before starting analysis.");
      return;
    }
    setStatus("analysing");
    setError("");
    try {
      const result = await uploader(file);
      onComplete(result.analysis_id);
    } catch (uploadError) {
      setStatus("error");
      setError(uploadError instanceof Error ? uploadError.message : "Analysis could not be completed.");
    }
  }

  return (
    <form className="upload-card" onSubmit={submit}>
      <div className="upload-heading">
        <span className="status-dot" />
        <span>New analysis</span>
      </div>
      <h2>Upload payment data</h2>
      <p>Canonical PayLens CSV · maximum 64 MiB</p>

      <input
        ref={inputRef}
        className="sr-only"
        type="file"
        accept=".csv,text/csv"
        onChange={chooseFile}
        aria-label="Payment CSV"
      />
      <button className="drop-zone" type="button" onClick={() => inputRef.current?.click()}>
        <span className="upload-icon">↑</span>
        <strong>{file ? "Change CSV" : "Choose payment CSV"}</strong>
        <small>Data stays in this local prototype session</small>
      </button>

      {file && (
        <div className="file-row" aria-label="Selected file">
          <div><strong>{file.name}</strong><small>{fileSize(file.size)}</small></div>
          <span>Ready</span>
        </div>
      )}
      {error && <div className="error-banner" role="alert">{error}</div>}
      <button className="primary-button" type="submit" disabled={status === "analysing"}>
        {status === "analysing" ? "Validating and analysing…" : "Analyse payments"}
      </button>
      <div className="upload-status" aria-live="polite">
        <span className={file ? "complete" : ""}>File selected</span>
        <span className={status === "analysing" ? "active" : ""}>Validation</span>
        <span className={status === "analysing" ? "active" : ""}>Analysis</span>
      </div>
    </form>
  );
}

