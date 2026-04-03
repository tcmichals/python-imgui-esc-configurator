# RISC-V Toolchain: Manual Installation

To ensure a deterministic and package-manager-free build environment, we use a manual installation of the **xPack RISC-V GCC** toolchain.

## Installation Steps

1.  **Create the Tools Directory**:
    ```bash
    mkdir -p ~/.tools
    ```

2.  **Download the xPack RISC-V GCC**:
    Visit the [xPack RISC-V GCC Releases](https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases) and download the **Linux x64** tarball.
    
    *Direct download example (v13.2.0-2):*
    ```bash
    wget https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v13.2.0-2/xpack-riscv-none-elf-gcc-13.2.0-2-linux-x64.tar.gz
    ```

3.  **Extract to ~/.tools**:
    ```bash
    tar -xzf xpack-riscv-none-elf-gcc-13.2.0-2-linux-x64.tar.gz -C ~/.tools
    ```

4.  **Verify the Installation**:
    ```bash
    ~/.tools/xpack-riscv-none-elf-gcc-13.2.0-2/bin/riscv-none-elf-gcc --version
    ```

## Project Configuration

Our CMake build system is configured to look for the toolchain in `~/.tools`. 

If you have installed a different version, update the **`riscv32-toolchain.cmake`** file or pass the path to CMake:

```bash
cmake -DRISCV_TOOLCHAIN_PATH=~/.tools/my-riscv-version ..
```

## Why No xpm/npm?
By sticking to a manual directory in `~/.tools`, we avoid global dependency pollution and keep the core flight-controller build system portable across different Linux environments without needing a JavaScript runtime.
