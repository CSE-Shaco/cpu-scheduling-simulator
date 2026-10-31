#include "scheduler.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int checks=0;
#define CHECK(x) do {++checks;if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);}}while(0)
static void scenario(const Task *tasks,size_t n,SimOptions options,const SimTime *expected) {
    SimResult r={0};char error[128];CHECK(sim_run(tasks,n,options,&r,error,sizeof(error)));
    SimTime service=0,cursor=0;
    for(size_t i=0;i<n;++i) {
        CHECK(r.metrics[i].completion==expected[i]);CHECK(r.metrics[i].waiting>=0);
        CHECK(r.metrics[i].turnaround==r.metrics[i].waiting+tasks[i].burst);service+=tasks[i].burst;
    }
    for(size_t i=0;i<r.segment_count;++i){CHECK(r.segments[i].start==cursor);CHECK(r.segments[i].end>cursor);cursor=r.segments[i].end;}
    CHECK(service==r.busy);CHECK(cursor==r.makespan);CHECK(r.busy+r.idle+r.switching==r.makespan);
    sim_result_free(&r);
}
int main(void) {
    Task base[]={{"A",0,8},{"B",1,4},{"C",2,2}};
    scenario(base,3,(SimOptions){SIM_FCFS,2,0},(SimTime[]){8,12,14});
    scenario(base,3,(SimOptions){SIM_SJF,2,0},(SimTime[]){8,14,10});
    scenario(base,3,(SimOptions){SIM_SRTF,2,0},(SimTime[]){14,7,4});
    scenario(base,3,(SimOptions){SIM_RR,2,0},(SimTime[]){14,10,6});
    scenario((Task[]){{"A",0,4},{"B",2,1}},2,(SimOptions){SIM_RR,2,0},(SimTime[]){5,3});
    scenario((Task[]){{"A",0,4},{"B",2,2}},2,(SimOptions){SIM_SRTF,2,0},(SimTime[]){4,6});
    scenario((Task[]){{"Z",0,2},{"A",0,2}},2,(SimOptions){SIM_SJF,2,0},(SimTime[]){2,4});
    scenario((Task[]){{"A",0,10},{"B",1,4},{"C",2,1}},3,(SimOptions){SIM_SRTF,2,3},(SimTime[]){24,12,5});
    scenario((Task[]){{"A",5,2},{"B",10,1}},2,(SimOptions){SIM_FCFS,2,7},(SimTime[]){7,11});
    scenario((Task[]){{"A",0,7}},1,(SimOptions){SIM_RR,1,10},(SimTime[]){7});
    scenario((Task[]){{"A",1000000000000LL,1}},1,(SimOptions){SIM_FCFS,2,0},(SimTime[]){1000000000001LL});
    scenario(NULL,0,(SimOptions){SIM_FCFS,2,0},NULL);
    SimResult r={0};char error[128];
    CHECK(!sim_run((Task[]){{"A",0,0}},1,(SimOptions){SIM_FCFS,2,0},&r,error,sizeof(error)));
    CHECK(!sim_run((Task[]){{"A",-1,1}},1,(SimOptions){SIM_FCFS,2,0},&r,error,sizeof(error)));
    CHECK(!sim_run((Task[]){{"A",0,1},{"A",1,1}},2,(SimOptions){SIM_FCFS,2,0},&r,error,sizeof(error)));
    CHECK(!sim_run((Task[]){{"IDLE",0,1}},1,(SimOptions){SIM_FCFS,2,0},&r,error,sizeof(error)));
    CHECK(!sim_run(NULL,0,(SimOptions){SIM_RR,0,0},&r,error,sizeof(error)));
    CHECK(!sim_run(NULL,0,(SimOptions){SIM_RR,1,-1},&r,error,sizeof(error)));
    CHECK(!sim_run((Task[]){{"A",INT64_MAX,1}},1,(SimOptions){SIM_FCFS,2,0},&r,error,sizeof(error)));
    CHECK(!sim_run((Task[]){{"A",0,1},{"B",0,1}},2,(SimOptions){SIM_FCFS,1,INT64_MAX},&r,error,sizeof(error)));
    CHECK(r.metrics==NULL && r.segments==NULL);
    printf("PASS %d C checks (12 hand-derived/edge scenarios plus validation)\n",checks);
    return 0;
}
