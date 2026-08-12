#define _POSIX_C_SOURCE 200809L

#include "quickdraw_bitblt.h"

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>


#define GUARD_SIZE 32
#define BENCH_REPETITIONS 9

typedef struct {
    uint8_t *raw;
    uint8_t *data;
    size_t size;
} Arena;

typedef struct {
    const char *name;
    QDBitBlt function;
} Variant;

static Variant variants[] = {
    {"R0_bit_reference", qd_bitblt_r0},
    {"R1_generic_32", qd_bitblt_r1},
    {"R2_quickdraw_16", qd_bitblt_r2},
    {"R3_modern_64_memmove", qd_bitblt_r3},
};

static uint64_t rng_state = UINT64_C(0x6a09e667f3bcc909);
static volatile uint64_t benchmark_sink;


static uint32_t random_u32(void) {
    uint64_t x = rng_state;
    x ^= x << 13;
    x ^= x >> 7;
    x ^= x << 17;
    rng_state = x;
    return (uint32_t) (x >> 16);
}


static Arena make_arena(size_t size) {
    Arena arena = {0};
    arena.raw = (uint8_t *) malloc(size + 2 * GUARD_SIZE);
    if (!arena.raw) {
        fprintf(stderr, "allocation failed for %zu bytes\n", size);
        exit(2);
    }
    arena.data = arena.raw + GUARD_SIZE;
    arena.size = size;
    memset(arena.raw, 0xA5, GUARD_SIZE);
    memset(arena.data + size, 0x5A, GUARD_SIZE);
    return arena;
}


static void free_arena(Arena *arena) {
    free(arena->raw);
    *arena = (Arena) {0};
}


static int guards_ok(const Arena *arena) {
    for (size_t i = 0; i < GUARD_SIZE; ++i) {
        if (arena->raw[i] != 0xA5 || arena->data[arena->size + i] != 0x5A) {
            return 0;
        }
    }
    return 1;
}


static void fill_content(uint8_t *data, size_t size, int pattern, uint64_t seed) {
    uint64_t saved = rng_state;
    rng_state = seed;
    for (size_t i = 0; i < size; ++i) {
        switch (pattern) {
        case 0: data[i] = 0; break;
        case 1: data[i] = 0xFF; break;
        case 2: data[i] = (i & 1U) ? 0xAA : 0x55; break;
        default: data[i] = (uint8_t) random_u32(); break;
        }
    }
    rng_state = saved;
}


static QDBitmap bitmap_for(Arena *arena, int stride, int rows,
                           int bounds_left, int bounds_top) {
    return (QDBitmap) {
        arena->data,
        arena->size,
        stride,
        {bounds_top, bounds_left, bounds_top + rows, bounds_left + stride * 8},
    };
}


static int compare_or_report(const uint8_t *expected, const uint8_t *actual,
                             size_t size, uint64_t case_id, const char *variant) {
    if (memcmp(expected, actual, size) == 0) {
        return 1;
    }
    size_t offset = 0;
    while (offset < size && expected[offset] == actual[offset]) {
        ++offset;
    }
    fprintf(stderr,
            "case=%" PRIu64 " variant=%s mismatch byte=%zu expected=%02x actual=%02x\n",
            case_id, variant, offset, expected[offset], actual[offset]);
    return 0;
}


static int run_case(uint64_t case_id, int width, int height,
                    int sx, int sy, int dx, int dy, int src_padding,
                    int dst_padding, int overlap, int pattern,
                    int bounds_left, int bounds_top) {
    int src_bits = sx + width + 9;
    int dst_bits = dx + width + 9;
    int src_stride = (src_bits + 7) / 8 + src_padding;
    int dst_stride = (dst_bits + 7) / 8 + dst_padding;
    int src_rows = sy + height + 3;
    int dst_rows = dy + height + 3;
    if (overlap) {
        int bits = src_bits > dst_bits ? src_bits : dst_bits;
        int rows = src_rows > dst_rows ? src_rows : dst_rows;
        src_stride = dst_stride = (bits + 7) / 8 + (src_padding > dst_padding
                                                    ? src_padding : dst_padding);
        src_rows = dst_rows = rows;
    }
    size_t src_size = (size_t) src_stride * (size_t) src_rows;
    size_t dst_size = (size_t) dst_stride * (size_t) dst_rows;

    Arena initial_src = make_arena(src_size);
    Arena initial_dst = overlap ? (Arena) {0} : make_arena(dst_size);
    fill_content(initial_src.data, initial_src.size, pattern,
                 UINT64_C(0x123456789abcdef0) ^ case_id);
    if (!overlap) {
        fill_content(initial_dst.data, initial_dst.size, (pattern + 2) & 3,
                     UINT64_C(0xfedcba9876543210) ^ case_id);
    }

    Arena expected_src = make_arena(src_size);
    Arena expected_dst = overlap ? (Arena) {0} : make_arena(dst_size);
    memcpy(expected_src.data, initial_src.data, src_size);
    if (!overlap) {
        memcpy(expected_dst.data, initial_dst.data, dst_size);
    }
    QDBitmap expected_src_bitmap = bitmap_for(&expected_src, src_stride, src_rows,
                                              bounds_left, bounds_top);
    QDBitmap expected_dst_bitmap = overlap
        ? expected_src_bitmap
        : bitmap_for(&expected_dst, dst_stride, dst_rows, bounds_left - 3, bounds_top + 2);
    QDRect source_rect = {
        expected_src_bitmap.bounds.top + sy,
        expected_src_bitmap.bounds.left + sx,
        expected_src_bitmap.bounds.top + sy + height,
        expected_src_bitmap.bounds.left + sx + width,
    };
    QDRect destination_rect = {
        expected_dst_bitmap.bounds.top + dy,
        expected_dst_bitmap.bounds.left + dx,
        expected_dst_bitmap.bounds.top + dy + height,
        expected_dst_bitmap.bounds.left + dx + width,
    };
    if (qd_bitblt_r0(&expected_src_bitmap, source_rect,
                     &expected_dst_bitmap, destination_rect, NULL) != 0) {
        fprintf(stderr, "oracle rejected case=%" PRIu64 "\n", case_id);
        return 0;
    }

    for (size_t variant_index = 0;
         variant_index < sizeof variants / sizeof variants[0]; ++variant_index) {
        Arena actual_src = make_arena(src_size);
        Arena actual_dst = overlap ? (Arena) {0} : make_arena(dst_size);
        memcpy(actual_src.data, initial_src.data, src_size);
        if (!overlap) {
            memcpy(actual_dst.data, initial_dst.data, dst_size);
        }
        QDBitmap actual_src_bitmap = bitmap_for(&actual_src, src_stride, src_rows,
                                                bounds_left, bounds_top);
        QDBitmap actual_dst_bitmap = overlap
            ? actual_src_bitmap
            : bitmap_for(&actual_dst, dst_stride, dst_rows, bounds_left - 3, bounds_top + 2);
        QDStats stats = {0};
        int result = variants[variant_index].function(
            &actual_src_bitmap, source_rect, &actual_dst_bitmap, destination_rect, &stats);
        const uint8_t *wanted = overlap ? expected_src.data : expected_dst.data;
        const uint8_t *got = overlap ? actual_src.data : actual_dst.data;
        size_t compared_size = overlap ? src_size : dst_size;
        int okay = result == 0
            && compare_or_report(wanted, got, compared_size, case_id,
                                 variants[variant_index].name)
            && guards_ok(&actual_src)
            && (overlap || guards_ok(&actual_dst));
        if (!overlap) {
            okay = okay && compare_or_report(initial_src.data, actual_src.data,
                                              src_size, case_id, "source_modified");
        }
        free_arena(&actual_src);
        if (!overlap) {
            free_arena(&actual_dst);
        }
        if (!okay) {
            return 0;
        }
    }

    int okay = guards_ok(&initial_src) && guards_ok(&expected_src)
        && (overlap || (guards_ok(&initial_dst) && guards_ok(&expected_dst)));
    free_arena(&initial_src);
    free_arena(&expected_src);
    if (!overlap) {
        free_arena(&initial_dst);
        free_arena(&expected_dst);
    }
    return okay;
}


static int run_tests(void) {
    static const int widths[] = {1, 2, 7, 8, 15, 16, 17, 31, 32, 33,
                                 63, 64, 65, 127, 128, 129, 511, 1023};
    static const int alignments[] = {0, 1, 7, 8, 15, 16, 17, 31};
    uint64_t case_id = 0;
    for (size_t wi = 0; wi < sizeof widths / sizeof widths[0]; ++wi) {
        for (size_t si = 0; si < sizeof alignments / sizeof alignments[0]; ++si) {
            for (size_t di = 0; di < sizeof alignments / sizeof alignments[0]; ++di) {
                int pattern = (int) ((wi + si + di) & 3U);
                if (!run_case(++case_id, widths[wi], 1 + (int) (wi % 5),
                              alignments[si], 1, alignments[di], 2,
                              (int) (si % 4), (int) (di % 5), 0, pattern,
                              -11, 7)) {
                    return 1;
                }
            }
        }
    }

    static const int shifts[][2] = {
        {1, 0}, {7, 0}, {-1, 0}, {-7, 0}, {0, 1}, {0, -1}, {5, 1}, {-5, -1},
    };
    for (size_t wi = 0; wi < sizeof widths / sizeof widths[0]; ++wi) {
        for (size_t shift = 0; shift < sizeof shifts / sizeof shifts[0]; ++shift) {
            int sx = 40, sy = 5;
            int dx = sx + shifts[shift][0], dy = sy + shifts[shift][1];
            if (!run_case(++case_id, widths[wi], 3 + (int) (wi % 7),
                          sx, sy, dx, dy, 5, 7, 1, (int) (shift & 3U),
                          23, -9)) {
                return 1;
            }
        }
    }

    rng_state = UINT64_C(0xbb67ae8584caa73b);
    for (int random_case = 0; random_case < 5000; ++random_case) {
        int width = 1 + (int) (random_u32() % 513U);
        int height = 1 + (int) (random_u32() % 41U);
        int overlap = (random_u32() % 3U) == 0;
        int sx, sy, dx, dy;
        if (overlap) {
            sx = 48 + (int) (random_u32() % 16U);
            sy = 8 + (int) (random_u32() % 8U);
            int shift_x = (int) (random_u32() % 31U) - 15;
            int shift_y = (int) (random_u32() % 7U) - 3;
            dx = sx + shift_x;
            dy = sy + shift_y;
        } else {
            sx = (int) (random_u32() % 40U);
            sy = (int) (random_u32() % 5U);
            dx = (int) (random_u32() % 40U);
            dy = (int) (random_u32() % 5U);
        }
        if (!run_case(++case_id, width, height, sx, sy, dx, dy,
                      (int) (random_u32() % 12U), (int) (random_u32() % 12U),
                      overlap, (int) (random_u32() & 3U),
                      (int) (random_u32() % 31U) - 15,
                      (int) (random_u32() % 17U) - 8)) {
            return 1;
        }
    }

    {
        Arena arena = make_arena(16);
        fill_content(arena.data, arena.size, 3, UINT64_C(0x510e527fade682d1));
        uint8_t before[16];
        memcpy(before, arena.data, sizeof before);
        QDBitmap bitmap = {arena.data, arena.size, 8, {0, 0, 2, 64}};
        QDRect empty = {0, 1, 0, 17};
        QDRect source = {0, 1, 1, 17};
        QDRect wrong_size = {0, 1, 1, 16};
        for (size_t v = 0; v < sizeof variants / sizeof variants[0]; ++v) {
            if (variants[v].function(&bitmap, empty, &bitmap, empty, NULL) != 0
                    || memcmp(before, arena.data, sizeof before) != 0) {
                fprintf(stderr, "empty rectangle contract failed: %s\n", variants[v].name);
                return 1;
            }
            if (variants[v].function(&bitmap, source, &bitmap, wrong_size, NULL) != -1
                    || memcmp(before, arena.data, sizeof before) != 0) {
                fprintf(stderr, "unequal rectangle contract failed: %s\n", variants[v].name);
                return 1;
            }
        }
        free_arena(&arena);
        case_id += 2;
    }

    printf("tests: %" PRIu64 " deterministic cases, %zu variants, all bit-identical\n",
           case_id, sizeof variants / sizeof variants[0]);
    return 0;
}


typedef struct {
    int sx, sy, dx, dy, width, height;
} BenchOperation;

typedef struct {
    const char *name;
    int overlap;
    size_t operation_count;
    BenchOperation *operations;
    uint64_t useful_bits;
} Workload;


static Workload make_workload(const char *name, int overlap, size_t count) {
    Workload workload = {name, overlap, count, NULL, 0};
    workload.operations = (BenchOperation *) calloc(count, sizeof *workload.operations);
    if (!workload.operations) {
        fprintf(stderr, "workload allocation failed\n");
        exit(2);
    }
    return workload;
}


static void initialize_workloads(Workload workloads[4]) {
    static const int small_widths[] = {1, 7, 15, 16, 17, 31, 32, 33, 63, 64, 65};
    workloads[0] = make_workload("small_ui", 0, 4096);
    for (size_t i = 0; i < workloads[0].operation_count; ++i) {
        int width = small_widths[i % (sizeof small_widths / sizeof small_widths[0])];
        int height = 1 + (int) ((i * 7) % 24);
        workloads[0].operations[i] = (BenchOperation) {
            3 + (int) ((i * 13) % 1000), (int) ((i * 5) % 700),
            11 + (int) ((i * 17) % 1000), (int) ((i * 11) % 700),
            width, height,
        };
        workloads[0].useful_bits += (uint64_t) width * (uint64_t) height;
    }

    workloads[1] = make_workload("aligned_large", 0, 64);
    workloads[2] = make_workload("misaligned_large", 0, 64);
    workloads[3] = make_workload("scroll_overlap", 1, 128);
    for (size_t i = 0; i < 64; ++i) {
        workloads[1].operations[i] = (BenchOperation) {
            64 + (int) ((i % 4) * 8), 32 + (int) ((i % 3) * 256),
            128 + (int) ((i % 4) * 8), 48 + (int) ((i % 3) * 256),
            1024, 240,
        };
        workloads[1].useful_bits += UINT64_C(1024) * 240;
        workloads[2].operations[i] = (BenchOperation) {
            3 + (int) (i % 5), 32 + (int) ((i % 3) * 256),
            11 + (int) (i % 7), 48 + (int) ((i % 3) * 256),
            1023, 240,
        };
        workloads[2].useful_bits += UINT64_C(1023) * 240;
    }
    for (size_t i = 0; i < workloads[3].operation_count; ++i) {
        int downward = (i & 1U) == 0;
        workloads[3].operations[i] = (BenchOperation) {
            256, downward ? 200 : 208,
            263, downward ? 208 : 200,
            768, 160,
        };
        workloads[3].useful_bits += UINT64_C(768) * 160;
    }
}


static uint64_t checksum(const uint8_t *data, size_t size) {
    uint64_t hash = UINT64_C(1469598103934665603);
    for (size_t i = 0; i < size; ++i) {
        hash = (hash ^ data[i]) * UINT64_C(1099511628211);
    }
    return hash;
}


static uint64_t now_ns(void) {
    struct timespec time;
#ifdef CLOCK_MONOTONIC_RAW
    clock_gettime(CLOCK_MONOTONIC_RAW, &time);
#else
    clock_gettime(CLOCK_MONOTONIC, &time);
#endif
    return (uint64_t) time.tv_sec * UINT64_C(1000000000) + (uint64_t) time.tv_nsec;
}


static int execute_workload(const Workload *workload, QDBitBlt function,
                            QDBitmap *src, QDBitmap *dst, QDStats *stats) {
    for (size_t i = 0; i < workload->operation_count; ++i) {
        const BenchOperation *operation = &workload->operations[i];
        QDRect source = {operation->sy, operation->sx,
                         operation->sy + operation->height,
                         operation->sx + operation->width};
        QDRect destination = {operation->dy, operation->dx,
                              operation->dy + operation->height,
                              operation->dx + operation->width};
        QDBitmap *actual_dst = workload->overlap ? src : dst;
        if (function(src, source, actual_dst, destination, stats) != 0) {
            return -1;
        }
    }
    return 0;
}


static int compare_u64(const void *left, const void *right) {
    uint64_t a = *(const uint64_t *) left;
    uint64_t b = *(const uint64_t *) right;
    return (a > b) - (a < b);
}


static void print_stats(const QDStats *stats) {
    printf("{\"useful_bits\":%" PRIu64 ",\"bit_reads\":%" PRIu64
           ",\"bit_writes\":%" PRIu64 ",\"word_iterations\":%" PRIu64
           ",\"edge_masks\":%" PRIu64 ",\"reconstructed_words\":%" PRIu64
           ",\"aligned_words\":%" PRIu64 ",\"reverse_rows\":%" PRIu64
           ",\"reverse_words\":%" PRIu64 ",\"memmove_bytes\":%" PRIu64
           ",\"peak_temporary_bytes\":%zu}",
           stats->useful_bits, stats->bit_reads, stats->bit_writes,
           stats->word_iterations, stats->edge_masks, stats->reconstructed_words,
           stats->aligned_words, stats->reverse_rows, stats->reverse_words,
           stats->memmove_bytes, stats->peak_temporary_bytes);
}


static int run_benchmarks(size_t variant_count) {
    enum { STRIDE = 264, ROWS = 1024 };
    size_t bitmap_size = (size_t) STRIDE * ROWS;
    Arena initial_src = make_arena(bitmap_size);
    Arena initial_dst = make_arena(bitmap_size);
    Arena work_src = make_arena(bitmap_size);
    Arena work_dst = make_arena(bitmap_size);
    fill_content(initial_src.data, bitmap_size, 3, UINT64_C(0x3c6ef372fe94f82b));
    fill_content(initial_dst.data, bitmap_size, 3, UINT64_C(0xa54ff53a5f1d36f1));
    QDBitmap src = {work_src.data, bitmap_size, STRIDE, {0, 0, ROWS, STRIDE * 8}};
    QDBitmap dst = {work_dst.data, bitmap_size, STRIDE, {0, 0, ROWS, STRIDE * 8}};
    Workload workloads[4];
    initialize_workloads(workloads);
    if (variant_count == 0 || variant_count > sizeof variants / sizeof variants[0]) {
        return 2;
    }

    printf("{\"timer\":\"CLOCK_MONOTONIC_RAW\",\"repetitions\":%d,\"workloads\":[",
           BENCH_REPETITIONS);
    for (size_t workload_index = 0; workload_index < 4; ++workload_index) {
        Workload *workload = &workloads[workload_index];
        uint64_t durations[sizeof variants / sizeof variants[0]][BENCH_REPETITIONS];
        uint64_t hashes[sizeof variants / sizeof variants[0]];
        QDStats stats[sizeof variants / sizeof variants[0]];
        memset(stats, 0, sizeof stats);

        for (size_t v = 0; v < variant_count; ++v) {
            memcpy(work_src.data, initial_src.data, bitmap_size);
            memcpy(work_dst.data, initial_dst.data, bitmap_size);
            execute_workload(workload, variants[v].function, &src, &dst, NULL);
        }
        for (int repetition = 0; repetition < BENCH_REPETITIONS; ++repetition) {
            size_t order[sizeof variants / sizeof variants[0]];
            for (size_t v = 0; v < variant_count; ++v) {
                order[v] = v;
            }
            for (size_t v = variant_count; v > 1; --v) {
                size_t swap = random_u32() % v;
                size_t temporary = order[v - 1];
                order[v - 1] = order[swap];
                order[swap] = temporary;
            }
            for (size_t position = 0; position < variant_count; ++position) {
                size_t v = order[position];
                memcpy(work_src.data, initial_src.data, bitmap_size);
                memcpy(work_dst.data, initial_dst.data, bitmap_size);
                uint64_t started = now_ns();
                if (execute_workload(workload, variants[v].function,
                                     &src, &dst, NULL) != 0) {
                    return 1;
                }
                durations[v][repetition] = now_ns() - started;
                hashes[v] = checksum(workload->overlap ? work_src.data : work_dst.data,
                                     bitmap_size);
                benchmark_sink ^= hashes[v];
            }
        }
        for (size_t v = 0; v < variant_count; ++v) {
            memcpy(work_src.data, initial_src.data, bitmap_size);
            memcpy(work_dst.data, initial_dst.data, bitmap_size);
            execute_workload(workload, variants[v].function, &src, &dst, &stats[v]);
        }
        for (size_t v = 1; v < variant_count; ++v) {
            if (hashes[v] != hashes[0]) {
                fprintf(stderr, "benchmark checksum mismatch: %s\n", workload->name);
                return 1;
            }
        }

        if (workload_index) {
            putchar(',');
        }
        printf("{\"name\":\"%s\",\"operations\":%zu,\"useful_bits\":%" PRIu64
               ",\"overlap\":%s,\"variants\":[",
               workload->name, workload->operation_count, workload->useful_bits,
               workload->overlap ? "true" : "false");
        for (size_t v = 0; v < variant_count; ++v) {
            uint64_t sorted[BENCH_REPETITIONS];
            memcpy(sorted, durations[v], sizeof sorted);
            qsort(sorted, BENCH_REPETITIONS, sizeof sorted[0], compare_u64);
            uint64_t median = sorted[BENCH_REPETITIONS / 2];
            uint64_t p95 = sorted[BENCH_REPETITIONS - 1];
            double gib_per_second = ((double) workload->useful_bits / 8.0)
                / ((double) median / 1e9) / (1024.0 * 1024.0 * 1024.0);
            if (v) {
                putchar(',');
            }
            printf("{\"name\":\"%s\",\"samples_ns\":[", variants[v].name);
            for (int sample = 0; sample < BENCH_REPETITIONS; ++sample) {
                if (sample) {
                    putchar(',');
                }
                printf("%" PRIu64, durations[v][sample]);
            }
            printf("],\"median_ns\":%" PRIu64 ",\"p95_ns\":%" PRIu64
                   ",\"median_ns_per_operation\":%.3f,\"useful_gib_s\":%.6f"
                   ",\"checksum\":\"%016" PRIx64 "\",\"stats\":",
                   median, p95, (double) median / (double) workload->operation_count,
                   gib_per_second, hashes[v]);
            print_stats(&stats[v]);
            putchar('}');
        }
        printf("]}");
    }
    printf("],\"sink\":\"%016" PRIx64 "\"}\n", benchmark_sink);

    for (size_t i = 0; i < 4; ++i) {
        free(workloads[i].operations);
    }
    free_arena(&initial_src);
    free_arena(&initial_dst);
    free_arena(&work_src);
    free_arena(&work_dst);
    return 0;
}


static void usage(const char *program) {
    fprintf(stderr, "usage: %s --test | --benchmark | --benchmark-r0-r2\n", program);
}


int main(int argc, char **argv) {
    if (argc != 2) {
        usage(argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "--test") == 0) {
        return run_tests();
    }
    if (strcmp(argv[1], "--benchmark") == 0) {
        return run_benchmarks(sizeof variants / sizeof variants[0]);
    }
    if (strcmp(argv[1], "--benchmark-r0-r2") == 0) {
        return run_benchmarks(3);
    }
    usage(argv[0]);
    return 2;
}
