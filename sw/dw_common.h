/* Shared definitions for the depthwise KxK kernels with generic K (used by the
 * 5x5 kernels). Same layout, data and checksum scheme as dwconv*.c. */
#ifndef DW_COMMON_H
#define DW_COMMON_H
#include "bench.h"
#include "requant.h"
#ifndef CH
#define CH 8
#endif
#ifndef H
#define H 16
#endif
#ifndef W
#define W 16
#endif
#ifndef K
#define K 5
#endif
#define OH (H - K + 1)
#define OW (W - K + 1)
static signed char input[CH][H][W] __attribute__((aligned(4)));
static signed char weight[CH][K][K];
static signed char output[CH][OH][OW];
static unsigned int rng_state;
static int rnd(void) { rng_state = rng_state * 1103515245u + 12345u; return (int)((rng_state >> 16) & 0xFF) - 128; }
static void init_data(void) {
    rng_state = 1;
    for (int c = 0; c < CH; c++) {
        for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) input[c][y][x] = (signed char)(rnd() >> 2);
        for (int i = 0; i < K; i++) for (int j = 0; j < K; j++) weight[c][i][j] = (signed char)(rnd() >> 3);
    }
}
static int checksum(void) {
    int sum = 0;
    for (int c = 0; c < CH; c++) for (int y = 0; y < OH; y++) for (int x = 0; x < OW; x++) sum += output[c][y][x];
    return sum & 0xFFFF;
}
#endif
