/* Smoke test: no I/O, no libc. The return value is what gets reported. */
int main(void) {
    volatile int a = 20;
    volatile int b = 22;
    return a + b;               /* expect 42 */
}
