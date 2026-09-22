# Manufacturing Operations Intelligence

A constraint-based production scheduling and optimization system for a simplified textile manufacturing environment.

The project explores how computational optimization can support manufacturing planning decisions involving **production deadlines, machine capacity, order priorities, routing, and sequence-dependent setup time**.

**Current status:** Part 1 — Optimization Engine

**Next:** Part 2 — AI Agent / Decision-Support Layer


## Overview

Manufacturing planners often need to make decisions such as:

* Which orders should be processed first?
* How should jobs be sequenced across machines?
* Which orders are at risk of missing their deadlines?
* How much production time is being consumed by machine changeovers?
* How can overall tardiness be reduced while respecting operational constraints?

To explore these problems, I built a small synthetic textile manufacturing environment and compared two scheduling approaches:

1. An **Earliest Due Date (EDD) baseline scheduler**
2. A **constraint-based CP-SAT optimization model** using Google OR-Tools

The optimization engine is designed to become the deterministic decision layer underneath a future AI-agent interface.



# Manufacturing Scenario

The simulated factory contains four machines:

| Machine | Process   |  Capacity | Setup Time |
| ------- | --------- | --------: | ---------: |
| M1      | Dyeing    | 100 kg/hr |     2.0 hr |
| M2      | Printing  |  80 kg/hr |     1.5 hr |
| M3      | Finishing | 120 kg/hr |     1.0 hr |
| M4      | Packing   | 150 kg/hr |     0.5 hr |

Three product types are modeled with different production routes:

```text
P1 → M1 → M2 → M3 → M4
P2 → M1 → M2 → M3 → M4
P3 → M1 → M3 → M4
```

The current benchmark contains:

* 20 production orders
* 4 machines
* 3 product types
* Production quantities
* Release times
* Due dates
* Order priorities
* Sequence-dependent setup times
* Gas and diesel energy estimates

The dataset is **synthetic** and does not represent proprietary factory data.



# Scheduling Approach

## 1. EDD Baseline

The first scheduler provides a reference point for evaluating the optimization model.

It uses a discrete-event scheduling heuristic based primarily on:

* Earliest Due Date (EDD)
* Order priority as a tie-breaker
* Machine availability
* Production routing
* Stage precedence
* Sequence-dependent setup time

The baseline is intentionally simple. Its purpose is not to represent the best possible scheduling strategy, but to provide a reproducible benchmark.



## 2. CP-SAT Optimization

The second scheduler uses **Google OR-Tools CP-SAT** to model production as a constraint optimization problem.

The model includes:

### Hard constraints

* Order release times
* Production routing
* Operation precedence
* One operation at a time per machine
* Machine-product compatibility
* Machine sequencing
* Sequence-dependent setup time

### Decision variables

The model determines:

* Operation start times
* Machine sequencing
* Order completion times
* Order tardiness

### Objective

The current V1 objective is:

```text
Minimize:

    Weighted Tardiness + Total Setup Time
```

where:

```text
Weighted Tardiness =
Σ (priority × tardiness)
```

and:

```text
Tardiness =
max(0, completion_time − due_time)
```

For V1, both objective components use equal weight:

```text
WT = 1
WS = 1
```

This weighting is intentionally simple for the first optimization experiment. Future versions can introduce different business scenarios such as delivery-focused, cost-focused, or balanced scheduling.



# Results

The CP-SAT model was evaluated against the EDD baseline.

| Metric             | Baseline | Optimizer V1 |
| ------------------ | -------: | -----------: |
| Raw tardiness      | 35.26 hr | **12.16 hr** |
| Weighted tardiness |   141.54 |    **41.81** |
| Total setup time   | 71.00 hr | **59.00 hr** |
| Late orders        |   7 / 20 |   **6 / 20** |
| Combined objective |   212.54 |   **100.83** |

### Improvement

Compared with the baseline:

* **65.5% reduction** in raw tardiness
* **70.5% reduction** in weighted tardiness
* **16.9% reduction** in setup time
* Late orders reduced from **7 to 6**
* Combined objective improved by approximately **52.6%**

The reduction in total tardiness is more significant than the reduction in the number of late orders. In other words, the optimizer did not eliminate every late order, but it substantially reduced **how late** the remaining late orders were.



# Important Solver Note

The CP-SAT solver returned a:

```text
FEASIBLE
```

solution within the configured time limit.

This means the schedule satisfies the modeled constraints, but the solver did **not prove that the solution is globally optimal** within the time limit.

Therefore, this project deliberately does **not** claim that the reported schedule is the mathematical optimum.

This distinction is important when evaluating constraint optimization results.



# What the Baseline Revealed

One of the more interesting observations came from analyzing the baseline schedule.

Some orders with relatively generous deadline windows still became late because a significant portion of their available time was consumed **waiting for the first production stage**.

In particular, the M1 dyeing stage acts as an important capacity bottleneck in this synthetic factory.

This demonstrated an important limitation of a simple EDD-based strategy:

> Choosing the order with the earliest deadline does not necessarily produce the best overall schedule when machine queues, routing, setup times, and downstream dependencies interact.

The optimization model can consider these constraints jointly instead of making each scheduling decision locally.



# Data Notes

The dataset went through an initial feasibility check during development.

The **first draft** of the synthetic dataset contained several orders whose minimum processing time exceeded their available release-to-due window even when machine contention was ignored.

That made those orders structurally impossible to complete on time, which would have made the benchmark less useful for evaluating a scheduling strategy.

The order deadlines and quantities were therefore adjusted during dataset refinement so that the final benchmark represents a **difficult but meaningful scheduling problem**, rather than a collection of orders that are inherently impossible to meet.

The current benchmark is the dataset used to generate the results reported above.

The data is synthetic and the adjustments are part of the benchmark-design process, not historical factory data.



# Why Setup Time Matters

Setup time represents the time required to change a machine from processing one product type to another.

For example, switching a machine from P1 to P2 may require a fixed setup period before the next order can begin.

Therefore, the reported setup time is **schedule-dependent**. It is not an unavoidable fixed amount of factory downtime.

A schedule that groups compatible products together can reduce the number of changeovers, while a schedule that frequently switches product types can increase setup time.

The optimizer therefore has to balance:

```text
Meeting deadlines
        +
Reducing weighted tardiness
        +
Reducing unnecessary changeovers
```



# Project Architecture

### Current — Part 1

```text
              Manufacturing Data
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
      Orders    Processing     Machines
                  Times
        └────────────┼────────────┘
                     ▼
             Baseline Scheduler
                     │
                     ▼
              CP-SAT Optimizer
                     │
                     ▼
             Optimized Schedule
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
      Tardiness    Setup     Utilization
       Analysis    Analysis    Analysis
```



# Planned Agentic AI Layer

The optimization engine is intentionally separated from the future AI interface.

The next stage will introduce an **LLM-based decision-support agent** capable of selecting analytical tools based on a planner's request.

The planned architecture is:

```text
                    User / Planner
                         │
                         ▼
                  AI Supervisor Agent
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   optimize_schedule  analyze_       analyze_
                     bottleneck()     energy()
          │              │              │
          ▼              ▼              ▼
       CP-SAT          Pandas        Energy Model
          └──────────────┼──────────────┘
                         ▼
                 Structured Results
                         │
                         ▼
                  Agent Explanation
```

For example, a planner could ask:

> "Create a production schedule for the current orders and identify the main bottleneck."

The agent will be able to:

1. Interpret the request
2. Select the appropriate tools
3. Run the scheduling optimizer
4. Analyze the resulting machine utilization
5. Combine the results
6. Explain the production decision in natural language

The LLM will not generate or invent the production schedule itself. The deterministic optimization engine will remain responsible for the scheduling computation.



# Technologies

* Python
* Pandas
* Google OR-Tools
* CP-SAT Constraint Programming
* Discrete-event scheduling
* Production scheduling
* Constraint optimization
* CSV-based data modeling

Planned Part 2 technologies:

* LLM / tool calling
* AI agents
* FastAPI
* Manufacturing analytics
* Natural-language decision support



# Project Structure

```text
manufacturing-operations-intelligence/
│
├── data/
│   ├── orders.csv
│   ├── processing_times.csv
│   └── machines.csv
│
├── user_baseline/
│   └── baseline_schedule.csv
│
├── optimizer_v1.py
├── optimizer_v1_schedule.csv
├── optimizer_v1_results.csv
├── requirements.txt
├── .gitignore
└── README.md
```



# Running Locally

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd manufacturing-operations-intelligence
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the environment

Windows PowerShell:

```powershell
.venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Run the optimizer

```bash
python optimizer_v1.py
```

The program generates:

```text
optimizer_v1_schedule.csv
optimizer_v1_results.csv
```

and reports:

* Order completion times
* Tardiness
* Weighted tardiness
* Late orders
* Setup time
* Machine utilization



# Limitations

This is a prototype scheduling and decision-support system built using a synthetic manufacturing environment.

Current limitations include:

* Synthetic production data
* Simplified machine behavior
* Simplified energy modeling
* No live factory data
* No real-time shop-floor events
* No machine breakdown modeling
* No inventory or raw-material availability constraints
* No workforce constraints
* No maintenance scheduling
* Current CP-SAT runs are time-limited
* The current version does not prove global optimality
* The AI-agent layer is not yet implemented

These limitations are intentional for the current prototype and provide directions for future development.



# Future Work

### Part 2 — AI Agent

* Add LLM-based tool calling
* Allow natural-language production requests
* Add bottleneck-analysis tools
* Add scenario-analysis tools
* Connect the agent to the CP-SAT optimizer

### Part 3 — Energy-Aware Planning

* Incorporate energy availability and cost into scheduling
* Compare gas and diesel operating scenarios
* Evaluate production plans under energy constraints
* Introduce multi-objective scheduling

### Part 4 — Decision-Support Interface

* Build a FastAPI backend
* Add an interactive dashboard
* Visualize schedules and machine utilization
* Display optimization decisions and explanations
* Add scenario comparison

### Longer-Term Direction

The longer-term goal is to explore how **optimization, analytics, and agentic AI** can work together in manufacturing decision-support systems.

---



**Current release: Part 1 — Manufacturing Scheduling & Optimization Engine**
