// These mirror the shapes returned by the DevAgent FastAPI backend
// (see backend/app/storage.py and backend/app/schemas.py).

export interface Review {
  id: number;
  created_at: number; // unix seconds
  repo_full_name: string;
  pr_number: number;
  head_sha: string | null;
  summary: string | null;
  comment_count: number | null;
  sandbox_exit_code: number | null;
  error: string | null;
}

// One issue diagnosed by the debug analyzer.
export interface DebugIssue {
  file: string;
  line: number;
  problem: string;
  fix: string;
  patch: string | null;
}

// One static-analysis finding from the heuristic pattern checks.
export interface StaticFinding {
  file: string;
  line: number;
  rule: string;
  message: string;
}

// Result of POST /debug/analyze or POST /debug/scan.
export interface DebugResult {
  root_cause_summary: string;
  issues: DebugIssue[];
  static_findings: StaticFinding[];
}

// A persisted row from GET /debug/history.
export interface DebugScan {
  id: number;
  created_at: number;
  repo_path: string;
  mode: "scan" | "analyze";
  root_cause_summary: string | null;
  issue_count: number | null;
  static_finding_count: number | null;
  issues: DebugIssue[];
  static_findings: StaticFinding[];
}

export interface HealthStatus {
  status: string;
}