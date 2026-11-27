Local 4060 laptop reference files. These snapshots contain machine-specific paths and require adjustment before use elsewhere. Game data, saves, logs, caches, and binaries are not included.

The session monitor logs GPU, system RAM, and game-process working set/private bytes/page faults every 30 seconds and exits with the game. GPU timestamp reporting needs the diagnostics build and VICTORY_CARD_SPANS=1. VICTORY_READ_KEEP_MB=64 releases oversized per-thread texture read buffers after use.

VICTORY_SECTION_MB=2 is an experimental physical-memory mapping change with an RTX 4060 Laptop report showing fewer mapping-lock stalls. Pair it with VICTORY_PORT_CONSTANTS=0: splitting sections prevents the optional renderer port from mapping across one contiguous section. This local run confirms the split path loads, but does not establish a 30 fps result.

The launcher sends A repeatedly after 15 seconds until gameplay passes the 10-draw menu threshold, so an early tap cannot be consumed by a splash screen. Current paired-wave and VRAM-reservation settings remain experimental.
