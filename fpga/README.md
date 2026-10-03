# FPGA safety watchdog (stretch goal)

An independent hardware check that does not trust the ESP32 software.

Idea: the FPGA counts step pulses on the motor STEP line over a fixed window. If the pulse rate exceeds a hard-wired maximum, it forces the driver ENABLE line off and latches a fault output that the ESP32 reads and reports as an alarm.

Only start this after phase 3 works end to end. See docs/PLAN.md, stretch goals.
