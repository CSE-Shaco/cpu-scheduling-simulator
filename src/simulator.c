#include "scheduler.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* One driver owns task state and CPU time. Ready queues hold indices,
 * not task copies, so remaining service has a single source of truth. */
typedef struct { SimTime remaining; } TaskState;
typedef struct { size_t *items, count; } ReadyQueue;
typedef struct { SimTime now; size_t previous; } CPU;
typedef struct Driver Driver;
typedef size_t (*SelectTask)(const Driver *driver);
typedef struct { SelectTask select; } Scheduler;
struct Driver {
    const Task *tasks;
    size_t count, next, completed, segment_capacity;
    size_t *arrivals;
    TaskState *states;
    ReadyQueue ready;
    CPU cpu;
    Scheduler scheduler;
    SimOptions options;
    SimResult *result;
};

static int add_time(SimTime a, SimTime b, SimTime *out) {
    if (b > INT64_MAX - a) return 0;
    *out = a + b;
    return 1;
}
static size_t select_queue(const Driver *d) { (void)d; return 0; }
static int shorter(const Driver *d, size_t a, size_t b) {
    if (d->states[a].remaining != d->states[b].remaining)
        return d->states[a].remaining < d->states[b].remaining;
    if (d->tasks[a].arrival != d->tasks[b].arrival)
        return d->tasks[a].arrival < d->tasks[b].arrival;
    return a < b;
}
static size_t select_shortest(const Driver *d) {
    size_t best = 0;
    for (size_t i = 1; i < d->ready.count; ++i)
        if (shorter(d, d->ready.items[i], d->ready.items[best])) best = i;
    return best;
}
static void admit(Driver *d) {
    while (d->next < d->count && d->tasks[d->arrivals[d->next]].arrival <= d->cpu.now)
        d->ready.items[d->ready.count++] = d->arrivals[d->next++];
}
static int advance(Driver *d, SimTime duration, size_t task) {
    SimTime end;
    if (!add_time(d->cpu.now, duration, &end)) return 0;
    if (!duration) return 1;
    SimResult *r = d->result;
    if (r->segment_count && r->segments[r->segment_count - 1].task == task) {
        r->segments[r->segment_count - 1].end = end;
    } else {
        if (r->segment_count == d->segment_capacity) {
            size_t cap = d->segment_capacity ? d->segment_capacity * 2 : 16;
            if (cap < d->segment_capacity || cap > SIZE_MAX / sizeof(SimSegment)) return 0;
            SimSegment *fresh = realloc(r->segments, cap * sizeof(*fresh));
            if (!fresh) return 0;
            r->segments = fresh;
            d->segment_capacity = cap;
        }
        r->segments[r->segment_count++] = (SimSegment){d->cpu.now, end, task};
    }
    d->cpu.now = end;
    return 1;
}
void sim_result_free(SimResult *r) {
    if (r) { free(r->metrics); free(r->segments); memset(r, 0, sizeof(*r)); }
}
int sim_run(const Task *tasks, size_t count, SimOptions options, SimResult *out,
            char *error, size_t error_size) {
    const char *failure = NULL;
    Driver d = {0};
    if (!out) { if (error && error_size) snprintf(error,error_size,"result is null"); return 0; }
    memset(out,0,sizeof(*out));
    if (error && error_size) error[0]='\0';
    if ((count && !tasks) || options.policy < SIM_FCFS || options.policy > SIM_RR ||
        options.quantum <= 0 || options.context_cost < 0) { failure="invalid options/input"; goto finish; }
    for (size_t i=0;i<count;++i) {
        if (!memchr(tasks[i].id,'\0',sizeof(tasks[i].id)) || !tasks[i].id[0] ||
            !strcmp(tasks[i].id,"IDLE") || !strcmp(tasks[i].id,"SWITCH") ||
            tasks[i].arrival < 0 || tasks[i].burst <= 0) { failure="invalid process";goto finish; }
        for (size_t j=0;j<i;++j) if (!strcmp(tasks[i].id,tasks[j].id)) { failure="duplicate process ID";goto finish; }
    }
    if (count > SIZE_MAX/sizeof(TaskState) || count > SIZE_MAX/sizeof(size_t) || count > SIZE_MAX/sizeof(TaskMetrics)) {
        failure="workload too large";goto finish;
    }
    d.tasks=tasks;d.count=count;d.options=options;d.result=out;d.cpu.previous=count;
    d.scheduler.select=(options.policy==SIM_FCFS || options.policy==SIM_RR)?select_queue:select_shortest;
    if (!count) return 1;
    d.states=calloc(count,sizeof(*d.states));d.arrivals=malloc(count*sizeof(*d.arrivals));
    d.ready.items=malloc(count*sizeof(*d.ready.items));out->metrics=calloc(count,sizeof(*out->metrics));out->count=count;
    if (!d.states || !d.arrivals || !d.ready.items || !out->metrics) {failure="allocation failure";goto finish;}
    /* Stable insertion sort avoids global qsort comparator state. */
    for(size_t i=0;i<count;++i) {
        d.states[i].remaining=tasks[i].burst;out->metrics[i].first_start=-1;
        size_t j=i;
        while(j && tasks[d.arrivals[j-1]].arrival>tasks[i].arrival) {d.arrivals[j]=d.arrivals[j-1];--j;}
        d.arrivals[j]=i;
    }
    while(d.completed<count) {
        admit(&d);
        if(!d.ready.count) {
            SimTime gap=tasks[d.arrivals[d.next]].arrival-d.cpu.now;
            if(!advance(&d,gap,SIZE_MAX)) {failure="time overflow or allocation failure";goto finish;}
            out->idle+=gap;d.cpu.previous=count;admit(&d);
        }
        size_t pos=d.scheduler.select(&d), selected=d.ready.items[pos];
        if(d.cpu.previous!=count && d.cpu.previous!=selected) {
            if(!advance(&d,options.context_cost,SIZE_MAX-1)) {failure="time overflow or allocation failure";goto finish;}
            out->switching+=options.context_cost;++out->context_switches;admit(&d);
            pos=d.scheduler.select(&d);selected=d.ready.items[pos];
        }
        memmove(d.ready.items+pos,d.ready.items+pos+1,(d.ready.count-pos-1)*sizeof(*d.ready.items));--d.ready.count;
        TaskMetrics *m=&out->metrics[selected];
        if(m->first_start<0)m->first_start=d.cpu.now;
        SimTime duration=d.states[selected].remaining;
        if(options.policy==SIM_RR && duration>options.quantum)duration=options.quantum;
        if(options.policy==SIM_SRTF && d.next<count) {
            SimTime until=tasks[d.arrivals[d.next]].arrival-d.cpu.now;
            if(until<duration)duration=until;
        }
        if(!advance(&d,duration,selected)) {failure="time overflow or allocation failure";goto finish;}
        d.states[selected].remaining-=duration;out->busy+=duration;admit(&d);
        if(!d.states[selected].remaining) {
            m->completion=d.cpu.now;m->turnaround=m->completion-tasks[selected].arrival;
            m->waiting=m->turnaround-tasks[selected].burst;m->response=m->first_start-tasks[selected].arrival;
            ++d.completed;
        } else d.ready.items[d.ready.count++]=selected;
        d.cpu.previous=selected;
    }
    out->makespan=d.cpu.now;
finish:
    free(d.states);free(d.arrivals);free(d.ready.items);
    if(failure) {sim_result_free(out);if(error && error_size)snprintf(error,error_size,"%s",failure);return 0;}
    return 1;
}
