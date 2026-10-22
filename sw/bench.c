/* Cycle-counter smoke test. */
#define START() (*(volatile int*)0x10000004 = 1)
#define STOP()  (*(volatile int*)0x10000008 = 1)

int main(void) {
    volatile int acc = 0;
    START();
    for (int i = 0; i < 100; i++) acc += i;
    STOP();
    return acc;                 /* expect 4950 */
}
