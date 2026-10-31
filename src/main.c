#include "scheduler.h"
#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int number(const char *s, SimTime *out) {
    if(!*s)return 0;
    for(const char *p=s;*p;++p)if(!isdigit((unsigned char)*p))return 0;
    errno=0;char *end;intmax_t value=strtoimax(s,&end,10);
    if(errno || *end || value<0 || value>INT64_MAX)return 0;
    *out=(SimTime)value;return 1;
}
static int policy(const char *s, SimPolicy *out) {
    const char *names[]={"fcfs","sjf","srtf","rr"};
    for(int i=0;i<4;++i)if(!strcmp(s,names[i])){*out=(SimPolicy)i;return 1;}
    return 0;
}
/* Read bounded text without treating an input NUL as an early string end. */
static int read_line(FILE *file, char *line, size_t capacity, size_t *length) {
    size_t used=0;int ch;
    while((ch=fgetc(file))!=EOF) {
        if(ch=='\0')return -1;
        if(used+1>=capacity)return -2;
        line[used++]=(char)ch;
        if(ch=='\n')break;
    }
    if(ferror(file))return -3;
    line[used]='\0';
    *length=used;
    return used?1:0;
}
int main(int argc,char **argv) {
    Task *tasks=NULL;size_t count=0,capacity=0;FILE *file=NULL;SimResult result={0};
    const char *failure=NULL;char error[160]={0};SimOptions options={SIM_FCFS,2,0};
    if(argc<2){failure="usage: scheduler_c workload.csv [--policy fcfs|sjf|srtf|rr] [--quantum N] [--context-switch N]";goto finish;}
    for(int i=2;i<argc;i+=2) {
        if(i+1==argc){failure="missing option value";goto finish;}
        if(!strcmp(argv[i],"--policy")) {if(!policy(argv[i+1],&options.policy)){failure="invalid policy";goto finish;}}
        else if(!strcmp(argv[i],"--quantum")) {if(!number(argv[i+1],&options.quantum)){failure="invalid quantum";goto finish;}}
        else if(!strcmp(argv[i],"--context-switch")) {if(!number(argv[i+1],&options.context_cost)){failure="invalid context cost";goto finish;}}
        else {failure="unknown option";goto finish;}
    }
    file=fopen(argv[1],"r");if(!file){failure="cannot read workload";goto finish;}
    char line[512];int line_status;size_t len;
    while((line_status=read_line(file,line,sizeof(line),&len))>0) {
        if(len==sizeof(line)-1 && line[len-1]!='\n'){failure="input line too long";goto finish;}
        while(len && (line[len-1]=='\r' || line[len-1]=='\n'))line[--len]='\0';
        if(!len || line[0]=='#' || !strcmp(line,"id,arrival,burst"))continue;
        char *a=strchr(line,',');if(!a){failure="expected id,arrival,burst";goto finish;}
        char *b=strchr(a+1,',');if(!b || strchr(b+1,',')){failure="expected three CSV fields";goto finish;}
        *a++='\0';*b++='\0';Task t={0};
        if(!line[0] || strlen(line)>=sizeof(t.id)){failure="invalid ID length";goto finish;}
        for(char *p=line;*p;++p)if(!isalnum((unsigned char)*p) && *p!='_' && *p!='-'){failure="invalid ID character";goto finish;}
        strcpy(t.id,line);
        if(!number(a,&t.arrival) || !number(b,&t.burst)){failure="invalid workload number";goto finish;}
        if(count==capacity) {
            size_t cap=capacity?capacity*2:16;
            if(cap<capacity || cap>SIZE_MAX/sizeof(*tasks)){failure="workload too large";goto finish;}
            Task *fresh=realloc(tasks,cap*sizeof(*tasks));if(!fresh){failure="allocation failure";goto finish;}
            tasks=fresh;capacity=cap;
        }
        tasks[count++]=t;
    }
    if(line_status<0){failure=line_status==-1?"input contains NUL byte":line_status==-2?"input line too long":"workload read error";goto finish;}
    if(!sim_run(tasks,count,options,&result,error,sizeof(error))){failure=error;goto finish;}
    puts("Gantt (half-open intervals)");
    for(size_t i=0;i<result.segment_count;++i) {
        SimSegment s=result.segments[i];const char *label=s.task==SIZE_MAX?"IDLE":s.task==SIZE_MAX-1?"SWITCH":tasks[s.task].id;
        printf("[%"PRId64",%"PRId64") %s\n",s.start,s.end,label);
    }
    puts("id,arrival,burst,start,completion,waiting,turnaround,response");long double waiting=0,turnaround=0;
    for(size_t i=0;i<count;++i) {
        TaskMetrics m=result.metrics[i];
        printf("%s,%"PRId64",%"PRId64",%"PRId64",%"PRId64",%"PRId64",%"PRId64",%"PRId64"\n",tasks[i].id,tasks[i].arrival,tasks[i].burst,m.first_start,m.completion,m.waiting,m.turnaround,m.response);
        waiting+=m.waiting;turnaround+=m.turnaround;
    }
    printf("makespan=%"PRId64" busy=%"PRId64" idle=%"PRId64" switching=%"PRId64" context_switches=%zu average_waiting=%.3Lf average_turnaround=%.3Lf\n",result.makespan,result.busy,result.idle,result.switching,result.context_switches,count?waiting/count:0,count?turnaround/count:0);
finish:
    if(file)fclose(file);free(tasks);sim_result_free(&result);
    if(failure){fprintf(stderr,"error: %s\n",failure);return 1;}return 0;
}
