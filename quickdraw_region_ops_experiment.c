#define _POSIX_C_SOURCE 200809L
#include "quickdraw_region_ops.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef enum { EMPTY, FULL, RECT, SPARSE, DENSE, FRAGMENTED, STABLE, UNSTABLE, RANDOM } Shape;
typedef union { QROB0 b0; QROB1 b1; QROB2 b2; } Obj;
typedef struct { const char *name; int (*build)(const QROMask*,Obj*,QROStats*); void(*free)(Obj*); int(*op)(const Obj*,const Obj*,QROp,Obj*,QROStats*); int(*apply)(const Obj*,const QDBitmap*,QDRect,QDBitmap*,QDRect); } Variant;
static uint64_t rng=UINT64_C(0x243f6a8885a308d3),sink;
static uint32_t rnd(void){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return(uint32_t)(rng>>16);}
static QROMask mask_new(int w,int h){QROMask m={w,h,(w+7)/8,NULL};m.bits=calloc((size_t)m.stride*h,1);if(!m.bits)exit(2);return m;}
static void mask_free(QROMask*m){free(m->bits);*m=(QROMask){0};}
static void rect(QROMask*m,int t,int l,int b,int r){if(t<0)t=0;if(l<0)l=0;if(b>m->height)b=m->height;if(r>m->width)r=m->width;for(int y=t;y<b;y++)for(int x=l;x<r;x++)qro_set(m,y,x,1);}
static void shape(QROMask*m,Shape s,uint64_t seed){memset(m->bits,0,(size_t)m->stride*m->height);uint64_t old=rng;rng=seed;switch(s){case EMPTY:break;case FULL:rect(m,0,0,m->height,m->width);break;case RECT:rect(m,m->height/5,m->width/7,m->height-m->height/6,m->width-m->width/9);break;case SPARSE:{int yd=m->height>5?m->height-5:1,xd=m->width>20?m->width-20:1;for(int i=0;i<18;i++){int y=3+(i*13)%yd,x=5+(i*47)%xd;rect(m,y,x,y+2,x+15+(i%4)*9);}}break;case DENSE:for(int y=2;y<m->height-2;y++){int l=3+(y*7)%29,r=m->width-4-(y*5)%37;rect(m,y,l,y+1,r);if(y%11<4)for(int x=m->width/2-4;x<m->width/2+5;x++)qro_set(m,y,x,0);}break;case FRAGMENTED:for(int y=0;y<m->height;y++)for(int x=0;x<m->width;x++)if(((x/3)+(y/3))&1)qro_set(m,y,x,1);break;case STABLE:for(int y=0;y<m->height;y++){if(y%7<5)rect(m,y,32,y+1,m->width-32);else rect(m,y,64,y+1,m->width-64);}break;case UNSTABLE:for(int y=0;y<m->height;y++){int n=1+(y%17),xd=m->width>8?m->width-8:1;for(int i=0;i<n;i++){int x=(i*37+y*19)%xd;rect(m,y,x,y+1,x+2+(i%5));}}break;default:for(int i=0;i<70;i++){int x=rnd()%(unsigned)m->width,y=rnd()%(unsigned)m->height;rect(m,y,x,y+1+(rnd()%9),x+1+(rnd()%45));}break;}rng=old;}
static void fill(uint8_t*p,size_t n,uint64_t seed){uint64_t old=rng;rng=seed;for(size_t i=0;i<n;i++)p[i]=(uint8_t)rnd();rng=old;}
static int build0(const QROMask*m,Obj*o,QROStats*s){return qro_b0_build(m,&o->b0,s);}static int build1(const QROMask*m,Obj*o,QROStats*s){return qro_b1_build(m,&o->b1,s);}static int build2(const QROMask*m,Obj*o,QROStats*s){return qro_b2_build(m,&o->b2,s);}
static void free0(Obj*o){qro_b0_free(&o->b0);}static void free1(Obj*o){qro_b1_free(&o->b1);}static void free2(Obj*o){qro_b2_free(&o->b2);}
static int op0(const Obj*a,const Obj*b,QROp p,Obj*c,QROStats*s){return qro_b0_op(&a->b0,&b->b0,p,&c->b0,s);}static int op1(const Obj*a,const Obj*b,QROp p,Obj*c,QROStats*s){return qro_b1_op(&a->b1,&b->b1,p,&c->b1,s);}static int op2(const Obj*a,const Obj*b,QROp p,Obj*c,QROStats*s){return qro_b2_op(&a->b2,&b->b2,p,&c->b2,s);}
static int ap0(const Obj*o,const QDBitmap*s,QDRect sr,QDBitmap*d,QDRect dr){return qro_b0_apply(&o->b0,s,sr,d,dr);}static int ap1(const Obj*o,const QDBitmap*s,QDRect sr,QDBitmap*d,QDRect dr){return qro_b1_apply(&o->b1,s,sr,d,dr);}static int ap2(const Obj*o,const QDBitmap*s,QDRect sr,QDBitmap*d,QDRect dr){return qro_b2_apply(&o->b2,s,sr,d,dr);}
static Variant vars[]={{"B0_bitmap",build0,free0,op0,ap0},{"B1_runs",build1,free1,op1,ap1},{"B2_transitions",build2,free2,op2,ap2}};
static QROMask oracle_mask(const QROMask*a,const QROMask*b,QROp p){QROMask c=mask_new(a->width,a->height);for(int y=0;y<a->height;y++)for(int x=0;x<a->width;x++){int av=qro_get(a,y,x),bv=qro_get(b,y,x),v=p==QRO_INTERSECT?av&bv:p==QRO_UNION?av|bv:p==QRO_DIFF?av&!bv:av^bv;qro_set(&c,y,x,v);}return c;}
static void obj_mask(const Obj*o,int vi,QROMask*m){memset(m->bits,0,(size_t)m->stride*m->height);if(vi==0){memcpy(m->bits,o->b0.bits,(size_t)m->stride*m->height);return;}if(vi==1){for(int y=0;y<o->b1.height;y++)for(size_t i=o->b1.offsets[y];i<o->b1.offsets[y+1];i++)for(int x=o->b1.runs[i].left;x<o->b1.runs[i].right;x++)qro_set(m,y,x,1);return;}uint8_t*scan=calloc((size_t)(m->width+7)/8,1);size_t i=0;for(int y=0;y<m->height;y++){while(i<o->b2.event_count&&o->b2.events[i].y==y){int in=0,l=0;for(int k=0;k<o->b2.events[i].count;k++){int x=o->b2.events[i].x[k];if(!in)l=x;else for(int z=l;z<x;z++)scan[z/8]^=(uint8_t)(0x80>>(z&7));in=!in;}i++;}memcpy(m->bits+(size_t)y*m->stride,scan,(size_t)m->stride);}free(scan);}
static uint64_t hash_bytes(const uint8_t*p,size_t n){uint64_t h=UINT64_C(1469598103934665603);for(size_t i=0;i<n;i++)h=(h^p[i])*UINT64_C(1099511628211);return h;}
static int equal_mask(const QROMask*a,const QROMask*b){return a->width==b->width&&a->height==b->height&&!memcmp(a->bits,b->bits,(size_t)a->stride*a->height);}
static uint64_t now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC_RAW,&t);return(uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
static int cmp64(const void*a,const void*b){uint64_t x=*(const uint64_t*)a,y=*(const uint64_t*)b;return(x>y)-(x<y);}
static const char*opname(QROp p){return p==QRO_INTERSECT?"intersect":p==QRO_UNION?"union":p==QRO_DIFF?"diff":"xor";}
static void print_stats(const QROStats*s){printf("{\"area\":%"PRIu64",\"bbox_area\":%"PRIu64",\"active_lines\":%"PRIu64",\"runs\":%"PRIu64",\"vertical_events\":%"PRIu64",\"transitions\":%"PRIu64",\"storage_bytes\":%zu,\"temporary_bytes\":%zu,\"allocations\":%"PRIu64"}",s->area,s->bbox_area,s->active_lines,s->runs,s->vertical_events,s->transitions,s->storage_bytes,s->temporary_bytes,s->allocations);}

static int test_case(int id,Shape sa,Shape sb,QROp p){int w=1+(id*17)%129,h=1+(id*11)%73;QROMask a=mask_new(w,h),b=mask_new(w,h),want=mask_new(w,h);shape(&a,sa,UINT64_C(0x9e3779b97f4a7c15)^id);shape(&b,sb,UINT64_C(0xd1b54a32d192ed03)^id);QROMask ow=oracle_mask(&a,&b,p);for(size_t vi=0;vi<3;vi++){Obj oa={0},ob={0},oc={0};QROStats s={0};if(vars[vi].build(&a,&oa,NULL)||vars[vi].build(&b,&ob,NULL)||vars[vi].op(&oa,&ob,p,&oc,&s)){return 0;}obj_mask(&oc,(int)vi,&want);if(!equal_mask(&ow,&want)){fprintf(stderr,"mismatch case=%d variant=%s op=%s size=%dx%d\n",id,vars[vi].name,opname(p),w,h);return 0;}vars[vi].free(&oa);vars[vi].free(&ob);vars[vi].free(&oc);}mask_free(&a);mask_free(&b);mask_free(&ow);mask_free(&want);return 1;}
static int tests(void){int id=0;Shape pairs[][2]={{RECT,RECT},{SPARSE,SPARSE},{SPARSE,DENSE},{DENSE,DENSE},{FRAGMENTED,FRAGMENTED},{STABLE,STABLE},{UNSTABLE,UNSTABLE},{EMPTY,FULL},{FULL,EMPTY},{RANDOM,RANDOM}};for(size_t q=0;q<sizeof pairs/sizeof*pairs;q++)for(int op=0;op<4;op++)for(int n=0;n<20;n++)if(!test_case(++id,pairs[q][0],pairs[q][1],(QROp)op))return 1;rng=UINT64_C(0x452821e638d01377);for(int n=0;n<3000;n++){Shape a=(Shape)(rnd()%9),b=(Shape)(rnd()%9);for(int op=0;op<4;op++)if(!test_case(++id,a,b,(QROp)op))return 1;}printf("tests: %d deterministic pairs x operations, 3 variants, bit-identical\n",id);return 0;}

typedef struct{const char*name;Shape a,b;int reuse;} Bench;
static int benchmarks(void){
    static const Bench bs[]={{"rect_rect",RECT,RECT,20},{"sparse_sparse",SPARSE,SPARSE,100},{"sparse_dense",SPARSE,DENSE,100},{"dense_dense",DENSE,DENSE,50},{"fragmented_fragmented",FRAGMENTED,FRAGMENTED,20},{"vertically_stable",STABLE,STABLE,100},{"vertically_unstable",UNSTABLE,UNSTABLE,20},{"empty_full",EMPTY,FULL,100}};
    enum{S=9};
    printf("{\"timer\":\"CLOCK_MONOTONIC_RAW\",\"samples\":%d,\"cases\":[",S);
    for(size_t bi=0;bi<sizeof bs/sizeof*bs;bi++){
        int w=512,h=256; QROMask a=mask_new(w,h),b=mask_new(w,h);
        shape(&a,bs[bi].a,UINT64_C(0xabc00000)+bi); shape(&b,bs[bi].b,UINT64_C(0xdef00000)+bi);
        QROStats as,bsx; qro_stats_mask(&a,&as); qro_stats_mask(&b,&bsx);
        if(bi)putchar(',');
        printf("{\"name\":\"%s\",\"reuse\":%d,\"input_a\":",bs[bi].name,bs[bi].reuse);
        print_stats(&as); printf(",\"input_b\":"); print_stats(&bsx); printf(",\"operations\":[");
        for(int op=0;op<4;op++){
            if(op)putchar(',');
            printf("{\"op\":\"%s\",\"variants\":[",opname((QROp)op));
            uint64_t expected=0;
            for(size_t vi=0;vi<3;vi++){
                if(vi)putchar(',');
                Obj oa={0},ob={0},oc={0}; QROStats a0={0},b0={0},co={0}; uint64_t bt[7],ot[7],at[7];
                for(int k=0;k<7;k++){uint64_t t=now();vars[vi].build(&a,&oa,&a0);vars[vi].free(&oa);vars[vi].build(&b,&ob,&b0);vars[vi].free(&ob);bt[k]=now()-t;}
                vars[vi].build(&a,&oa,&a0); vars[vi].build(&b,&ob,&b0);
                for(int k=0;k<7;k++){uint64_t t=now();vars[vi].op(&oa,&ob,(QROp)op,&oc,&co);ot[k]=now()-t;vars[vi].free(&oc);}
                vars[vi].op(&oa,&ob,(QROp)op,&oc,&co);
                QROMask result=mask_new(w,h); obj_mask(&oc,(int)vi,&result); QROStats result_stats; qro_stats_mask(&result,&result_stats); result_stats.storage_bytes=co.storage_bytes; result_stats.temporary_bytes=co.temporary_bytes; result_stats.allocations=co.allocations;
                size_t n=(size_t)((w+7)/8)*h; uint8_t*srcd=malloc(n),*dstd=malloc(n),*work=malloc(n); fill(srcd,n,bi+17); fill(dstd,n,bi+31); QDBitmap src={srcd,n,(w+7)/8,{0,0,h,w}},dst={work,n,(w+7)/8,{0,0,h,w}}; QDRect rr={0,0,h,w};
                vars[vi].apply(&oc,&src,rr,&dst,rr);
                for(int k=0;k<7;k++){memcpy(work,dstd,n);uint64_t t=now();for(int z=0;z<bs[bi].reuse;z++)vars[vi].apply(&oc,&src,rr,&dst,rr);at[k]=now()-t;}
                uint64_t checksum=hash_bytes(work,n); if(!vi)expected=checksum; else if(checksum!=expected){fprintf(stderr,"benchmark application mismatch %s %s\n",bs[bi].name,vars[vi].name);return 1;}
                qsort(bt,7,sizeof*bt,cmp64);qsort(ot,7,sizeof*ot,cmp64);qsort(at,7,sizeof*at,cmp64);
                printf("{\"name\":\"%s\",\"build_pair_median_ns\":%"PRIu64",\"op_median_ns\":%"PRIu64",\"op_p95_ns\":%"PRIu64",\"apply_batch_median_ns\":%"PRIu64",\"apply_ns_per_use\":%.3f,\"build_once_apply_once_ns\":%.3f,\"build_once_apply_many_ns\":%.3f,\"dynamic_clip_one_cycle_ns\":%.3f,\"result\":",vars[vi].name,bt[3],ot[3],ot[6],at[3],(double)at[3]/bs[bi].reuse,(double)bt[3]+ot[3]+(double)at[3]/bs[bi].reuse,(double)bt[3]+ot[3]+at[3],(double)bt[3]+ot[3]+(double)at[3]/bs[bi].reuse); print_stats(&result_stats); printf(",\"checksum\":\"%016"PRIx64"\"}",checksum);
                mask_free(&result); vars[vi].free(&oa);vars[vi].free(&ob);vars[vi].free(&oc);free(srcd);free(dstd);free(work);
            }
            printf("]}");
        }
        printf("]}"); mask_free(&a);mask_free(&b);
    }
    printf("],\"sink\":\"%016"PRIx64"\"}\n",sink); return 0;
}
int main(int argc,char**argv){if(argc==2&&!strcmp(argv[1],"--test"))return tests();if(argc==2&&!strcmp(argv[1],"--benchmark"))return benchmarks();fprintf(stderr,"usage: %s --test | --benchmark\n",argv[0]);return 2;}
