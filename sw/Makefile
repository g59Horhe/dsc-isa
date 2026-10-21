# Build bare-metal programs for the CV32E40P Verilator harness.
#
#   make                 build hello.hex and dotp.hex
#   make run-hello       run hello on the baseline core
#   make run-dotp        run dotp on both cores (dotp needs COREV_PULP=1)
#
# Set CROSS if your toolchain prefix differs:
#   make CROSS=riscv32-unknown-elf-

CROSS   ?= riscv32-unknown-elf-
CC       = $(CROSS)gcc
OBJCOPY  = $(CROSS)objcopy
OBJDUMP  = $(CROSS)objdump

ARCH    = -march=rv32imc -mabi=ilp32
CFLAGS  = $(ARCH) -nostdlib -nostartfiles -O2 -T link.ld

HARNESS = ..

.PHONY: all clean run-hello run-dotp

all: hello.hex dotp.hex

%.elf: %.c crt0.S link.ld
	$(CC) $(CFLAGS) crt0.S $< -o $@

%.bin: %.elf
	$(OBJCOPY) -O binary $< $@

%.hex: %.bin
	python3 bin2hex.py $< > $@

%.dis: %.elf
	$(OBJDUMP) -d $< > $@

run-hello: hello.hex
	$(HARNESS)/obj_base/Vcv32e40p_core --hex hello.hex --cycles 10000

run-dotp: dotp.hex
	@echo "--- COREV_PULP=1 (expect 10) ---"
	@$(HARNESS)/obj_pulp/Vcv32e40p_core --hex dotp.hex --cycles 5000
	@echo "--- COREV_PULP=0 (expect TIMEOUT: illegal instruction) ---"
	-@$(HARNESS)/obj_base/Vcv32e40p_core --hex dotp.hex --cycles 5000

clean:
	rm -f *.elf *.bin *.hex *.dis
