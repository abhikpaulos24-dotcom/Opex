# SOP-MNT-017 Spindle drive belt inspection and tensioning

## Purpose
Find and fix belt slip, which shows up as spindle speed dropping under load, longer cycle times and a burning smell.

## Safety
Apply Lockout-Tagout (SOP-MNT-009). Never check belt tension with the machine powered.

## Inspection steps
1. Compare commanded and actual spindle speed under load on the CNC diagnostics page; a drop of more than 2% under load suggests slip.
2. After LOTO, remove the belt guard. Look for glazing (shiny belt surface), cracks across the ribs, and black dust inside the guard.
3. Measure tension with the sonic tension meter at the midpoint of the span.
4. Check pulley alignment with a straight edge or laser alignment tool.
5. Check the spindle motor encoder connector for looseness or oil contamination.

## Expected readings
- Speed drop under load: less than 1%.
- Belt tension: within the range on the machine's belt label.
- Pulley misalignment: less than 0.5 mm over the span.

## Fix
- Glazed, cracked or stretched belt: replace the belt (always replace matched sets together) and re-tension.
- Good belt but low tension: re-tension, run 30 minutes, re-check (new belts relax).
- Encoder alarm or speed hunting with a good belt: clean and re-seat the encoder connector; replace the encoder if the alarm returns.

## Typical duration
Re-tension: 45 minutes. Belt replacement: 3–4 hours.
