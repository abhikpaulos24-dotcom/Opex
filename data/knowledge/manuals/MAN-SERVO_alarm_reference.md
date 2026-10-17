# Servo drive alarm reference - excerpt (generic, demo plant)

## Overvoltage on the DC bus
Cause: braking energy not absorbed (failed regeneration resistor), supply voltage spikes, or a loose power terminal.
Check: incoming three-phase voltage (415 V ±10%), regeneration resistor resistance, terminal temperature with a thermal camera.
Fix: retighten terminals to the specified torque; replace the power module if the alarm repeats under normal supply.

## Overcurrent / overload
Cause: mechanical overload (worn tool, crash, seized bearing), motor insulation fault.
Check: cutting load history, spindle load meter, motor insulation resistance (above 100 MΩ at 500 V).
Fix: remove the mechanical cause first; never just reset and continue.

## Encoder communication alarm
Cause: loose or oil-contaminated connector, damaged cable.
Fix: clean and re-seat; replace the cable if damaged; replace the encoder if the alarm returns.

## Safety
All work inside the electrical cabinet requires Lockout-Tagout (SOP-MNT-009) and a 5-minute wait for capacitor discharge. Verify zero voltage before touching terminals.
