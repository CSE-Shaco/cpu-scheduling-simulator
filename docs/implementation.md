# Implementation Decisions

## State and Ownership

The public C API borrows an immutable array of `Task` records. The driver allocates one `TaskState` array for remaining burst time. Ready queues contain indices into that array, not task copies, so each task has one mutable execution state.

The caller supplies a new/cleared `SimResult`. On success it owns the metrics and timeline buffers and releases them with `sim_result_free()`. On failure the engine clears partial allocations and writes a diagnostic. Callers must not pass an already allocated result without freeing it first.

## One Clock and Event Boundaries

`CPU.now` is the only simulation clock. `Driver` coordinates admission, selection, service and accounting. FCFS/SJF advance to completion; RR advances to the lesser of remaining service and quantum; SRTF can advance to the next arrival to reconsider selection. An empty ready queue jumps directly to the next arrival.

The driver admits arrivals before selection and admits arrivals at a quantum boundary before requeueing the expired task. A process-to-process transition can emit a `SWITCH` interval; arrivals during that interval participate in the final selection without a second charge. [Exact semantics](semantics.md).

## Scheduling and Queue Representation

A scheduler function pointer selects an entry in the ready-index array. FCFS/RR select the head. SJF/SRTF scan for the shortest remaining service with arrival/input-order ties. The representation favors inspectable behavior; selection and queue removal are linear and arrival ordering uses stable insertion sort.

## Validation and Output

Signed 64-bit time addition rejects overflow. IDs must be unique and input/options valid. The engine returns service/idle/switch totals, per-process metrics and half-open timeline intervals; adjacent intervals with the same label are merged.

C API assertions use hand-derived schedules, conservation/metric identities and invalid-input cases. Independent tick-oracle tests advance time one unit at a time for zero-cost dispatch. [Executed results and coverage limits](validation.md).
