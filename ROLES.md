# Roles in OpEx: who can do what, and why

OpEx has two roles. Every person has exactly one. The rules are enforced **on the server**, not just hidden in the screens, so they hold even if someone calls the API directly. The source of truth is `backend/app/auth/security.py`.

**The idea in one line:** engineers make the day-to-day decisions on the floor; managers also run the plant (people, priorities, costs).

```
Plant manager          everything an engineer can do, plus people, priorities, costs, demo controls
   └─ Maintenance engineer   approves or rejects any action, acknowledges alerts, writes investigations
```

## How people get in

- Everyone signs in with **Google**. OpEx keeps no passwords for real people.
- A person can sign in only after a manager has added their Google email. A Google account nobody added is turned away with a message to ask the plant manager.
- The first manager is created automatically for the email in `MASTER_ADMIN_EMAIL` (`srihithapulapa1@gmail.com`). That account can never be demoted or switched off from the app, so there is always a manager.
- Demo mode only (`DEMO_MODE=true`): a list of two demo accounts (manager and engineer) to pick from and log in. Turn demo mode off for real use.

## What each role can do

✅ = can, ➖ = cannot

| | Plant manager | Maintenance engineer |
|---|:-:|:-:|
| See the overview, every machine, charts, the learning log | ✅ | ✅ |
| Ask the copilot, hear answers, use the AI incident room | ✅ | ✅ |
| Run the 5-year simulation, rewind, download results | ✅ | ✅ |
| Check a part photo, check a sensor CSV | ✅ | ✅ |
| Acknowledge alerts | ✅ | ✅ |
| Approve or reject **any** recommendation, small or major | ✅ | ✅ |
| Write an AI investigation for an incident | ✅ | ✅ |
| Add documents (SOPs, notes) to the factory memory | ✅ | ✅ |
| Change plant priorities and factory economics (₹ assumptions) | ✅ | ➖ |
| Demo controls (move the plant clock, start a fault, reset) | ✅ | ➖ |
| Send a snapshot to BigQuery | ✅ | ➖ |
| Add and manage people | ✅ managers and engineers | ➖ |
| Read the audit log | ✅ | ➖ |
| See who made each decision, their notes, who acknowledged an alert | ✅ | ✅ |

Notes:
- Actions that stop or slow a machine ask for a second confirmation that spells out the consequence, whoever approves them.
- A manager cannot change their own role or switch themselves off, so the plant is never left without a manager.

## Each role, and why it is set up this way

### Plant manager
**Does:** everything an engineer can do, plus plant priorities (cost, production, quality, energy, risk weights), factory economics, demo controls, BigQuery export, the full audit log, and adding or managing managers and engineers.

**Why:** the manager is accountable for the plant's money and its people, so they set the numbers every recommendation is priced with and decide who works in the system.

### Maintenance engineer
**Does:** approves or rejects any recommendation, including stops, slowdowns, shifting production and part replacements. Acknowledges alerts, writes investigations and adds SOPs to the factory memory.

**Cannot:** change economics, priorities or people, or read the audit log.

**Why:** stopping a machine or swapping a spindle bearing costs real downtime and money, and needs someone who understands the machine and the plan. That is the engineer's job in a real plant. Engineers also own the documents the Safety officer agent quotes and the write-ups that become the plant's memory.

## Who adds whom

| Role | Can add / change / switch off |
|---|---|
| Plant manager | Plant managers and maintenance engineers (not themselves) |
| Maintenance engineer | Nobody |

Everything a manager does to the people list is written to the audit log.

## Why these choices overall

1. **Keep it simple.** Two roles are easy to explain and to audit.
2. **Humans decide.** OpEx never changes a machine on its own. Every action has a named person behind it.
3. **Money and people need a manager.** Settings, costs and the people list are manager-only.
4. **Safe defaults.** Unknown accounts are refused, the first manager cannot be removed from the app, and demo shortcuts exist only in demo mode.
5. **Everything is on the record.** Decisions, settings changes and people changes go to the audit log.

## Upgrading from five roles

Earlier versions had master admin, plant manager, maintenance engineer, machine operator and viewer. On start-up OpEx moves anyone still on a retired role: master admin becomes manager, and operator and viewer become engineer. The old operator and viewer demo accounts are switched off. If you use Supabase, run `database/05_two_roles.sql` once in the SQL Editor to tighten the database rule.

## Changing the rules

All permissions are in one table, `PERMISSIONS`, and who can add whom in `MANAGEABLE_ROLES`, both in `backend/app/auth/security.py`. The tests in `backend/tests/test_flows.py` check every rule above, so a change that breaks one fails the tests.
