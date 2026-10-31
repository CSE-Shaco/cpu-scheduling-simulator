#ifndef PORTFOLIO_SCHEDULER_H
#define PORTFOLIO_SCHEDULER_H
#include <stddef.h>
#include <stdint.h>

typedef int64_t SimTime;
typedef enum { SIM_FCFS, SIM_SJF, SIM_SRTF, SIM_RR } SimPolicy;
typedef struct { char id[64]; SimTime arrival, burst; } Task;
typedef struct { SimPolicy policy; SimTime quantum, context_cost; } SimOptions;
typedef struct { SimTime first_start, completion, waiting, turnaround, response; } TaskMetrics;
/* task == SIZE_MAX denotes IDLE; SIZE_MAX-1 denotes SWITCH. */
typedef struct { SimTime start, end; size_t task; } SimSegment;
typedef struct {
    TaskMetrics *metrics;
    SimSegment *segments;
    size_t count, segment_count, context_switches;
    SimTime makespan, busy, idle, switching;
} SimResult;

/* out must be a new/cleared result. On failure it is cleared; error is diagnostic.
 * Input tasks are borrowed and never modified. Caller frees a successful result. */
int sim_run(const Task *tasks, size_t count, SimOptions options, SimResult *out,
            char *error, size_t error_size);
void sim_result_free(SimResult *result);
#endif
