/* cv.dotsp.b: signed 8-bit SIMD dot product.
   rD = rs1[7:0]*rs2[7:0] + rs1[15:8]*rs2[15:8]
      + rs1[23:16]*rs2[23:16] + rs1[31:24]*rs2[31:24]

   Encoding (docs/source/instruction_set_extensions.rst):
     [31:25]=0x48  [24:20]=rs2  [19:15]=rs1  [14:12]=0x1  [11:7]=rd  [6:0]=0x7b   */

static inline int cv_dotsp_b(int a, int b) {
    int r;
    asm volatile (".insn r 0x7b, 0x1, 0x48, %0, %1, %2"
                  : "=r"(r) : "r"(a), "r"(b));
    return r;
}

int main(void) {
    volatile int a = 0x01020304;   /* bytes 4,3,2,1 */
    volatile int b = 0x01010101;   /* bytes 1,1,1,1 */
    return cv_dotsp_b(a, b);       /* expect 4+3+2+1 = 10 */
}
