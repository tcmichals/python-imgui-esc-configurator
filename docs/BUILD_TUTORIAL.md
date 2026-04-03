---
title: Pico 2 Build and Toolchain Setup Tutorial
doc_type: guide
status: active
audience:
      - human
      - ai-agent
      - developer
canonicality: canonical
subsystem: firmware
purpose: Document the build environment, toolchain setup, compile workflow, and flashing process for the Pico firmware.
related_docs:
      - ../README.md
      - README.md
      - DOC_METADATA_STANDARD.md
verified_on: 2026-03-22
---

# Pico 2 Flight Controller — Build & Toolchain Setup Tutorial

> **AI doc role:** canonical build/setup reference
>
> **Use this in prompts for:** build environment setup, toolchain installation, compile/flash workflow, onboarding contributors
>
> **Do not infer from this doc alone:** runtime protocol behavior or active ESC passthrough semantics

See also:

- `DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

## Overview

This guide walks you through everything needed to compile the Pico 2 flight controller firmware from scratch on a Linux machine, covering:
1. Installing the ARM cross-compiler toolchain
2. Cloning the Pico SDK
3. Setting up environment variables
4. Building the project
5. Flashing the `.uf2` firmware onto the Pico 2

---

## Prerequisites

You will need `cmake` (already installed on this system) and `git`:
```bash
# Verify cmake is ready
cmake --version   # Should show 3.13 or newer
git --version     # Should show git 2.x
```

---

## Step 1: Install ARM Cross-Compiler Toolchain

> ⚠️ **Important:** The `.msi` installer on the ARM downloads page is for **Windows only**.
> On Linux you need the **`.tar.xz` tarball** for `x86_64`.

Download the correct Linux bare-metal toolchain:

```bash
# Create tools directory
mkdir -p "$HOME/.tools/gcc-arm-none"
cd "$HOME/.tools/gcc-arm-none"

# Download the LINUX x86_64 arm-none-eabi toolchain (v15.2)
wget "https://developer.arm.com/-/media/Files/downloads/gnu/15.2.rel1/binrel/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi.tar.xz"

# Extract it
tar xf arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi.tar.xz

# Rename for consistency with build config
mv arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi gcc-arm-none-eabi-15.2

# Verify it works
"$HOME/.tools/gcc-arm-none/gcc-arm-none-eabi-15.2/bin/arm-none-eabi-gcc" --version
```

Expected output:
```
arm-none-eabi-gcc (Arm GNU Toolchain 15.2.Rel1) 15.2.1
```

> **Key naming explained:**
> - `x86_64` = your Linux PC
> - `arm-none-eabi` = **bare-metal ARM target** (no OS on the target — correct for Pico 2)
> - **NOT** `arm-none-linux-gnueabihf` (that's for Linux-running ARM targets like RPi)


---

## Step 2: Add the Toolchain to your PATH

Add the following to your `~/.bashrc` (or `~/.zshrc` if you use Zsh):
```bash
# ARM Toolchain for Pico 2
export ARM_TOOLCHAIN="$HOME/.tools/gcc-arm-none/gcc-arm-none-eabi-15.2/bin"
export PATH="$ARM_TOOLCHAIN:$PATH"
```

Then reload your shell:
```bash
source ~/.bashrc

# Verify it resolves
arm-none-eabi-gcc --version
```


---

## Step 3: Clone the Raspberry Pi Pico SDK

The Pico SDK is the official C/C++ framework required to compile any Pico project.
Clone it alongside your tools:

```bash
# Suggested location
mkdir -p "$HOME/.tools"
cd "$HOME/.tools"

# Clone with all submodules (required!)
git clone --recurse-submodules https://github.com/raspberrypi/pico-sdk.git

# Verify the SDK structure
ls pico-sdk/src/rp2_common/hardware_spi/
```

---

## Step 4: Set the PICO_SDK_PATH Environment Variable

Add this to your `~/.bashrc` alongside the toolchain PATH:
```bash
# Pico SDK
export PICO_SDK_PATH="$HOME/.tools/pico-sdk"
```

Reload:
```bash
source ~/.bashrc
echo $PICO_SDK_PATH   # Should print the path
```

---

## Step 5: Build the Flight Controller

The project uses a **CMake toolchain file** (`cmake/toolchain-arm-none-eabi.cmake`) to
specify the cross-compiler path. Edit that file first if your toolchain is in a different location.

```bash
cd <repository-root>

# Configure (one time)
cmake -DPICO_BOARD=pico2 \
      -DCMAKE_BUILD_TYPE=Release \
      -DPICO_SDK_PATH="$PICO_SDK_PATH" \
      -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-arm-none-eabi.cmake \
      -B build -S .

# Build
cmake --build build --parallel
```

To **clean and rebuild**:
```bash
cmake --build build --target clean
cmake --build build --parallel
```

To **reconfigure** (e.g. after changing CMakeLists.txt):
```bash
rm -rf build
cmake -DPICO_BOARD=pico2 \
      -DCMAKE_BUILD_TYPE=Release \
      -DPICO_SDK_PATH="$PICO_SDK_PATH" \
      -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-arm-none-eabi.cmake \
      -B build -S .
cmake --build build --parallel
```


Expected output at the end:
```
[100%] Linking CXX executable msp_bridge.elf
...
[100%] Built target msp_bridge
```

The following output files are generated:
| File | Use |
|------|-----|
| `msp_bridge.uf2` | **Flash to Pico 2** (drag and drop) |
| `msp_bridge.elf` | Debug with GDB/OpenOCD |
| `msp_bridge.bin` | Raw binary |
| `msp_bridge.hex` | Intel HEX format |

---

## Step 6: Flash the Firmware

### Option A — USB UF2 Drag and Drop (Recommended)

1. Hold the **BOOTSEL** button on the Pico 2
2. While holding, plug in the USB cable to your PC
3. Release BOOTSEL — the Pico 2 mounts as a drive called `RPI-RP2`
4. Copy the firmware:
```bash
cp build/msp_bridge.uf2 /media/$USER/RPI-RP2/
```
5. The Pico automatically reboots and starts running the firmware immediately.

### Option B — OpenOCD (SWD Debug Probe)

If you have a Raspberry Pi Debug Probe or a second Pico running `picoprobe`:
```bash
openocd -f interface/cmsis-dap.cfg \
        -f target/rp2350.cfg \
        -c "adapter speed 5000" \
      -c "program build/msp_bridge.elf verify reset exit"
```

---

## Step 7: Verify via USB Serial

Once flashed, the Pico 2 will appear as a USB CDC Serial port (Virtual COM Port).
Connect to it to see the debug startup output:

```bash
# Find the port name (usually /dev/ttyACM0 or /dev/ttyUSB0)
ls /dev/ttyACM*

# Connect at any baud rate (USB CDC ignores baud rate)
screen /dev/ttyACM0 115200
# or
minicom -D /dev/ttyACM0 -b 115200
```

Expected startup output:
```
========================================
  Pico 2 Flight Controller v0.1
  RP2350 @ 150MHz
  DSHOT600 | WS2812 RGBW | 6-CH PWM
  SPI Slave (WishboneSPI Protocol)
========================================

DSHOT: Motor 1 on GP6 (SM0)
DSHOT: Motor 2 on GP7 (SM1)
DSHOT: Motor 3 on GP8 (SM2)
DSHOT: Motor 4 on GP9 (SM3)
NeoPixel: 16 LEDs on GP10 (PIO1/SM0)
PWM Decode: CH1 on GP0 (slice 0) at 1us/tick
...
SPI Slave: GP16(MOSI) GP17(CS) GP18(SCK) GP19(MISO) at 10MHz
Arming ESCs (sending zero throttle)...
ESCs armed. Starting flight loop.
```

---

## Convenience Script

Save this as `build.sh` in the repository root for quick rebuilds:

```bash
#!/bin/bash
set -e

export PICO_SDK_PATH="$HOME/.tools/pico-sdk"
export PATH="$HOME/.tools/gcc-arm-none/gcc-arm-none-eabi-15.2/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake -DPICO_BOARD=pico2 \
      -DCMAKE_BUILD_TYPE=Release \
      -DPICO_SDK_PATH="$PICO_SDK_PATH" \
      ..

make -j$(nproc)

echo ""
echo "Build complete! Flash with:"
echo "  cp $BUILD_DIR/msp_bridge.uf2 /media/\$USER/RPI-RP2/"
```

Make it executable:
```bash
chmod +x build.sh
```

Then run `./build.sh` from the project root whenever you want to rebuild.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `arm-none-eabi-gcc not found` | Check `$PATH` includes your toolchain `bin/` dir |
| `PICO_SDK_PATH not found` | Ensure `export PICO_SDK_PATH=` is in `~/.bashrc` and you ran `source ~/.bashrc` |
| `pioasm not found` | Let CMake handle it — `pico_generate_pio_header()` compiles `dshot.pio` automatically |
| `hardware/spi.h not found` in IDE | The Pico SDK headers are only available inside the CMake environment. IDE warnings are expected — the build is the source of truth |
| Pico 2 not mounting as `RPI-RP2` | Hold BOOTSEL **before** plugging in USB, not after |
| USB Serial `/dev/ttyACM0` permission denied | Add yourself to the `dialout` group: `sudo usermod -aG dialout $USER` then log out/in |
