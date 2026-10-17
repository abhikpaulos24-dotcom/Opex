// Shapes of the main API responses (only the fields the web app uses).

export type Severity = "critical" | "high" | "medium" | "low";
export type MachineState = "running" | "idle" | "maintenance" | "breakdown" | "stopped";

export interface Anomaly {
  signal: string;
  label: string;
  value: number;
  normal_low: number;
  normal_high: number;
  deviation_pct: number;
  severity: "watch" | "warning" | "critical";
  sentence: string;
  plain_sentence: string;
}

export interface Cause {
  key: string;
  name: string;
  component: string | null;
  match: number;
  probability: number;
}

export interface ComponentOutlook {
  component: string;
  component_name: string;
  health_pct: number;
  window: string;
}

export interface MaintenanceJob {
  component: string;
  component_name: string;
  when: string;
  emergency: boolean;
  inspect: string;
  parts: string[];
  repair_h: number;
  part_cost_inr: number;
  needed_within: string;
}

export interface MachineReport {
  machine: { id: string; name: string; line_id: string; product: string };
  plant_time: string;
  state: MachineState;
  state_detail: {
    idle_waste: boolean;
    speed_pct: number;
    replacing: string | null; // component being swapped during maintenance
    pending_jobs: { reason: string; in_minutes: number }[];
  };
  anomalies: Anomaly[];
  data_health: { score: number; completeness_pct: number; issues: { text: string }[] };
  components: Record<string, ComponentOutlook>;
  prediction: {
    p_fail_8h: number;
    window: string | null;
    method: "trend" | "model" | null;
    severity: Severity;
    failure_cost_inr: number;
    confidence: number;
    confidence_before_data_check: number;
  };
  root_cause: {
    top: Cause | null;
    candidates: Cause[];
    chain: { signal: string; text: string }[];
    memory: { sentence: string; matches?: { id: string; date: string; machine_id: string; root_cause: string; technician_note: string; downtime_h: number }[] };
  };
  quality: { sentence: string } | null;
  impact: { inr_per_hour: number; lost_parts_per_h: number; extra_defects_per_h: number; energy_per_part_change_pct: number | null };
  ranges: Record<string, [number, number]>;
  maintenance_plan: MaintenanceJob[];
  tech_tip: { title: string; text: string } | null;
}

export interface Option {
  key: string;
  title: string;
  description: string;
  downtime_h: number;
  total_inr: number;
  p_fail: number;
  extra_defects: number;
  energy_change_pct: number;
  confidence: number;
  lost_parts: number;
  safety_blocked: boolean;
  learned: { successes: number; trials: number };
  permission: "decide_minor" | "decide_major";
}

export interface Recommendation {
  id: string;
  machine_id: string;
  needed: true;
  preset: string;
  options: Option[];
  hours_to_window: number;
  hours_to_shift: number;
  recommendation: {
    action_key: string;
    headline: string;
    value_protected_inr: number;
    p_fail_before: number;
    p_fail_after: number;
    added_downtime_h: number;
    confidence: number;
    why: string[];
  };
}

export type RecommendationResponse = Recommendation | { needed: false; message: string };

export interface DecisionResult {
  decision: "approved" | "rejected" | "modified";
  action: string;
  result: string;
  check_in_plant_minutes: number;
}

export interface MachineTile {
  id: string;
  name: string;
  line_id: string;
  state: MachineState;
  severity: Severity;
  p_fail_8h: number;
  health_pct: number | null;
  headline: string;
  speed_pct: number;
}

export interface Alert {
  id: string;
  machine_id: string;
  severity: Severity;
  title: string;
  message: string;
  plant_time: string;
}

export interface Overview {
  plant_time: string;
  shift: string;
  kpis: {
    oee: number; availability: number; performance: number; quality: number; running: number; machines: number;
    down_now: string[]; downtime_min: number; maintenance_min: number; defect_rate: number; good_parts: number;
    energy_kwh: number; energy_kwh_per_part: number; anomalies: number;
  };
  health: Record<string, number>;
  risks: MachineTile[];
  machines: MachineTile[];
  lines: { id: string; name: string; oee: number; good_parts: number; worst_machine: string }[];
  events: { time: string; machine_id: string; message: string }[];
  maintenance: { due_soon: (MaintenanceJob & { machine: string })[] };
  window_in_h: number;
  alerts: Alert[];
  open_alert_count: number;
}
