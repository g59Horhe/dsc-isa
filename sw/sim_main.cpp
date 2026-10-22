// Minimal Verilator harness for CV32E40P.
//
// Memory model: one flat array serving both instruction and data ports.
// The core's memory protocol is req/gnt/rvalid:
//   - core raises req
//   - memory raises gnt in the same cycle (we always grant immediately)
//   - memory raises rvalid with the data one cycle later
//
// Halt: a store to MAGIC_HALT ends the simulation and prints the stored word.
// This is how the benchmark will report its result later -- no need to peek
// into the register file.

#include <verilated.h>
#include "Vcv32e40p_core.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <string>

static const uint32_t MEM_WORDS  = 64 * 1024 / 4;   // 64 KB
static const uint32_t BOOT_ADDR  = 0x00000080;
static const uint32_t MAGIC_HALT  = 0x10000000;  // store -> end sim, report value
static const uint32_t MAGIC_START = 0x10000004;  // store -> start cycle counter
static const uint32_t MAGIC_STOP  = 0x10000008;  // store -> stop cycle counter

static uint32_t mem[MEM_WORDS];

static inline bool in_range(uint32_t addr) {
    return (addr >> 2) < MEM_WORDS;
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);

    const char* hexfile = nullptr;
    uint64_t max_cycles = 100000;
    uint32_t wait_states = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--hex") && i + 1 < argc)    hexfile = argv[++i];
        if (!strcmp(argv[i], "--cycles") && i + 1 < argc) max_cycles = strtoull(argv[++i], nullptr, 0);
        if (!strcmp(argv[i], "--wait") && i + 1 < argc)   wait_states = (uint32_t)strtoul(argv[++i], nullptr, 0);
    }
    if (!hexfile) { fprintf(stderr, "usage: %s --hex <file> [--cycles N]\n", argv[0]); return 1; }

    // Load program: one 32-bit word per line, hex, starting at BOOT_ADDR.
    memset(mem, 0, sizeof(mem));
    FILE* f = fopen(hexfile, "r");
    if (!f) { fprintf(stderr, "cannot open %s\n", hexfile); return 1; }
    char line[256];
    uint32_t idx = BOOT_ADDR >> 2;
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == '\0' || line[0] == '\n' || line[0] == '#' || line[0] == '/') continue;
        mem[idx++] = (uint32_t)strtoul(line, nullptr, 16);
    }
    fclose(f);
    printf("loaded %u words at 0x%08x\n", idx - (BOOT_ADDR >> 2), BOOT_ADDR);

    Vcv32e40p_core* dut = new Vcv32e40p_core;

    dut->clk_i               = 0;
    dut->rst_ni              = 0;
    dut->pulp_clock_en_i     = 1;
    dut->scan_cg_en_i        = 0;
    dut->boot_addr_i         = BOOT_ADDR;
    dut->mtvec_addr_i        = 0;
    dut->dm_halt_addr_i      = 0;
    dut->hart_id_i           = 0;
    dut->dm_exception_addr_i = 0;
    dut->irq_i               = 0;
    dut->debug_req_i         = 0;
    dut->fetch_enable_i      = 0;
    dut->instr_gnt_i         = 0;
    dut->instr_rvalid_i      = 0;
    dut->instr_rdata_i       = 0;
    dut->data_gnt_i          = 0;
    dut->data_rvalid_i       = 0;
    dut->data_rdata_i        = 0;
    dut->apu_gnt_i           = 0;
    dut->apu_rvalid_i        = 0;
    dut->apu_result_i        = 0;
    dut->apu_flags_i         = 0;

    // Memory response pipeline. With wait_states = 0 a request granted this
    // cycle returns next cycle. With N > 0 the response is delayed N more
    // cycles, and the port refuses new grants while a response is outstanding.
    int      i_delay = -1;  uint32_t i_data = 0;   // -1 = idle
    int      d_delay = -1;  uint32_t d_data = 0;

    uint64_t cycle = 0;
    bool halted = false;
    uint32_t halt_value = 0;

    // Cycle counter, bracketed by the program itself.
    bool     counting = false;
    uint64_t count_start = 0;
    uint64_t measured = 0;
    bool     measured_valid = false;

    while (cycle < max_cycles && !halted) {
        // ---- falling edge: present responses from the previous request ----
        dut->clk_i = 0;
        dut->instr_rvalid_i = (i_delay == 0);
        dut->instr_rdata_i  = i_data;
        dut->data_rvalid_i  = (d_delay == 0);
        dut->data_rdata_i   = d_data;
        dut->eval();

        // Grant only when the port is free (no response outstanding).
        dut->instr_gnt_i = dut->instr_req_o && (i_delay <= 0);
        dut->data_gnt_i  = dut->data_req_o  && (d_delay <= 0);
        dut->eval();

        if (i_delay > 0) i_delay--;
        else             i_delay = -1;
        if (d_delay > 0) d_delay--;
        else             d_delay = -1;

        if (dut->instr_req_o && dut->instr_gnt_i) {
            uint32_t a = dut->instr_addr_o;
            i_data = in_range(a) ? mem[a >> 2] : 0;
            i_delay = (int)wait_states;
        }

        if (dut->data_req_o && dut->data_gnt_i) {
            d_delay = (int)wait_states;
            uint32_t a  = dut->data_addr_o;
            uint32_t be = dut->data_be_o;
            if (dut->data_we_o) {
                if (a == MAGIC_HALT) {
                    halt_value = dut->data_wdata_o;
                    halted = true;
                } else if (a == MAGIC_START) {
                    counting = true;
                    count_start = cycle;
                } else if (a == MAGIC_STOP) {
                    if (counting) {
                        measured = cycle - count_start;
                        measured_valid = true;
                        counting = false;
                    }
                } else if (in_range(a)) {
                    uint32_t old = mem[a >> 2];
                    uint32_t wd  = dut->data_wdata_o;
                    uint32_t m = 0;
                    for (int b = 0; b < 4; b++) if (be & (1u << b)) m |= 0xFFu << (b * 8);
                    mem[a >> 2] = (old & ~m) | (wd & m);
                }
                d_data = 0;
            } else {
                d_data = in_range(a) ? mem[a >> 2] : 0;
            }
        }

        // ---- rising edge ----
        dut->clk_i = 1;
        dut->eval();

        cycle++;
        if (cycle == 5)  dut->rst_ni = 1;          // release reset
        if (cycle == 10) dut->fetch_enable_i = 1;  // start fetching
    }

    dut->final();
    delete dut;

    if (halted) {
        printf("HALT at cycle %llu, value = %u (0x%08x)\n",
               (unsigned long long)cycle, halt_value, halt_value);
        if (measured_valid)
            printf("MEASURED %llu cycles (wait_states=%u)\n",
                   (unsigned long long)measured, wait_states);
        return 0;
    }
    printf("TIMEOUT after %llu cycles\n", (unsigned long long)cycle);
    return 2;
}
