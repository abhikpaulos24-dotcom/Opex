// Shape of a saved simulation run (GET /api/simulations/{id}); only what the page reads.

type World = "without" | "with";
type Totals = { oee: number; failures: number; downtime_h: number };

export interface SimRun {
  id: string;
  params: { years: number; adoption_rate: number; sensor_coverage: number; seed: number };
  player: {
    days: number;
    start_date: string;
    machines: string[];
    worlds: Record<World, {
      failures: number[]; downtime_h: number[]; good: number[]; defects: number[]; energy_kwh: number[]; cost_inr: number[];
      states: string[]; // one character per machine per day, 0-5 (see STATE_INFO)
    }>;
  };
  ticker: { day: number; world: World; machine: string; component: string; kind: "failure" | "planned_repair"; detail: string; downtime_h: number }[];
  rewind: { day: number; machine: string; component: string; total_inr: number }[]; // total = repair + lost production
  summary: {
    kpis: Record<World, { oee: number }>;
    monthly: { oee_without: number[]; oee_with: number[] };
    yearly: ({ year: number } & Record<World, Totals>)[];
    delta: {
      net_benefit_inr: number; opex_cost_inr: number; roi_multiple: number; payback_months: number | null;
      failures_avoided: number; breakdowns_reduction: number; downtime_avoided_h: number; good_parts_gained: number;
      production_protected_inr: number; maintenance_savings_inr: number; maintenance_cost_reduction: number;
      defects_avoided: number; scrap_savings_inr: number; energy_saved_mwh: number; co2_avoided_t: number;
      energy_savings_inr: number; oee_points: number;
    };
    benchmarks: Record<"breakdowns_reduction" | "maintenance_cost_reduction" | "downtime_reduction", { ours: number }>;
    calculations: { label: string; formula: string; value: string }[];
    costs: { sensor_kits_inr: number; implementation_inr: number; yearly_inr: number };
  };
}

export interface RunListItem {
  id: string;
  created_at: string;
  created_by: string;
  params: SimRun["params"];
  headline: { net_benefit_inr: number; roi_multiple: number };
}

export const WORLD_LABEL: Record<World, string> = { without: "Without AI", with: "With OpEx" };
