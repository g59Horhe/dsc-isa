/* REAL_DATA mode: fill the kernel's working arrays from the const arrays of
 * the data header (-DREAL_HDR=real/<file>.h, included by requant.h). Element-wise copy; the attribute keeps
 * GCC from turning it into a memcpy call (no libc). */
#ifndef REAL_INIT_H
#define REAL_INIT_H
#define REAL_INIT(inp, ninp, wgt, nwgt) \
    __attribute__((optimize("no-tree-loop-distribute-patterns"))) \
    static void init_data(void) { \
        unsigned char *di = (unsigned char *)(inp); signed char *dw = (signed char *)(wgt); \
        for (int i = 0; i < (ninp); i++) di[i] = real_input[i]; \
        for (int i = 0; i < (nwgt); i++) dw[i] = real_weight[i]; \
    }
#endif
