# Hardware Testing & Feedback Guide

This is the **exact procedure** for testing LiveReact on the real rig, and the
system for capturing what happens so you can hand it straight back to Claude for
analysis. Pair it with [`HARDWARE.md`](HARDWARE.md) (the deeper setup reference).

> First contact between this code and real devices **will** surface mismatches
> (channel maps, MIDI CCs) — that's expected and exactly what these tools are for.
> Don't try to fix code yourself; **record the session and send it back.**

---

## The feedback loop (how this works)

```
  1. Run a test with --record   →  creates recordings/session-<timestamp>/
  2. Watch the lights, fill in     NOTES.md in that folder (what you saw)
  3. Hand the folder back to Claude ("analyze recordings/session-<timestamp>")
  4. Claude reads logs + state + your notes, proposes/makes fixes
  5. Repeat
```

Every recorded session folder contains:

| File | What it is |
|------|------------|
| `session.log` | All output (info/warnings/errors + tracebacks) |
| `errors.log`  | Just warnings/errors — quick scan for problems |
| `state.jsonl` | What the show did, sampled ~10×/sec (BPM, beat, energy, inputs, active DMX channels) |
| `meta.json`   | Your machine + detected devices + run settings at startup |
| `summary.json`| Totals (frames sent, samples) at shutdown |
| `NOTES.md`    | **You fill this in** — what you expected vs. what actually happened |

To send it back: either point Claude at the folder path, or zip it:
```
python -m livereact --bundle          # zips the latest session
```

---

## Before you start

```
# 1. Activate the venv and confirm the environment + detected devices:
python -m livereact --doctor

# 2. (Only for Pro DJ Link) install the git-only library:
python -m pip install "git+https://github.com/flesniak/python-prodj-link"
```

`--doctor` writes `diagnostics/doctor.txt` — **send that first**; it tells Claude
exactly what your machine sees (serial ports with VID/PID, MIDI inputs, versions).

---

## Test 1 — Fixtures, one at a time (safest; no DJ gear needed)

Goal: confirm each of the 8 fixtures is wired/addressed correctly and that every
channel does what the profile claims.

```
python -m livereact --hardware --fixture-test --record
```

For **each** fixture (MH L/R, Laser L/R, Par L/R, Bar L/R):
1. Click its **Flash** button — the right fixture should light up. Note in `NOTES.md`
   if the *wrong* fixture lights (addressing problem).
2. Drag each channel slider and confirm the behavior matches the label
   (pan / tilt / dimmer / red / green / blue / strobe / …). Note any mismatch.

⚠️ **Laser safety:** raise laser channels only briefly, with beams pointed safely
above head height. Confirm the laser is OFF at slider 0.

**Expected:** every fixture identifiable; every channel does what its label says.
**Record:** per-fixture observations in `NOTES.md`.

---

## Test 2 — Network / Pro DJ Link

```
python -m livereact --net-check          # check the link-local IP + firewall first
python -m livereact --hardware --visualize --record
```

Play a track on the XDJ-XZ.

**Expected:** in the console, BPM shows the track tempo, the beat/bar counters
advance, and "clock=locked / PDL fresh". The rig pulses on the **real** beats.
**If you see "No DJ-Link device seen":** check the static IP (`169.254.50.50/16`),
that Link is on, and the firewall (UDP 50000–50002) — see `HARDWARE.md`.
**Record:** `state.jsonl` captures whether `pdl_fresh` / `bpm` / `bar` are correct.

---

## Test 3 — MIDI (the XDJ mixer)

The default CC map is a guess and almost certainly needs remapping for your unit.

```
python -m livereact --midi-monitor --record
```

Move each control and watch the printed `channel`/`cc`:
- channel faders A and B
- crossfader
- EQ low/mid/high on each channel

Write down which `channel`/`cc` each control reports. (This is captured to
`midi-monitor.txt` in the session folder.) Then either send it to Claude to build
your `midi_map.json`, or fill it in yourself (keys are `"channel:cc"`):
```json
{ "5:31": "crossfader", "5:23": "fader_a", "5:24": "fader_b" }
```

**Expected:** moving controls prints CC events. (Some controls may be HID and not
appear at all — note which.)

---

## Test 4 — Full end-to-end

```
python -m livereact --hardware --visualize --record
```

Play a set: a track, a build, a drop, then mix into another track.

**Expected:**
- lights pulse on the beat, color follows the EQ
- scenes rotate every ~16 bars
- a drop brings lasers (once armed in the console) + bigger movement
- crossfading into the next track is detected (console shows TRANSITION) and the
  show settles into a new look afterward
- the operator controls (brightness, blackout, freeze, skip) all respond

**Record:** the whole thing. Note anything that felt wrong (timing, color, a fixture
misbehaving) in `NOTES.md`.

---

## Quick troubleshooting

| Symptom | First thing to check |
|--------|----------------------|
| No lights at all | `--doctor` shows the Enttec (FTDI VID `0x0403`)? DMX terminator on? |
| Wrong fixture responds | DMX address/mode on that fixture vs. `default_rig.json` |
| A channel does the wrong thing | Channel map in `fixtures/profiles.py` (send the session, Claude fixes it) |
| "No DJ-Link device seen" | Static IP `169.254.50.50/16`, Link on, firewall UDP 50000–50002 |
| Beat not locking | `state.jsonl` — is `bpm` right and `pdl_fresh` true? Else network/PDL issue |
| MIDI does nothing | `--midi-monitor` — do controls show up? Enable Utility→MIDI on the XZ |
| Lasers won't light | Arm them in the console; only drop scenes use them |

---

## What to send back to Claude

For any issue, the most useful bundle is:
1. `diagnostics/doctor.txt` (or `.json`)
2. the whole `recordings/session-<timestamp>/` folder (especially `NOTES.md`,
   `errors.log`, and `state.jsonl`)
3. for MIDI: the `midi-monitor.txt` capture

Then just say: *"analyze this session and tell me what's wrong / fix it."*
