"""
Optimizer V1 (CP-SAT)
- Fixed routing, all 20 orders accepted
- AddCircuit per machine for sequencing (built-in subtour elimination)
- Sequence-dependent setup via reified timing constraints on chosen arcs
- Objective: WT * sum(priority * tardiness) + WS * total_setup_time   (scaled units)
"""
import pandas as pd
from ortools.sat.python import cp_model

SCALE = 1000  # 1 hour = 1000 units
HORIZON = 250 * SCALE
WT, WS = 1, 1

orders = pd.read_csv("orders.csv")
processing = pd.read_csv("processing_times.csv")
machines_df = pd.read_csv("machines.csv")

routing = {
    "P1": ["M1", "M2", "M3", "M4"],
    "P2": ["M1", "M2", "M3", "M4"],
    "P3": ["M1", "M3", "M4"],
}

setup_time_hr = dict(zip(machines_df.machine_id, machines_df.setup_time_hr))
proc_lookup = {(r.order_id, r.machine_id): r.processing_time_hr for r in processing.itertuples()}

model = cp_model.CpModel()

starts, ends, op_machine, op_product = {}, {}, {}, {}

for o in orders.itertuples():
    stages = routing[o.product_type]
    for k, m in enumerate(stages):
        dur = int(round(proc_lookup[(o.order_id, m)] * SCALE))
        s = model.NewIntVar(0, HORIZON, f"s_{o.order_id}_{k}")
        e = model.NewIntVar(0, HORIZON, f"e_{o.order_id}_{k}")
        model.Add(e == s + dur)
        starts[(o.order_id, k)] = s
        ends[(o.order_id, k)] = e
        op_machine[(o.order_id, k)] = m
        op_product[(o.order_id, k)] = o.product_type

# Release + within-order stage precedence
for o in orders.itertuples():
    release = int(round((o.release_day * 24 + o.release_hour) * SCALE))
    model.Add(starts[(o.order_id, 0)] >= release)
    stages = routing[o.product_type]
    for k in range(len(stages) - 1):
        model.Add(starts[(o.order_id, k + 1)] >= ends[(o.order_id, k)])

# Group operations by machine
machine_ops = {m: [] for m in machines_df.machine_id}
for (oid, k), m in op_machine.items():
    machine_ops[m].append((oid, k))

setup_terms = []  # (bool_lit, setup_cost_scaled, machine_id) for objective + reporting

for m, ops in machine_ops.items():
    n = len(ops)
    if n == 0:
        continue
    su = int(round(setup_time_hr[m] * SCALE))
    arcs = []
    lit_map = {}

    for i in range(n):
        lit_in = model.NewBoolVar(f"arc_{m}_depot_to_{i}")
        arcs.append((0, i + 1, lit_in))
        lit_map[(0, i + 1)] = lit_in

        lit_out = model.NewBoolVar(f"arc_{m}_{i}_to_depot")
        arcs.append((i + 1, 0, lit_out))
        lit_map[(i + 1, 0)] = lit_out

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            lit = model.NewBoolVar(f"arc_{m}_{i}_to_{j}")
            arcs.append((i + 1, j + 1, lit))
            lit_map[(i + 1, j + 1)] = lit

    model.AddCircuit(arcs)

    for i in range(n):
        oid_i, k_i = ops[i]
        for j in range(n):
            if i == j:
                continue
            oid_j, k_j = ops[j]
            lit = lit_map[(i + 1, j + 1)]
            cost = su if op_product[(oid_i, k_i)] != op_product[(oid_j, k_j)] else 0
            model.Add(starts[(oid_j, k_j)] >= ends[(oid_i, k_i)] + cost).OnlyEnforceIf(lit)
            if cost > 0:
                setup_terms.append((lit, cost, m))

# Tardiness
tardi_vars = []
for o in orders.itertuples():
    stages = routing[o.product_type]
    last_k = len(stages) - 1
    due = int(round((o.due_day * 24 + o.due_hour) * SCALE))
    T = model.NewIntVar(0, HORIZON, f"T_{o.order_id}")
    model.Add(T >= ends[(o.order_id, last_k)] - due)
    tardi_vars.append((o.order_id, T, o.priority, due))

# Objective
tardi_obj = sum(WT * pr * T for _, T, pr, _ in tardi_vars)
setup_obj = sum(WS * cost * lit for lit, cost, _ in setup_terms)
model.Minimize(tardi_obj + setup_obj)

# ---- Warm start from the frozen EDD baseline schedule ----
baseline_sched = pd.read_csv("user_baseline/baseline_schedule.csv")
for r in baseline_sched.itertuples():
    key = (r.order_id, r.stage - 1)
    if key in starts:
        model.add_hint(starts[key], int(round(r.processing_start * SCALE)))

solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60
solver.parameters.num_search_workers = 8
solver.parameters.random_seed = 42
status = solver.Solve(model)

print("Status:", solver.StatusName(status))
print("Objective (scaled):", solver.ObjectiveValue())
print("Best bound (scaled):", solver.BestObjectiveBound())
print("Wall time:", solver.WallTime(), "s")

if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    raise SystemExit("No feasible solution found.")

# ---- Extract results ----
results = []
for oid, T, pr, due in tardi_vars:
    stages = routing[orders.set_index("order_id").loc[oid, "product_type"]]
    last_k = len(stages) - 1
    completion = solver.Value(ends[(oid, last_k)]) / SCALE
    tardiness = solver.Value(T) / SCALE
    results.append({
        "order_id": oid, "due_hour": due / SCALE,
        "completion_hour": round(completion, 2),
        "tardiness_hr": round(tardiness, 2), "priority": pr,
    })
results_df = pd.DataFrame(results)

schedule = []
for (oid, k), m in op_machine.items():
    schedule.append({
        "order_id": oid, "stage": k + 1, "machine_id": m,
        "start_hr": round(solver.Value(starts[(oid, k)]) / SCALE, 2),
        "end_hr": round(solver.Value(ends[(oid, k)]) / SCALE, 2),
    })
schedule_df = pd.DataFrame(schedule).sort_values(["machine_id", "start_hr"])

machine_setup_hr = {m: 0.0 for m in machines_df.machine_id}
n_changeovers = {m: 0 for m in machines_df.machine_id}
for lit, cost, m in setup_terms:
    if solver.Value(lit):
        machine_setup_hr[m] += cost / SCALE
        n_changeovers[m] += 1
total_setup_hr = sum(machine_setup_hr.values())

print("\n" + "=" * 70)
print("OPTIMIZER V1 (CP-SAT) — RESULTS")
print("=" * 70)
print(results_df.sort_values("order_id").to_string(index=False))
print("\n" + "-" * 70)
raw_tardiness = results_df["tardiness_hr"].sum()
weighted_tardiness = (results_df["tardiness_hr"] * results_df["priority"]).sum()
print(f"Raw total tardiness: {raw_tardiness:.2f} hours")
print(f"Priority-weighted tardiness: {weighted_tardiness:.2f}")
print(f"Late orders: {(results_df['tardiness_hr'] > 0).sum()} / {len(results_df)}")
print(f"On-time orders: {(results_df['tardiness_hr'] == 0).sum()} / {len(results_df)}")
print(f"Total setup time: {total_setup_hr:.2f} hours")

print("\n" + "-" * 70)
print("Machine utilization:")
for m in machines_df.machine_id:
    m_sched = schedule_df[schedule_df.machine_id == m]
    proc_hours = sum(proc_lookup[(r.order_id, m)] for r in m_sched.itertuples())
    total_hours = proc_hours + machine_setup_hr[m]
    last_finish = m_sched["end_hr"].max() if len(m_sched) else 0
    print(f"{m}: {total_hours:.2f}h (processing={proc_hours:.2f}h, "
          f"setup={machine_setup_hr[m]:.2f}h over {n_changeovers[m]} changeovers), "
          f"last job finishes at t={last_finish:.1f}h")

schedule_df.to_csv("optimizer_v1_schedule.csv", index=False)
results_df.to_csv("optimizer_v1_results.csv", index=False)
print("\nSaved: optimizer_v1_schedule.csv, optimizer_v1_results.csv")