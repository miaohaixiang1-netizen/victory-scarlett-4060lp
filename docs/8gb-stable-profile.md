# 8 GB NVIDIA stable profile

A standing set of switches and code changes measured stable on an 8 GB NVIDIA
laptop GPU. This is the combination the `scarlett-fox-8gb-stable` branch is
verified against. Everything here was reached by single-variable A/B tests;
nothing is a guess.

> ## MANDATORY before first run: full pre-warm
>
> The numbers above are only reachable after a **full shader + pipeline
> pre-warm**. Do not skip it.
>
> - Shaders: **25 782** translated (`victory.exe shaders <shaders.rpf>`)
> - Pipelines: **83 737** pre-built (`victory.exe warm --jobs 32`, ~8 min)
> - Total coverage: **100 %** — every shader and every pipeline.
>
> Without it the first session translates while playing: severe compile
> stalls on entering scenes, and character faces can be drawn wrong for that
> session. After the full warm every scene is compile-stall-free and faces are
> correct from the first frame. The warm result is cached, so later starts
> skip it; an incremental warm (`victory.exe warm --jobs 16`) only fills in
> newly seen pipelines after a session.

## Runtime environment

| item | value |
|---|---|
| GPU | RTX 4060 Laptop, **8 GB VRAM** |
| CPU | i9-14900HX |
| System RAM | **32 GB** (currently saturated under load) |
| OS | Windows |
| Build | `cargo build --release -p victory` |
| Title console mode | `series-s` |

> **Memory is the current ceiling.** The 32 GB host RAM is pinned full during
> heavy scenes (shader translation tables, residency staging, pipeline book).
> A host with **48 GB or more** is expected to breathe and lift the heavy-scene
> floor. VRAM (8 GB) is already budgeted and stable at ~6.4/7.2 GB; the
> remaining headroom is on the host-RAM side.

## Performance (measured, stable)

| scene | frame rate |
|---|---|
| Heavy / complex scene (~3000-3600 draws) | **~10 fps** |
| Light / simple scene (~1200 draws) | **18-20 fps** |

Compared with the previous best profile (cool_fox_8gb) this is roughly a **3x**
lift (5.0-5.7 -> 10-20 fps), frame time down ~65 % (174-197 ms -> 50-100 ms).

## What was changed (code)

This branch (`scarlett-fox-8gb-stable`) sits on `scarlett-fox` and adds one
ported piece plus the standing switch set.

### Ported from cool_fox_8gb: title-patch hooks

scarlett-fox was missing the title-patch hooks module. Three files, ported from
the cool_fox_8gb loader, commit `8cd56e9`:

- `crates/victory-loader/src/hooks.rs` (new, 258 lines): `disarm_watchdog()` and
  `resolution_levers()`, each checked against the 1.0.2.1 title hash.
  `RENDER_SCALE` patches both the dynamic-resolution factor and the FSR/own-
  upscaler load; `OWN_UPSCALER` toggles the self-reconstruction path.
- `crates/victory-loader/src/lib.rs`: declare the windows-gated `hooks` module.
- `crates/victory-loader/src/windows.rs`: invoke the hooks right after the image
  is mapped, before any title code runs.

This is the lever for the v2 profile (render at 0.5 -> 540p, reconstruct to
1080p). The v3 profile simply does not set the three env vars, so the code path
is inert.

### Already in scarlett-fox (carried, not re-done)

- `HALF_VIEWS` / `D16_BITS` — fix frozen faces and black splotches (code default on).
- `NAN_GUARD` — fix black spots (code default on).
- 26 `wave64 -> wave32` translation fixes in `emit/mod.rs` — hair shadow, water
  volumetrics, particle, decals no longer dropped (0 failures vs 26 before).
- `VICTORY_PORT_CONSTANTS` — 174 MB constant heap read straight by the card, 0 fills.
- `VICTORY_TEXBACK_ASYNC` — async texture read-back.
- Descriptor sync five-piece (`SYNC_IN_PLACE` / `SPANS_QUICK` / `SYNC_FINE` /
  `HEAP_SYNC_FIRST` / `HEAP_SYNC_AT_SUBMIT`) — NVIDIA descriptor-heap fix-up.
- `VICTORY_PAGE_POOL` + `STAGING_PACK` — ~1.2 GB VRAM saving.
- `VICTORY_LEAVE_OUT` — skip an 11.85 ms decal-defrag pipeline.

## Optimisations realised (the standing switch set)

Grouped by what they buy. Only the three hooks vars change between v3 and v2;
the rest is shared.

### Face fix triad — correct character faces

| var | value | regression if changed |
|---|---|---|
| `VICTORY_RELAY` | `1` | relay path for texture residency |
| `VICTORY_CARD_STEPS` | `0` | `2` stretches character bodies |
| `VICTORY_TEXTURE_NO_WAIT` | `0` | `1` gives rainbow skin |

### 8 GB VRAM budget + page pool — keeps VRAM at ~6.4/7.2 GB

| var | value |
|---|---|
| `VICTORY_DYNAMIC_SLOTS` | `524288` |
| `VICTORY_MAX_PRELUDES` | `32` |
| `VICTORY_CARD_BUFFERS_MB` | `1024` |
| `VICTORY_CARD_WINDOWS_MB` | `512` |
| `VICTORY_TEXTURE_MIP_DROP` | `1` |
| `VICTORY_TEXTURE_ROOM_PERCENT` | `94` |
| `VICTORY_TEXTURE_RAM_CAPS` | `0` |
| `VICTORY_PAGE_POOL` | `1` |
| `VICTORY_STAGING_PACK` | `1` |
| `VICTORY_LEVELS_ON_DEMAND` | `0` |

`MIP_DROP=1` is mandatory on 8 GB (`=0` overflows VRAM and goes black).
`RAM_CAPS=0` removes a redundant host-RAM soft cap that live-locked texture
upload (297 MB retransmit versus 13843 MB with the cap on); critical-OOM
protection stays on. No-trade-off win, not a budget cut.

### CPU submit & upload — cuts prepare time ~35 %

| var | value |
|---|---|
| `VICTORY_WAIT_RESIDENT` | `0` |
| `VICTORY_JOIN_COPIES` | `0` |
| `VICTORY_REFRESH_ONCE` | `1` |
| `VICTORY_CARD_REHASH_RUNS` | `1` |
| `VICTORY_BACK_OWN_VIEW` | `1` |
| `VICTORY_WIDE_MERGE` | `1` |
| `VICTORY_MIRROR_FAST` | `1` |
| `VICTORY_PIPELINE_WAIT_MS` | `20` |
| `VICTORY_ASYNC_SUBMIT` | `1` |
| `VICTORY_THIN` | `1` |
| `VICTORY_QUEUE2` | `1` |
| `VICTORY_INDIRECT_WINDOW` | `1` |
| `VICTORY_COPY_PLAIN` | `1` |
| `VICTORY_WIDE_TEXTURES` | `1` |
| `VICTORY_INDIRECT_GATHER` | `1` |
| `VICTORY_LATE_WAIT_LISTS` | `1024` |
| `VICTORY_CARD_FILLS_BATCH` | `0` |
| `VICTORY_GATHER_DISPATCH` | `0` |
| `VICTORY_WIDE_BACK` | `1` |
| `VICTORY_RELAY_COPY` | `1` |
| `VICTORY_INDIRECT_BATCH` | `2` |
| `VICTORY_MAP_THREADS` | `1` |
| `VICTORY_CARD_AWAKE` | `0` |
| `VICTORY_SHOW_AFTER` | `1` |
| `VICTORY_JOIN_PARTS` | `8` |
| `VICTORY_UPLOAD_AHEAD` | `1` |
| `VICTORY_CARD_BUFFERS_MIN_KB` | `64` |

`THIN=1` parallelises list-call translation across 8 threads. The scarlett-fox
author found no gain and 2x long frames on a 7900 XTX / 64 GB host; on this
8 GB / 32 GB host the bottleneck is CPU, so THIN is a win here (+26 % heavy
scene, every metric improved, no regression). Measured, not assumed.

### Memory, upload and draw set-up

| var | value |
|---|---|
| `VICTORY_POOL_DISCARD` | `1` |
| `VICTORY_FILL_TITLE` | `1` |
| `VICTORY_PARTIAL_DELTA` | `1` |
| `VICTORY_BAKE_DELTA` | `1` |
| `VICTORY_MAP_LOCK_FINE` | `1` |
| `VICTORY_POOL_CAP` | `1` |
| `VICTORY_TABLE_MEMO` | `1` |
| `VICTORY_LIST_ALIAS_EXACT` | `1` |
| `VICTORY_LIST_HOLD` | `1` |
| `VICTORY_EARLY_TEXTURES_MS` | `40` |
| `VICTORY_BAKE_TEXTURES_MS` | `10000` |
| `VICTORY_HEAP_PASS_MAX` | `0` |
| `VICTORY_HEAP_CHANGED_MAX` | `0` |
| `VICTORY_WC_NO_BACK` | `1` |
| `VICTORY_WC_NO_BACK_MIN_KB` | `1024` |
| `VICTORY_SOFT_VIEWS` | `copies` |
| `VICTORY_SAMPLERS_MADE` | `1` |
| `VICTORY_TABLE_NAMED_ONLY` | `1` |
| `VICTORY_QUEUE_MARKS` | `1` |

### Descriptor sync — NVIDIA descriptor-heap fix-up

| var | value |
|---|---|
| `VICTORY_SYNC_IN_PLACE` | `1` |
| `VICTORY_SPANS_QUICK` | `1` |
| `VICTORY_SYNC_FINE` | `1` |
| `VICTORY_HEAP_SYNC_FIRST` | `1` |
| `VICTORY_HEAP_SYNC_AT_SUBMIT` | `1` |

### Ported wins

| var | value | effect |
|---|---|---|
| `VICTORY_PORT_CONSTANTS` | `1` | 174 MB constant heap read straight by the card, 0 fills |
| `VICTORY_LEAVE_OUT` | `02384a60fda6f2d0` | skip an 11.85 ms decal-defrag pipeline |
| `VICTORY_EARLY_DEPTH` | `1` | material-class depth plane current before the tiling pass |

### Ambient light (no ray tracing)

```
VICTORY_AMBIENT=0.8
VICTORY_AMBIENT_AIR=1.5
```

### Bookkeeping

```
VICTORY_PIPELINE_BOOK=1
VICTORY_LOG=info
VICTORY_FRAME_INTERVAL_MS=16.667
```

### Auto start (press through the start screens)

```
VICTORY_AUTO_INPUT='d>=15,rep(A,1,d<10),w3,d>=20,w1,rep(A,1,d>=35),w1.5,Down,w7,Down,w0.6,A,w1.5,A,w0.7,Down,w0.5,A,w0.7,Down,w0.5,A'
```

## Two recommended profiles

Both share the switch set above. They differ only in the three title-patch env vars.

### v3 — native 1080p (recommended)

Do **not** set `VICTORY_NO_WATCHDOG`, `VICTORY_RENDER_SCALE` or
`VICTORY_OWN_UPSCALER`. The hooks code path is not taken; the title runs its
native Series S 1080p path. Sharper picture, and the heavy-scene floor holds.

- Picture: 1920x1080 native, sharp
- VRAM: ~6412 / 7188 MB
- No crashes

### v2 — 540p + own upscaler (fallback)

```
VICTORY_NO_WATCHDOG=1
VICTORY_RENDER_SCALE=0.5
VICTORY_OWN_UPSCALER=1
```

Renders at 960x540 and lets the title's own upscaler reconstruct to 1080p.
Softer picture; use where the native path is too heavy.

- Picture: 960x540 -> 1080p, soft

`RENDER_SCALE` outside [0.5, 0.65] is not viable on this 8 GB card: 1.0 crashes
(see Known issues), below 0.5 is too coarse.

## Build & pre-warm

1. Build the release binary:
   ```
   cargo build --release -p victory
   ```
2. Pre-translate the shaders once (a few minutes; remembered in the cache).
   This produces **25 782** translated shaders:
   ```
   victory.exe shaders <shaders.rpf in your game dir>
   ```
3. **Full pipeline pre-warm — mandatory.** Builds all **83 737** pipelines
   ahead of time so no scene ever compiles while playing:
   ```
   victory.exe warm --jobs 32
   ```
   ~8 min for the full set. After this, shader coverage (25 782) + pipeline
   coverage (83 737) = **100 %**, and every scene is compile-stall-free with
   correct faces from the first frame. The result is cached, so later starts
   skip it; run `victory.exe warm --jobs 16` after a session to incrementally
   fill in only the pipelines that session newly saw.

## Known issues

1. **Host RAM saturated.** 32 GB is pinned full under heavy scenes; the
   heavy-scene floor (~10 fps) is partly memory-bound. A 48 GB host is the
   expected next step and should lift the floor.

2. **Water surface dark blocks.** A row of regular dark rectangles on the ocean
   horizon (a volumetric tile symptom). `CS_TransmissionVolumetrics_Tiled`
   needs wave-wide widening to translate on NVIDIA; `VICTORY_LEAVE_OUT`
   currently skips one such pipeline. Removing `LEAVE_OUT` is the next
   experiment.

3. **`RENDER_SCALE=1.0` with hooks crashes.** The hooks patch the title binary;
   at scale 1.0 it crashes in Game Init frame 0 (title Breakpad). Use v3 (hooks
   off, native 1080p) or keep `RENDER_SCALE` in [0.5, 0.65].

4. **8 GB VRAM is a hard ceiling.** `MIP_DROP=0` overflows VRAM and goes black;
   `MIP_DROP=1` is mandatory. The headroom (~0.8 GB) is small.

## Do-not-touch (each was tried and regressed)

- `VICTORY_TEXTURE_NO_WAIT=1` -> rainbow skin
- `VICTORY_CARD_STEPS=2` -> stretched character bodies
- `VICTORY_TEXTURE_MIP_DROP=0` -> VRAM overflow, black screen
- `VICTORY_TEXTURE_RAM_CAPS=1` -> texture upload live-lock (13.8 GB retransmit)
- `VICTORY_RENDER_SCALE=1.0` with hooks -> Game Init crash (title Breakpad)
