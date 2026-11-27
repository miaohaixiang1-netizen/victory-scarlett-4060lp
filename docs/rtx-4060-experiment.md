# RTX 4060 Laptop experimental settings

This is a snapshot of settings used in a local Windows test on an i9-14900HX, RTX 4060 Laptop (8 GB VRAM), and 32 GB RAM. The translation and budget switches are already implemented in this repository; this snapshot enables them. It is experimental, not a validated default or a stability guarantee.

In Git Bash, source `scripts/rtx-4060-laptop-experimental.env.sh` in the same shell before invoking the existing `victory.exe` run command. Set your own game, cache and data paths as needed. The snapshot omits local paths, automatic input, and the local HUD. It includes texture mip dropping, so do not assume all settings preserve image quality.

The snapshot enables `VICTORY_WAVE_PAIRS_FIRST=1`, sets `VICTORY_TEXTURE_ROOM_PERCENT=94` and `VICTORY_CARD_ROOM_FOR_TARGETS_MB=1536`. A separate refresh-range experiment (`VICTORY_REFRESH_PAGES=1`) was still in progress and is not included.

In one comparison with roughly 3,000–5,000 draws per frame, the paired-wave configuration averaged about 13.5 FPS with the earlier reserve and about 13.1 FPS with the more aggressive reserve. The camera views were not identical, so these figures do not establish a causal performance difference. Performance, image correctness and stability require independent testing; shader and pipeline warm-up can affect results.
