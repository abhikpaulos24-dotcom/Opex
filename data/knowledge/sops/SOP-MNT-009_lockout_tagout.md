# SOP-MNT-009 Lockout-Tagout (LOTO) for CNC machines

## Purpose
Make sure no machine can start, move or release stored energy while someone works on it.
Applies to every maintenance task that opens a guard, enclosure or electrical panel.

## Safety
- Only trained and authorised people may apply a lock. Each person applies their own lock.
- Never rely on the emergency stop or the CNC "feed hold" as isolation.
- Spindles coast: wait until the spindle has fully stopped (check the spindle speed display reads 0).

## Steps
1. Tell the operator and the shift supervisor; record the job in the maintenance log.
2. Stop the program at a safe point, retract the tool, and press cycle stop.
3. Switch off the machine at the main isolator. Lock the isolator in the OFF position and attach your tag (name, date, reason).
4. Release stored energy: bleed hydraulic and pneumatic pressure to zero, lower or block any vertical axis that can fall under gravity, and wait 5 minutes for drive capacitors to discharge.
5. Verify isolation: try to start the machine (it must not start), then test for zero voltage at the drive input with a rated tester.
6. Do the work.
7. Remove tools and rags, refit all guards, and check nobody is inside the guarding.
8. Remove your own lock and tag, restore power, and hand over to the operator with a test run at reduced feed.

## Required tools
Personal padlock and tag, voltage tester (CAT III 600 V or better), axis support blocks.
