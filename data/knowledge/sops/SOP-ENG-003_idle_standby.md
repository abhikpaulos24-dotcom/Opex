# SOP-ENG-003 Idle standby and energy saving

## Purpose
Cut the energy machines waste while they are not making parts. An idle CNC machine with spindle, coolant pump, hydraulics and chip conveyor running draws 40–60% of its cutting power.

## Rule
If a machine will be idle for more than 10 minutes (waiting for material, inspection, breaks, shift handover):
1. Stop the spindle and the coolant pump.
2. Switch the chip conveyor and mist collector off.
3. Put the machine in its controller "energy saving / standby" mode if available (servos off, hydraulics idle).
Do not switch off the main isolator for short waits; warm-up after a full shutdown costs more energy and time.

## Restart
Leave 5 minutes of spindle warm-up for high-precision work (grinding, boring) before restarting production.

## Why it matters
At ₹9.25 per kWh, a machine idling at 5 kW for 2 hours a day costs about ₹28,000 a year.
