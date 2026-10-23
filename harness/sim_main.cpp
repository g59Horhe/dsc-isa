// Verilator harness for CV32E40P.
//
// Memory: one flat array behind both ports. Protocol is req/gnt/rvalid.
// With --wait 0 a granted request returns the next cycle. With --wait N the
// response is delayed N further cycles and the port refuses new grants while
// a response is outstanding.
//
// Magic addresses (stores):
//   0x10000000  halt, report the stored word
//   0x10000004  start cycle counter
//   0x10000008  stop cycle counter
//   0x1000000C  report an auxiliary word (printed as AUX <n>)
//
// --wait N   wait states on the data port (and on the instruction port
//            unless --iwait is given)
// --iwait N  wait states on the instruction port only
// --icache SIZE LINE  direct-mapped instruction cache model, SIZE and LINE in
//            bytes; a hit answers with zero wait, a miss waits --iwait (or
//            --wait) cycles and fills the line. Hit/miss counts are reported.
//
// While the cycle counter runs, the harness counts data-port reads and
// writes and instruction-port fetches (32-bit words), reported on the
// MEASURED line. An unaligned word load from the core shows as two reads.

#include <verilated.h>
#include "Vcv32e40p_core.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

static const uint32_t MEM_WORDS   = 64 * 1024 / 4;
static const uint32_t BOOT_ADDR   = 0x00000080;
static const uint32_t MAGIC_HALT  = 0x10000000;
static const uint32_t MAGIC_START = 0x10000004;
static const uint32_t MAGIC_STOP  = 0x10000008;
static const uint32_t MAGIC_AUX   = 0x1000000C;   // store -> print as AUX (perf counter deltas etc.)

static uint32_t mem[MEM_WORDS];

static inline bool in_range(uint32_t addr) { return (addr >> 2) < MEM_WORDS; }

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);

    const char* hexfile = nullptr;
    uint64_t max_cycles = 100000;
    uint32_t wait_states = 0; uint32_t iwait = 0xFFFFFFFFu;
    uint32_t ic_size = 0, ic_line = 16; uint64_t ic_hit = 0, ic_miss = 0; uint64_t n_dread=0, n_dwrite=0, n_ifetch=0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--hex")    && i + 1 < argc) hexfile = argv[++i];
        if (!strcmp(argv[i], "--cycles") && i + 1 < argc) max_cycles = strtoull(argv[++i], nullptr, 0);
        if (!strcmp(argv[i], "--wait")   && i + 1 < argc) wait_states = (uint32_t)strtoul(argv[++i], nullptr, 0);
        if (!strcmp(argv[i], "--iwait")  && i + 1 < argc) iwait = (uint32_t)strtoul(argv[++i], nullptr, 0);
        if (!strcmp(argv[i], "--icache") && i + 2 < argc) { ic_size = (uint32_t)strtoul(argv[++i], nullptr, 0); ic_line = (uint32_t)strtoul(argv[++i], nullptr, 0); }
    }
    if (iwait == 0xFFFFFFFFu) iwait = wait_states;
    // Direct-mapped I-cache: one tag per line, valid bit in tag[31].
    uint32_t ic_sets = (ic_size && ic_line) ? ic_size / ic_line : 0;
    uint32_t* ic_tag = ic_sets ? new uint32_t[ic_sets]() : nullptr;
    if (!hexfile) { fprintf(stderr, "usage: %s --hex <f> [--cycles N] [--wait N]\n", argv[0]); return 1; }

    memset(mem, 0, sizeof(mem));
    FILE* f = fopen(hexfile, "r");
    if (!f) { fprintf(stderr, "cannot open %s\n", hexfile); return 1; }
    char line[256];
    uint32_t idx = BOOT_ADDR >> 2;
    while (fgets(line, sizeof(line), f)) {
        if (line[0]=='\0'||line[0]=='\n'||line[0]=='#'||line[0]=='/') continue;
        mem[idx++] = (uint32_t)strtoul(line, nullptr, 16);
    }
    fclose(f);
    printf("loaded %u words at 0x%08x\n", idx - (BOOT_ADDR >> 2), BOOT_ADDR);

    Vcv32e40p_core* dut = new Vcv32e40p_core;
    dut->clk_i=0; dut->rst_ni=0; dut->pulp_clock_en_i=1; dut->scan_cg_en_i=0;
    dut->boot_addr_i=BOOT_ADDR; dut->mtvec_addr_i=0; dut->dm_halt_addr_i=0;
    dut->hart_id_i=0; dut->dm_exception_addr_i=0; dut->irq_i=0;
    dut->debug_req_i=0; dut->fetch_enable_i=0;
    dut->instr_gnt_i=0; dut->instr_rvalid_i=0; dut->instr_rdata_i=0;
    dut->data_gnt_i=0; dut->data_rvalid_i=0; dut->data_rdata_i=0;
    dut->apu_gnt_i=0; dut->apu_rvalid_i=0; dut->apu_result_i=0; dut->apu_flags_i=0;

    int i_delay = -1; uint32_t i_data = 0;
    int d_delay = -1; uint32_t d_data = 0;
    uint64_t cycle = 0;
    bool halted = false; uint32_t halt_value = 0;
    bool counting = false; uint64_t count_start = 0, measured = 0;
    bool measured_valid = false;

    while (cycle < max_cycles && !halted) {
        dut->clk_i = 0;
        dut->instr_rvalid_i = (i_delay == 0);
        dut->instr_rdata_i  = i_data;
        dut->data_rvalid_i  = (d_delay == 0);
        dut->data_rdata_i   = d_data;
        dut->eval();

        dut->instr_gnt_i = dut->instr_req_o && (i_delay <= 0);
        dut->data_gnt_i  = dut->data_req_o  && (d_delay <= 0);
        dut->eval();

        if (i_delay > 0) i_delay--; else i_delay = -1;
        if (d_delay > 0) d_delay--; else d_delay = -1;

        if (dut->instr_req_o && dut->instr_gnt_i) {
            uint32_t a = dut->instr_addr_o;
            i_data = in_range(a) ? mem[a >> 2] : 0;
            int d = (int)iwait;
            if (ic_sets) {
                uint32_t line = a / ic_line, set = line % ic_sets, tag = line | 0x80000000u;
                if (ic_tag[set] == tag) { d = 0; if (counting) ic_hit++; }
                else { ic_tag[set] = tag; if (counting) ic_miss++; }
            }
            i_delay = d; if (counting) n_ifetch++;
        }

        if (dut->data_req_o && dut->data_gnt_i) {
            d_delay = (int)wait_states;
            uint32_t a  = dut->data_addr_o;
            uint32_t be = dut->data_be_o;
            if (dut->data_we_o) {
                if (a == MAGIC_HALT) {
                    halt_value = dut->data_wdata_o; halted = true;
                } else if (a == MAGIC_START) {
                    counting = true; count_start = cycle;
                } else if (a == MAGIC_AUX) {
                    printf("AUX %u\n", dut->data_wdata_o);
                } else if (a == MAGIC_STOP) {
                    if (counting) { measured = cycle - count_start;
                                    measured_valid = true; counting = false; }
                } else if (in_range(a)) {
                    if (counting) n_dwrite++;
                    uint32_t old = mem[a >> 2], wd = dut->data_wdata_o, m = 0;
                    for (int b = 0; b < 4; b++) if (be & (1u << b)) m |= 0xFFu << (b * 8);
                    mem[a >> 2] = (old & ~m) | (wd & m);
                }
                d_data = 0;
            } else {
                d_data = in_range(a) ? mem[a >> 2] : 0; if (counting) n_dread++;
            }
        }

        dut->clk_i = 1;
        dut->eval();

        cycle++;
        if (cycle == 5)  dut->rst_ni = 1;
        if (cycle == 10) dut->fetch_enable_i = 1;
    }

    dut->final();
    delete dut;

    if (halted) {
        printf("HALT at cycle %llu, value = %u (0x%08x)\n",
               (unsigned long long)cycle, halt_value, halt_value);
        if (measured_valid && ic_sets)
            printf("ICACHE size=%u line=%u hits=%llu misses=%llu\n", ic_size, ic_line,
                   (unsigned long long)ic_hit, (unsigned long long)ic_miss);
        if (measured_valid)
            printf("MEASURED %llu cycles (wait_states=%u iwait=%u) dread=%llu dwrite=%llu ifetch=%llu\n",
                   (unsigned long long)measured, wait_states, iwait, (unsigned long long)n_dread, (unsigned long long)n_dwrite, (unsigned long long)n_ifetch);
        return 0;
    }
    printf("TIMEOUT after %llu cycles\n", (unsigned long long)cycle);
    return 2;
}
