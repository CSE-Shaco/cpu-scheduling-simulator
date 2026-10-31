# Simulation Semantics

Time is signed 64-bit integer abstract units, starting at zero. Input order breaks ties for equal arrivals; IDs have no ordering role. Every accepted process has a unique ID, arrival ≥ 0 and burst > 0. Addition that would exceed the supported time range fails explicitly.

## Selection

- FCFS takes the oldest admitted ready process and runs to completion.
- SJF chooses smallest burst among ready processes and runs to completion.
- SRTF chooses smallest remaining service at arrival/completion boundaries. Equal remaining service chooses earliest arrival, then original input order; an equally short new process therefore does not preempt an earlier arrival.
- RR takes the queue head and runs for at most a positive quantum. Arrivals at or before slice expiry are appended before the expired process is requeued. A sole process can renew its quantum without a process-to-process context switch.

All arrivals at a timestamp are admitted in stable input order. For nonpreemptive policies and RR, arrivals during a service interval are batched at its endpoint in arrival order, which preserves the queue/selection semantics without intermediate ticks.

## Context switching

A context switch occurs when dispatch changes from one previously running process to a different process with no intervening CPU idle interval. This includes completion followed by another ready process and preemptive changes. Initial dispatch and dispatch after idle incur no switch. No overhead is charged after final completion. The count includes transitions with configured cost zero.

When a change is selected, time advances by `context_cost` and a `SWITCH` interval is emitted if cost > 0. All arrivals through the end of that interval are admitted. The policy then chooses the final target again; the target can change from the provisional choice. That single switch is charged once. There is no execution or burst consumption during switching.

Example: SRTF processes A=(arrival 0, burst 10), B=(1,4), C=(2,1), cost=3. A runs 0–1; switch 1–4; C arriving during the switch is selected at 4 and completes at 5; switch 5–8; B completes at 12; switch 12–15; A completes at 24. Three switches total nine units.

These rules are this simulator's explicit model, rather than a universal claim about every operating system's dispatch implementation.

## Metrics

For each process:

- turnaround = completion − arrival
- waiting = turnaround − burst (includes dispatch overhead while ready)
- response = first CPU service − arrival

Global accounting: makespan = service + idle + switching, from time zero to final completion. Initial idle is included. Empty workload returns empty metrics/timeline and zeros. Consecutive same-label timeline segments are merged; RR slice renewals can be invisible in the Gantt output. `context_switches` preserves the number of process transitions even when their duration is zero.
