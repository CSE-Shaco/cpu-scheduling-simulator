# Scheduling Case Studies: Policy Goals and Finite Postponement

This report compares four implemented algorithms on explicit synthetic CPU-only workloads. It asks which assumptions and objectives make a policy useful, and which metrics can hide an undesirable outcome. It does not select a universally best scheduler or measure host execution speed.

The [recorded study](../benchmarks/results/policy-study-2026-10-31/README.md) contains **116 executed configurations**: 84 policy/quantum/context-cost comparisons and 32 controlled finite-prefix cases. All simulated time is in abstract integer units. Values below come from the retained simulator outputs, with exact values in the [summary CSV](../benchmarks/results/policy-study-2026-10-31/analysis/summary.csv).

## Model and Workload Assumptions

- One CPU, one CPU burst per process, no I/O blocking, priorities, aging, multicore affinity, or real timer interrupts.
- The simulator receives the full finite arrival list so its engine can jump to the next event. **Selection uses only admitted ready processes**; future jobs are not eligible before arrival.
- SJF and SRTF know the burst/remaining service of ready processes exactly. A production scheduler generally does not receive this ideal input.
- Initial dispatch and dispatch after idle have no switching charge. A process-to-process transition costs the configured constant; arrivals during it can change the final dispatch target. [Exact semantics](semantics.md).
- Cost 1 means one simulated unit relative to these burst lengths and quanta. It is not a measured microsecond context-switch cost.

The workloads are independent, explicit CSV constructions, not real traces or textbook exercise inputs. `bursty.csv` has bursts of **arrivals**; it does not model alternating CPU and I/O bursts.

OSTEP's [CPU scheduling chapter](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-sched.pdf) motivates stating workload assumptions, separating first-response from turnaround objectives, and considering quantum/overhead tradeoffs. The examples and measurements in this report are our own simulator experiments; no book code or figures are included.

## Four Algorithms, Seven Base Configurations

| Algorithm | Ready-process selection | When execution can end before completion | Objective or tradeoff examined |
| --- | --- | --- | --- |
| FCFS | Arrival/queue order; stable input-order ties | No policy preemption | Simple ordering and low preemption overhead; convoy risk |
| SJF | Smallest ready burst | No policy preemption | Short-job mean delay under ideal burst knowledge; long-job postponement |
| SRTF | Smallest ready remaining service | A new arrival can cause re-selection | Short-job latency through preemption; additional transitions and long-job postponement |
| Round Robin | Queue head | Positive quantum expires | Recurring service and first response; quantum/dispatch overhead |

FCFS and RR share queue-selection machinery but have different run-duration rules. SJF and SRTF share shortest-ready selection but differ in arrival-boundary preemption. These are distinct behaviors, not renamed versions of one policy. For `A=(0,8), B=(1,4), C=(2,2)`, zero switch cost, and RR quantum 2, the executed hand-check gives:

| Algorithm | Completion A | Completion B | Completion C | Mean waiting |
| --- | ---: | ---: | ---: | ---: |
| FCFS | 8 | 12 | 14 | 5.667 |
| SJF | 8 | 14 | 10 | 5.000 |
| SRTF | 14 | 7 | 4 | 2.667 |
| RR, q=2 | 14 | 10 | 6 | 4.333 |

The base matrix uses FCFS, SJF and SRTF once, plus RR at q=1,2,4,8: **seven configurations of four algorithms**, not seven algorithms. All receive the same workload per comparison. The non-RR command's quantum field stays 2 and has no scheduling effect.

## Case 1 — Convoy and Short-Job Delay

`convoy.csv` puts LONG=(0,24) first, followed by four ready short jobs with total service 8. At zero switch cost:

| Policy | Mean waiting | Mean response | Makespan |
| --- | ---: | ---: | ---: |
| FCFS | 21.4 | 21.4 | 32 |
| SJF | 3.4 | 3.4 | 32 |
| SRTF | 3.4 | 3.4 | 32 |
| RR, q=2 | 6.0 | 3.6 | 32 |

Short-first selection greatly reduces the mean delay here, while RR starts jobs sooner through time slicing. FCFS lets LONG finish first but leaves the short jobs behind it. Every policy has the same total service and makespan; a lower mean delay is **not** a throughput gain in this case. SJF and SRTF coincide because every process arrives at zero, leaving no later arrival that needs preemption.

## Case 2 — Arrivals Make Preemption Relevant

`staggered.csv` begins with an 18-unit job, then admits shorter jobs at times 2, 4, 5, 9 and 13. At zero switch cost:

| Policy | Mean waiting | Mean response | Context switches |
| --- | ---: | ---: | ---: |
| FCFS | 16.167 | 16.167 | 5 |
| SJF | 12.833 | 12.833 | 5 |
| SRTF | 4.500 | 1.167 | 7 |
| RR, q=2 | 9.667 | 2.500 | 14 |

SJF cannot interrupt the first long burst, even after a short job arrives. SRTF can, and gains lower delay on these particular inputs. The transition counts show why that result should be reconsidered when switching has a cost. The experiment does not assume that future short bursts can be predicted before arrival.

## Case 3 — RR Quantum Trades First Response for Overhead

For `mixed-bounded.csv`, all policies have makespan 45 with zero switch cost. Changing RR's quantum produces the following recorded results:

| Quantum | Mean response, cost 0 | Mean response, cost 1 | Switches, cost 1 | Makespan, cost 1 | Productive utilization, cost 1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1.875 | 6.000 | 43 | 88 | 51.14% |
| 2 | 4.250 | 8.125 | 22 | 67 | 67.16% |
| 4 | 7.750 | 11.500 | 12 | 57 | 78.95% |
| 8 | 12.625 | 16.500 | 9 | 54 | 83.33% |

Small quanta improve first response on this input, but the cost-1 model spends more time dispatching. Larger quanta improve the productive fraction while delaying the first service of some jobs. Productive utilization is `busy / makespan`, with initial idle and switching included in makespan; it is not an operating-system CPU-utilization counter.

Positive switching cost can also change which arrivals are present at a dispatch. The switch count itself can change: in this workload RR q=1 has 42 transitions at cost zero and 43 at cost one. A positive-cost result therefore cannot always be predicted by adding overhead to an unchanged zero-cost timeline; compare complete executions.

![RR quantum and switching sensitivity](../benchmarks/results/policy-study-2026-10-31/analysis/round-robin-tradeoff.svg)

## Case 4 — Finite Postponement and What “Starvation” Means

Two controlled workload families each use LONG=(arrival 0, burst 64), RR q=2, switch cost 0, and H in 16,32,64,128. LONG is first in the CSV. Every finite simulation runs to completion; the report separately observes its timeline during **[0,H)**.

- **Ready short stream:** H one-unit jobs arrive at 0,1,...,H−1. A short job is already eligible at time zero.
- **Late short stream:** H one-unit jobs arrive at 1,2,...,H. LONG can begin before the stream arrives.

For each process that is still unfinished, the *longest ready/no-service gap before H* is the largest interval with no service between its arrival and `min(H, completion)`. Time after completion is excluded. “Done by H” includes completion exactly at H. Full waiting/completion values remain full-run metrics, not prefix estimates.

At H=64, the executed LONG observations are:

| Family | Policy | First start | Service in [0,64) | Longest ready gap in prefix | Full waiting | Full completion |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Ready stream | FCFS | 0 | 64 | 0 | 0 | 64 |
| Ready stream | SJF | 64 | 0 | 64 | 64 | 128 |
| Ready stream | SRTF | 64 | 0 | 64 | 64 | 128 |
| Ready stream | RR, q=2 | 0 | 14 | 13 | 64 | 128 |
| Late stream | FCFS | 0 | 64 | 0 | 0 | 64 |
| Late stream | SJF | 0 | 64 | 0 | 0 | 64 |
| Late stream | SRTF | 0 | 1 | 63 | 64 | 128 |
| Late stream | RR, q=2 | 0 | 14 | 12 | 64 | 128 |

For the ready family, SJF/SRTF postpone LONG's first service to H as the short stream lengthens. For the late family, SJF has already committed to LONG nonpreemptively, while SRTF gives it one unit and then postpones further progress. In that SRTF case, LONG has **response time zero** despite a 63-unit no-service gap before H=64. First-response time alone therefore misses a later stall. RR makes repeated prefix progress here, even when its full completion and waiting match SJF/SRTF; those full-run metrics alone also miss how service was distributed.

![Finite-prefix progress and postponement](../benchmarks/results/policy-study-2026-10-31/analysis/finite-postponement.svg)

### Observation Versus Theoretical Continuation

The finite CSVs do not prove infinite starvation. All finish, and every prefix family/policy has makespan H+64 and no idle at cost zero.

Our conceptual continuation argument is conditional: if a one-unit short job kept arriving at every integer time indefinitely, shortest-ready selection would always find a shorter eligible job than the untouched 64-unit LONG in the ready family. In the late family, SRTF would repeatedly prefer those jobs over LONG's remaining 63 units after its first unit. This describes possible indefinite postponement under an idealized unbounded stream and time model, not a run supported by this finite-input, bounded-integer C program.

OSTEP's [MLFQ chapter](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-sched-mlfq.pdf) discusses starvation under sustained higher-priority work and priority boosting in that separate scheduler model. This simulator implements neither MLFQ nor aging/boosting. No claim about those algorithms is inferred from our four-policy measurements.

## Decision Criteria Instead of a Universal Ranking

| Goal and assumptions | What these cases suggest investigating | What must still be checked |
| --- | --- | --- |
| Low average waiting with credible burst estimates | SJF/SRTF as candidates | Estimate quality, long-job delay, and preemption overhead |
| Fast first service plus continued progress | RR and quantum sensitivity | Tail latency, queue growth, switching cost, and progress after first response |
| Simple arrival ordering or few transitions | FCFS | Convoys and the delay imposed on later short jobs |
| Sustained arrivals with a long-job progress requirement | Explicit progress/tail metrics and an appropriate policy guarantee | Finite prefixes are insufficient to prove a guarantee; mechanisms beyond these four may be needed |

Real operating-system or application choices require workload evidence, service objectives, and actual platform costs. This project has no automatic policy selector. It provides controlled comparisons and explicit semantics so a choice can be argued under stated assumptions.

## Reproduction and Validation Limits

See [experiment commands](../benchmarks/README.md). The recorded 116 configurations preserve stdout/stderr, workload CSV contents and hashes, source/binary hashes, compiler identity and exact invocation records. All cases pass timeline, service, metric and switching-accounting checks. **74 zero-cost cases** also match the independent tick oracle. Nonzero-cost cases use accounting plus hand-derived checks and the C assertion suite; an independent nonzero-cost oracle is not claimed.

No elapsed host timings are collected, no speedup is reported, and repeated runs of this deterministic model are not treated as statistical evidence. The cases illustrate specific mechanisms; they are not production workload traces or proof of a policy's behavior for all possible inputs.
