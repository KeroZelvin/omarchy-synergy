# Receiving input bridge patches

These patches modify [iamnarayana/wayland-kdeconnect-fix](https://github.com/iamnarayana/wayland-kdeconnect-fix), based on upstream commit `ea55f66c8238235983d60d381bf2abe1fed50043`. Preserve its [MIT license](UPSTREAM-LICENSE) and original project history. The upstream project was forked from [gfhdhytghd/hypr-kdeconnect-fix](https://github.com/gfhdhytghd/hypr-kdeconnect-fix).

Apply in order:

1. `0001-native-caller.patch`: verify native Synergy callers through the caller PID and exact executable path. Adds an optional documented service sandbox override.
2. `0002-eis-input.patch`: libeis 1.6 input handling, pointer capabilities, modifier propagation and static multi-output bounds.
3. `0003-keyboard-transitions.patch`: suppress duplicate key-down/unmatched-release transitions to prevent stuck modifiers, including the Shift/Codex regression.

The first patch forms one proposed upstream PR; the second and third form the other. They are local review candidates, not published or accepted upstream. Patch headers use the owner's established public Git identity. Original upstream authorship and MIT notices are preserved.

From the omarchy-synergy repository root:

```bash
mkdir -p build
git clone https://github.com/iamnarayana/wayland-kdeconnect-fix.git build/input-bridge
git -C build/input-bridge checkout --detach ea55f66c8238235983d60d381bf2abe1fed50043
git -C build/input-bridge apply ../../patches/input-bridge/0001-native-caller.patch ../../patches/input-bridge/0002-eis-input.patch ../../patches/input-bridge/0003-keyboard-transitions.patch
```

Start with a fresh checkout and apply once. Read the resulting `build/input-bridge/docs/synergy.md` and `docs/input-compatibility.md`, then follow [the setup guide](../../docs/OMARCHY-GUIDE.md) for dependencies, build and deliberate activation on the receiver. No source binary is distributed here. The bridge does not implement portal clipboard support.

Known limits: static output bounds, unqualified fractional scaling/rotation/hotplug and broader physical keyboard layouts; discrete sub-v120 scroll fractions are truncated. The optional caller-verification service override reduces filesystem isolation and is never installed automatically.
