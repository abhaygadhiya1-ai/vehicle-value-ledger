// The export's contract: export.py writes window.DASH into data.js beside the page. Only the fields the page reads
// are typed; the rest stay loose until a view uses them.

export type BookRow = { m: string; cars: number; book: number; level: number; curve: number }
export type Check = [name: string, pass: boolean, detail: string]
export type Leak = { name: string; short: string; expected: number; one_in_ten: number }
export type Pair = [low: number, high: number]   // [measured rate, published rate]
export type Decision = 'clear' | 'hold' | 'review'
export type CarRow = { car: number; make: string; model: string; age: number; p3: number; p3_low: number; p3_high: number
  mark: number; low: number; high: number; reason: string; reason_type: string; thin: boolean; body: string }
export type UpgradeRow = CarRow & { owner: string }
export type SupplyRow = CarRow & { expected: number; route: string; action: string }
export type DeskRow = { car: number; make: string; model: string; came_back: string; age: number; mark: number; low: number
  high: number; cap_pct: number; day_cost: number; thin: boolean; reason_type: string; action: string; body: string }
// the tool pass, part 6: every listed car for the search, and each source's as-of date
export type CarRef = { car: number; make: string; model: string; body: string; in: ('claims' | 'upgrade' | 'incoming' | 'desk')[] }
export type Source = { source: string; name: string; holds: string; kind: string; views: string; records: number
  happened: string; learnt: string }
export type ClaimRow = { claim: string; car: number | null; dealer: string; programme: string; system: string; eur: number
  decision: Decision; reason: string; reason_type: string; filed: string; checked_after_days: number; action: string }

export type Scenario = { name: string; build: number; by_phase: number[]; range: [number, string][]; payback_plan: number
  payback_ref: number; loss_gate1_ref: number; value_ref: number; floor: number; switch: number; money_gate: number; note: string }

export type Group = {
  var: { leaks: Leak[]; expected: number; one_in_ten: number; stress: number }
  kpis_targets: {
    vin_link: number; precision: number; recall: number; claim_days: number; review_rate: number; uplift: number
    gl: number; band_tol: number; drift: number; days_cut: number; band_cov_heldout: number
    claims_recovered: string; route_margin: number; engine_margin: number
  }
  prices: {
    p1_low: number; p1_high: number; p1_book_low: number; p1_book_high: number
    p2_option_pct: number; p2_option_eur: number; p2_cold_pts: number; p2_tail_pct: number
    p2_tail_book_eur_m: number; p2_cold_book_eur_m: number; band_avg_pct: number; thin_switch_cars: number
    day_cost: number; day_cost_low: number; day_cost_high: number; channel_after: number; channel_before: number
    channel_breakeven_days: number
  }
  tied_caps: { from: number; to: number; band_half: number; cap: number }[]
  sample_car: { pltv_low: number; pltv_high: number; pl: Pair; p1_cost: Pair; p2_hold: Pair; gain_refinance: number
    loss_elsewhere: number; early_repay_cap: number; contribution: number }
  monthend_benchmark: { other: number; psa: number; fca: number; opel: number; years: string }
  targeting_upper: number
  programme: { run_cost: number; exit_gate: number; fallback_gate: number; scenarios: Scenario[] }
  phases: { n: number; name: string; months: string; where: string; earns: string }[]
  gates: [phase: number, gate: string, ifMissed: string][]
  funnel: { step: string; eur_m: number }[]
  levers: { lever: string; eur_m: number; from: string }[]
  risks: [risk: string, answer: string][]
  pilot: { per_arm: number; gate_pp: number; interim_extra_pct: number }
  [key: string]: unknown
}

export type Proto = {
  as_of: string
  book: BookRow[]
  book_now: BookRow
  level_now: { m: string; level: number; avg36: number; gap_pct: number; cold_third: boolean
    option_action: string; buyback_action: string }
  claims: { decisions: { decision: Decision; claims: number; eur: number }[]; review_share: number
    tool_precision: number; tool_recall: number; linked_share_value: number; total: number; total_eur: number
    by_system: { system: string; claims: number; eur: number }[]
    by_system_decision: { system: string; decision: Decision; claims: number; eur: number }[]
    reasons: { reason: string; decision: Decision; claims: number; eur: number }[]
    run_date: string; flagged_eur: number; lag_median_days: number; lag_q: number[]; within_sla: number }
  claim_queue: ClaimRow[]
  claim_queue_more: ClaimRow[]
  monthend: { share: number; cars: number; years: string; handover_3m: number
    by_make: { make: string; cars: number; share: number }[] }
  price1: { cars: number; incentives: number; charge_low: number; charge_high: number
    by_make: { make: string; cars: number; incentive_per_car: number; charge_low: number; charge_high: number }[] }
  upgrade: { window_month: number; retail_scored: number; flagged: number; financed: number; financed_share: number
    flag_cut: number; flag_ages: number[]; by_age: { age: number; flagged: number; financed: number; queued: number }[]
    pilot: { treated: number; control: number; dealers: number } }
  upgrade_queue: UpgradeRow[]
  upgrade_queue_more: UpgradeRow[]
  ready_curve: { age: number; p3: number; p3_low: number; p3_high: number; cars: number }[]
  level_result: { year: number; cars: number; level_part: number; per_car: number }[]
  level_result_total: { cars: number; level_part: number; residual_set: number }
  returns_by_month: { m: string; cars: number }[]
  supply_queue: SupplyRow[]
  supply_queue_more: SupplyRow[]
  supply_by_model: { make: string; model: string; cars: number; expected_3m: number; expected_eur: number }[]
  supply_by_age: { age: number; cars: number; p3: number; expected_3m: number }[]
  pricing_desk: DeskRow[]
  desk_count: number
  desk_past_breakeven: number
  thin: { models: number; cars: number; of_models: number; counts: number[]; list: { make: string; model: string; cars: number }[] }
  supply_totals: { book: string; cars: number; expected_3m: number; expected_12m: number; expected_eur: number }[]
  metric_lines: [line: string, held: string][]
  // each queue's short fixed list of reason types, [type, what it means]: the rows carry one each
  reason_types: Record<'claims' | 'timing' | 'desk', [type: string, means: string][]>
  car_index: CarRef[]
  sources: Source[]
  [key: string]: unknown
}

export type Dash = {
  built: string
  group: Group
  proto: Proto
  trace: [label: string, source: string][]
  checks: Check[]
}

declare global {
  interface Window { DASH?: Dash }
}

export const DASH = window.DASH
