#define _GNU_SOURCE
#include "../../quickdraw_region_ops.h"
#include <sched.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

enum { W = 512, H = 256, SAMPLES = 31, BATCH = 50 };
typedef enum { BANDS, CHECKER } Shape;

static uint64_t now_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC_RAW, &t); return (uint64_t)t.tv_sec * 1000000000ULL + (uint64_t)t.tv_nsec; }
static int cmp_u64(const void *a, const void *b) { uint64_t x=*(const uint64_t *)a,y=*(const uint64_t *)b; return (x>y)-(x<y); }
static QROMask mask_new(void) { QROMask m={W,H,(W+7)/8,NULL}; m.bits=calloc((size_t)m.stride*H,1); if(!m.bits) exit(2); return m; }
static void mask_free(QROMask *m) { free(m->bits); memset(m,0,sizeof *m); }
static void fill(QROMask *m, Shape s) {
    for(int y=0;y<H;y++) for(int x=0;x<W;x++) {
        int on = s==BANDS ? ((y/8)&1)==0 : ((x^y)&1)==0;
        qro_set(m,y,x,on);
    }
}
static uint64_t canonical_hash_b1(const QROB1 *r) {
    uint64_t h=UINT64_C(1469598103934665603); uint8_t bit;
    for(int y=0;y<r->height;y++) for(int x=0;x<r->width;x++) {
        bit=0; for(size_t i=r->offsets[y];i<r->offsets[y+1];i++) if(x>=r->runs[i].left&&x<r->runs[i].right){bit=1;break;}
        h=(h^(uint8_t)(bit+(uint8_t)(x==0)))*UINT64_C(1099511628211);
    }
    return h;
}
static uint64_t canonical_hash_mask(const QROMask *m) {
    uint64_t h=UINT64_C(1469598103934665603); for(int y=0;y<m->height;y++) for(int x=0;x<m->width;x++) { uint8_t bit=(uint8_t)qro_get(m,y,x); h=(h^(uint8_t)(bit+(uint8_t)(x==0)))*UINT64_C(1099511628211); } return h;
}
static uint64_t run_count_mask(const QROMask *m) { uint64_t n=0; for(int y=0;y<H;y++){int in=0;for(int x=0;x<W;x++){int v=qro_get(m,y,x);if(v&&!in)n++;in=v;}}return n; }
static void one(const char *name, Shape shape) {
    QROMask a=mask_new(), full=mask_new(); fill(&a,shape); for(int y=0;y<H;y++)for(int x=0;x<W;x++)qro_set(&full,y,x,1);
    QROB0 ba={0},bf={0},result={0}; QROB1 b1={0}; QROB2 b2={0}; QROStats st={0},st2={0};
    if(qro_b0_build(&a,&ba,NULL)||qro_b0_build(&full,&bf,NULL)||qro_b0_op(&ba,&bf,QRO_INTERSECT,&result,NULL))exit(3);
    QROMask view={result.width,result.height,result.stride,result.bits}; if(qro_b1_build(&view,&b1,&st)||qro_b2_build(&view,&b2,&st2))exit(4);
    uint64_t c[SAMPLES],r0[SAMPLES],r1[SAMPLES],r2[SAMPLES];
    for(int i=0;i<SAMPLES;i++){uint64_t t=now_ns();QROB1 tmp={0};qro_b1_build(&view,&tmp,NULL);c[i]=now_ns()-t;qro_b1_free(&tmp);}
    size_t bytes=(size_t)((W+7)/8)*H; uint8_t *srcd=calloc(bytes,1),*dstd=calloc(bytes,1); QDBitmap src={srcd,bytes,(W+7)/8,{0,0,H,W}},dst={dstd,bytes,(W+7)/8,{0,0,H,W}}; QDRect rr={0,0,H,W};
    for(int i=0;i<SAMPLES;i++){uint64_t t=now_ns();for(int z=0;z<BATCH;z++)qro_b0_apply(&result,&src,rr,&dst,rr);r0[i]=(now_ns()-t)/BATCH;t=now_ns();for(int z=0;z<BATCH;z++)qro_b1_apply(&b1,&src,rr,&dst,rr);r1[i]=(now_ns()-t)/BATCH;t=now_ns();for(int z=0;z<BATCH;z++)qro_b2_apply(&b2,&src,rr,&dst,rr);r2[i]=(now_ns()-t)/BATCH;}
    qsort(c,SAMPLES,sizeof*c,cmp_u64);qsort(r0,SAMPLES,sizeof*r0,cmp_u64);qsort(r1,SAMPLES,sizeof*r1,cmp_u64);qsort(r2,SAMPLES,sizeof*r2,cmp_u64);
    uint64_t saving=r0[SAMPLES/2]>r1[SAMPLES/2]?r0[SAMPLES/2]-r1[SAMPLES/2]:0; uint64_t threshold=saving?(c[SAMPLES/2]/saving)+1:0;
    uint64_t h0=canonical_hash_mask((const QROMask*)&result),h1=canonical_hash_b1(&b1);
    printf("{\"shape\":\"%s\",\"area\":%d,\"density\":0.5,\"input_runs\":%" PRIu64 ",\"b1_storage_bytes\":%zu,\"b2_storage_bytes\":%zu,\"conversion_b1_median_ns\":%" PRIu64 ",\"apply_b0_ns\":%" PRIu64 ",\"apply_b1_ns\":%" PRIu64 ",\"apply_b2_ns\":%" PRIu64 ",\"b1_point_estimate_N\":%" PRIu64 ",\"b0_canonical_hash\":\"%016" PRIx64 "\",\"b1_canonical_hash\":\"%016" PRIx64 "\",\"logical_identity\":%s}\n",name,W*H/2,run_count_mask(&a),st.storage_bytes,st2.storage_bytes,c[SAMPLES/2],r0[SAMPLES/2],r1[SAMPLES/2],r2[SAMPLES/2],threshold,h0,h1,h0==h1?"true":"false");
    free(srcd);free(dstd);qro_b1_free(&b1);qro_b2_free(&b2);qro_b0_free(&ba);qro_b0_free(&bf);qro_b0_free(&result);mask_free(&a);mask_free(&full);
}
int main(void){cpu_set_t set;CPU_ZERO(&set);CPU_SET(0,&set);sched_setaffinity(0,sizeof set,&set);puts("[");one("horizontal_bands",BANDS);puts(",");one("checker",CHECKER);puts("]");return 0;}
