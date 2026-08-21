import Link from "next/link";

export function AppHeader({ analysisId }: { analysisId?: string }) {
  return (
    <header className="app-header">
      <Link className="brand" href="/" aria-label="PayLens home">
        <span className="brand-mark">P</span><span>PAYLENS</span>
      </Link>
      <nav>
        {analysisId && <span className="analysis-reference">{analysisId.slice(0, 20)}…</span>}
        <Link className="secondary-button" href="/providers">Payment providers</Link>
        <Link className="secondary-button" href="/">New analysis</Link>
      </nav>
    </header>
  );
}
