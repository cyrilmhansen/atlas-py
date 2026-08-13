#define _GNU_SOURCE
#include "quickdraw_region_ops.h"
#include <inttypes.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { WIDTH = 512, HEIGHT = 256, SAMPLES = 31, APPLY_BATCH = 100 };
typedef enum { SPARSE, FRAGMENTED } CaseKind;
typedef struct { uint64_t production, conversion, apply_b0, apply_b1; size_t b0_bytes, b1_bytes; uint64_t b0_hash, b1_hash; } Components;

static uint64_t now_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC_RAW, &t); return (uint64_t)t.tv_sec*1000000000ULL + (uint64_t)t.tv_nsec; }
static int cmp_u64(const void*a,const void*b){uint64_t x=*(const uint64_t*)a,y=*(const uint64_t*)b;return(x>y)-(x<y);}
static uint64_t hash_bytes(const uint8_t*p,size_t n){uint64_t h=UINT64_C(1469598103934665603);for(size_t i=0;i<n;i++)h=(h^p[i])*UINT64_C(1099511628211);return h;}
static QROMask new_mask(void){QROMask m={WIDTH,HEIGHT,(WIDTH+7)/8,NULL};m.bits=calloc((size_t)m.stride*HEIGHT,1);if(!m.bits)exit(2);return m;}
static void set_rect(QROMask*m,int top,int left,int bottom,int right){for(int y=top;y<bottom;y++)for(int x=left;x<right;x++)qro_set(m,y,x,1);}
static void make_shape(QROMask*m,CaseKind kind){memset(m->bits,0,(size_t)m->stride*m->height);if(kind==SPARSE){for(int i=0;i<18;i++){int y=3+(i*13)%(HEIGHT-5),x=5+(i*47)%(WIDTH-20);set_rect(m,y,x,y+2,x+15+(i%4)*9);}}else{for(int y=0;y<HEIGHT;y++)for(int x=0;x<WIDTH;x++)if(((x/3)+(y/3))&1)qro_set(m,y,x,1);}}
static void free_mask(QROMask*m){free(m->bits);memset(m,0,sizeof*m);}

static int canonical_from_b1(const QROB1*r,QROMask*out){memset(out->bits,0,(size_t)out->stride*out->height);for(int y=0;y<r->height;y++)for(size_t i=r->offsets[y];i<r->offsets[y+1];i++)for(int x=r->runs[i].left;x<r->runs[i].right;x++)qro_set(out,y,x,1);return 0;}
static int measure_components(CaseKind kind,Components*out){QROMask a=new_mask(),b=new_mask();make_shape(&a,kind);make_shape(&b,kind);QROB0 ba={0},bb={0},result={0};uint64_t p[SAMPLES],c[SAMPLES],a0[SAMPLES],a1[SAMPLES];
    qro_b0_build(&a,&ba,NULL);qro_b0_build(&b,&bb,NULL);qro_b0_op(&ba,&bb,QRO_INTERSECT,&result,NULL);qro_b0_free(&ba);qro_b0_free(&bb);qro_b0_free(&result);
    for(int i=0;i<SAMPLES;i++){uint64_t t=now_ns();qro_b0_build(&a,&ba,NULL);qro_b0_build(&b,&bb,NULL);qro_b0_op(&ba,&bb,QRO_INTERSECT,&result,NULL);p[i]=now_ns()-t;qro_b0_free(&ba);qro_b0_free(&bb);qro_b0_free(&result);}
    qro_b0_build(&a,&ba,NULL);qro_b0_build(&b,&bb,NULL);qro_b0_op(&ba,&bb,QRO_INTERSECT,&result,NULL);QROMask view={result.width,result.height,result.stride,result.bits};QROB1 converted={0};QROStats cs={0};
    qro_b1_build(&view,&converted,&cs);QROMask logical=new_mask(),canonical=new_mask();memcpy(logical.bits,result.bits,(size_t)result.stride*result.height);canonical_from_b1(&converted,&canonical);if(memcmp(logical.bits,canonical.bits,(size_t)logical.stride*logical.height)!=0){fprintf(stderr,"conversion identity failure\n");return -1;}
    qro_b1_free(&converted); qro_b1_build(&view,&converted,&cs);
    for(int i=0;i<SAMPLES;i++){uint64_t t=now_ns();qro_b1_build(&view,&converted,&cs);c[i]=now_ns()-t;qro_b1_free(&converted);}qro_b1_build(&view,&converted,&cs);
    size_t bytes=(size_t)((WIDTH+7)/8)*HEIGHT;uint8_t*srcd=malloc(bytes),*dst0=malloc(bytes),*dst1=malloc(bytes);memset(srcd,0xa5,bytes);memset(dst0,0x5a,bytes);memcpy(dst1,dst0,bytes);QDBitmap src={srcd,bytes,(WIDTH+7)/8,{0,0,HEIGHT,WIDTH}},d0={dst0,bytes,(WIDTH+7)/8,{0,0,HEIGHT,WIDTH}},d1={dst1,bytes,(WIDTH+7)/8,{0,0,HEIGHT,WIDTH}};QDRect rect={0,0,HEIGHT,WIDTH};
    qro_b0_apply(&result,&src,rect,&d0,rect);qro_b1_apply(&converted,&src,rect,&d1,rect);if(memcmp(dst0,dst1,bytes)!=0){fprintf(stderr,"application identity failure\n");return -1;}
    qro_b0_apply(&result,&src,rect,&d0,rect);qro_b1_apply(&converted,&src,rect,&d1,rect);
    for(int i=0;i<SAMPLES;i++){memcpy(dst0,dst1,bytes);uint64_t t=now_ns();for(int n=0;n<APPLY_BATCH;n++)qro_b0_apply(&result,&src,rect,&d0,rect);a0[i]=now_ns()-t;memcpy(dst1,dst0,bytes);t=now_ns();for(int n=0;n<APPLY_BATCH;n++)qro_b1_apply(&converted,&src,rect,&d1,rect);a1[i]=now_ns()-t;}
    qsort(p,SAMPLES,sizeof*p,cmp_u64);qsort(c,SAMPLES,sizeof*c,cmp_u64);qsort(a0,SAMPLES,sizeof*a0,cmp_u64);qsort(a1,SAMPLES,sizeof*a1,cmp_u64);out->production=p[SAMPLES/2];out->conversion=c[SAMPLES/2];out->apply_b0=a0[SAMPLES/2]/APPLY_BATCH;out->apply_b1=a1[SAMPLES/2]/APPLY_BATCH;out->b0_bytes=sizeof result+(size_t)result.stride*result.height;out->b1_bytes=cs.storage_bytes;out->b0_hash=hash_bytes(result.bits,(size_t)result.stride*result.height);out->b1_hash=hash_bytes(canonical.bits,(size_t)canonical.stride*canonical.height);
    qro_b1_free(&converted);qro_b0_free(&ba);qro_b0_free(&bb);qro_b0_free(&result);free_mask(&a);free_mask(&b);free_mask(&logical);free_mask(&canonical);free(srcd);free(dst0);free(dst1);return 0;}

static uint64_t lifecycle_once(CaseKind kind,int n,int convert){QROMask a=new_mask(),b=new_mask();make_shape(&a,kind);make_shape(&b,kind);QROB0 ba={0},bb={0},result={0};QROB1 runs={0};uint64_t t=now_ns();qro_b0_build(&a,&ba,NULL);qro_b0_build(&b,&bb,NULL);qro_b0_op(&ba,&bb,QRO_INTERSECT,&result,NULL);if(convert){QROMask view={result.width,result.height,result.stride,result.bits};qro_b1_build(&view,&runs,NULL);}size_t bytes=(size_t)((WIDTH+7)/8)*HEIGHT;uint8_t*srcd=malloc(bytes),*dst=malloc(bytes);memset(srcd,0xa5,bytes);memset(dst,0x5a,bytes);QDBitmap src={srcd,bytes,(WIDTH+7)/8,{0,0,HEIGHT,WIDTH}},dest={dst,bytes,(WIDTH+7)/8,{0,0,HEIGHT,WIDTH}};QDRect rect={0,0,HEIGHT,WIDTH};for(int i=0;i<n;i++){if(convert)qro_b1_apply(&runs,&src,rect,&dest,rect);else qro_b0_apply(&result,&src,rect,&dest,rect);}uint64_t elapsed=now_ns()-t;qro_b1_free(&runs);qro_b0_free(&ba);qro_b0_free(&bb);qro_b0_free(&result);free_mask(&a);free_mask(&b);free(srcd);free(dst);return elapsed;}
static uint64_t lifecycle(CaseKind kind,int n,int convert){uint64_t v[SAMPLES];lifecycle_once(kind,n,convert);for(int i=0;i<SAMPLES;i++)v[i]=lifecycle_once(kind,n,convert);qsort(v,SAMPLES,sizeof*v,cmp_u64);return v[SAMPLES/2];}

static void print_case(const char*name,CaseKind kind){Components x;if(measure_components(kind,&x))exit(1);uint64_t threshold=0;double lhs=(double)x.conversion,save=(double)x.apply_b0-(double)x.apply_b1;if(save>0)threshold=(uint64_t)(lhs/save)+1;int n0=threshold>1?(int)threshold-1:1,n1=threshold? (int)threshold:1;uint64_t w0=lifecycle(kind,n0,0),c0=lifecycle(kind,n0,1),w1=lifecycle(kind,n1,0),c1=lifecycle(kind,n1,1);printf("{\"workload\":\"%s\",\"operation\":\"intersect\",\"source_representation\":\"B0_bitmap_result\",\"target_representation\":\"B1_runs_converted\",\"timer\":\"CLOCK_MONOTONIC_RAW\",\"samples\":%d,\"apply_batch\":%d,\"production_median_ns\":%"PRIu64",\"conversion_median_ns\":%"PRIu64",\"apply_b0_median_ns_per_use\":%"PRIu64",\"apply_b1_median_ns_per_use\":%"PRIu64",\"b0_storage_bytes\":%zu,\"b1_storage_bytes\":%zu,\"b0_canonical_hash\":\"%016"PRIx64"\",\"b1_canonical_hash\":\"%016"PRIx64"\",\"logical_identity\":%s,\"calculated_break_even\":%"PRIu64",\"end_to_end\":{\"N_minus_1\":{\"N\":%d,\"without_ns\":%"PRIu64",\"with_ns\":%"PRIu64"},\"N\":{\"N\":%d,\"without_ns\":%"PRIu64",\"with_ns\":%"PRIu64"}}}\n",name,SAMPLES,APPLY_BATCH,x.production,x.conversion,x.apply_b0,x.apply_b1,x.b0_bytes,x.b1_bytes,x.b0_hash,x.b1_hash,x.b0_hash==x.b1_hash?"true":"false",threshold,n0,w0,c0,n1,w1,c1);}
int main(void){cpu_set_t set;CPU_ZERO(&set);CPU_SET(0,&set);sched_setaffinity(0,sizeof set,&set);printf("{\"program\":\"semantic_core_v1_native_conversion.c + quickdraw_region_ops.c\",\"compiler\":\"native C harness\",\"cases\":[");print_case("sparse_sparse_intersection",SPARSE);putchar(',');print_case("fragmented_fragmented_intersection",FRAGMENTED);printf("]}\n");return 0;}
