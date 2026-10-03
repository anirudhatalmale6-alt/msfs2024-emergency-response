# Emergency Landing Response System — MSFS 2024

You declare an emergency. You land. Emergency services actually come and meet you.

Fire appliances to the runway for a fire. Ambulance to the stand for a sick
passenger. The right services, to the right place, without you clicking anything.

---

## Why this doesn't integrate with SayIntentions or BeyondATC

Because it shouldn't have to.

When you declare an emergency you squawk **7700**, and the transponder code is
just a value in the sim. This watches that. It neither knows nor cares whether
you told SayIntentions, BeyondATC, VATSIM or nobody at all.

That beats integrating with either of them:

- works with every ATC addon, including ones that don't exist yet
- works with no ATC at all
- can't be broken by someone else's update
- nothing to reverse-engineer and no API to be granted access to

On top of the squawk it also watches the actual aircraft state — engine fire,
fuel state — so the trucks roll even if you were too busy flying to squawk.

## Where this sits next to what already exists

Checked before writing a line of this:

| Addon | What it is | Overlap |
|---|---|---|
| EmergencyDispatcherPro | you fly **as** the responder | none — opposite direction |
| FS Fire / Aero Fire Global / MissionGen | aerial firefighting, you're the responder | none |
| **Emergency Response On Demand** (free) | spawns emergency vehicles from a toolbar | **closest** — but entirely **manual** |

The vehicles exist already and are free. Manual spawning exists already and is
free. What nobody has built is the part that **notices you are in trouble,
works out what you need, and sends it to where you actually stopped.**

That's the whole point of this project, and it's a much sharper job than
"build an emergency response addon", because the assets are a solved problem.

## How it actually works

```
    watch the sim                decide                    act
 ┌────────────────────┐   ┌──────────────────┐   ┌──────────────────────┐
 │ transponder = 7700 │   │ what's wrong?    │   │ spawn out of sight   │
 │ engine on fire     │──▶│ → which services │──▶│ drive to the target  │
 │ fuel state         │   │ → runway or gate?│   │ park around aircraft │
 │ position, speed    │   │ → how many?      │   │ resolve, then leave  │
 └────────────────────┘   └──────────────────┘   └──────────────────────┘
```

The decision step is where the domain knowledge lives, and it's the bit that
makes it feel real rather than scripted:

- **Fire** → appliances meet you **on the runway**. You don't taxi a burning
  aircraft to a stand.
- **Sick passenger** → you continue to a **stand**, and the ambulance meets you
  there. That's what actually happens.
- **Heavy landing / gear problem** → both, on the runway, and they sit and wait
  rather than approaching.

## Build order

Deliberately smallest-risk-first. Each step is only worth doing if the one
before it worked.

1. **`step1_connect.py`** — does SimConnect work on MSFS 2024 at all, and can
   we read the transponder? *(written — run this first)*
2. **Spawn one fire truck and drive it to the parked aircraft.** This is the
   real technical risk of the entire project. Everything after it is logic.
3. Emergency detection and service selection.
4. Formation parking, resolution, cleanup.
5. UI panel.

## Performance

This is an **external program**, not an in-sim module. It runs in its own
process, so the sim's frame loop is untouched. That is the single biggest
reason to build it this way.

The things that actually cost frames, and what's being done about each:

| Cost | Decision |
|---|---|
| Number of spawned objects | a handful, not a fleet |
| Model complexity | low-poly vehicle models |
| Position update rate | ~10 Hz is plenty for a driving vehicle; nowhere near frame rate |
| Polling the sim | request only the values actually needed, on change where possible |
| Objects left lying around | despawn once the scenario resolves |

Frame timing gets measured before and after rather than assumed.

## Status

Step 1 written, **not yet run** — SimConnect needs the sim, and this was
written on Linux. That's exactly what step 1 is for.
