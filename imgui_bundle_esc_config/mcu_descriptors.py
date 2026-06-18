"""MCU descriptor table for ESC bootloader identification.

Maps ESC MCU signatures (from the init_flash response) to hardware-specific
parameters needed for correct settings read/write/erase operations.

This table mirrors the JavaScript reference implementation:
  - webapp/esc-configurator/src/utils/Hardware/Silabs.js
  - webapp/esc-configurator/src/utils/Hardware/Arm.js

The init_flash (0x37) response payload contains:
  - bytes 0-1: MCU signature (big-endian)
  - byte 3:   interfaceMode (1=SiLabs, 2=Atmel, 3=SimonK, 4=ARM)

Usage:
    signature = int.from_bytes(init_response.params[0:2], 'big')
    mcu = get_mcu_by_signature(signature)
    if mcu:
        address = mcu.eeprom_offset
        page_size = mcu.page_size
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MCUDescriptor:
    """Hardware descriptor for an ESC microcontroller."""

    name: str
    signature: int
    eeprom_offset: int
    page_size: int
    flash_size: int
    flash_offset: int = 0x00
    firmware_start: int = 0x00
    bootloader_address: Optional[int] = None
    lockbyte_address: Optional[int] = None


# ---------------------------------------------------------------------------
# Silabs EFM8 MCU descriptors (BLHeli_S / Bluejay)
# Source: webapp/esc-configurator/src/utils/Hardware/Silabs.js
# ---------------------------------------------------------------------------
SILABS_MCUS: dict[int, MCUDescriptor] = {
    0xE8B1: MCUDescriptor(
        name="EFM8BB10x",
        signature=0xE8B1,
        eeprom_offset=0x1A00,
        page_size=512,
        flash_size=8192,
        bootloader_address=0x1C00,
        lockbyte_address=0x1FFF,
    ),
    0xE8B2: MCUDescriptor(
        name="EFM8BB21x",
        signature=0xE8B2,
        eeprom_offset=0x1A00,
        page_size=512,
        flash_size=8192,
        bootloader_address=0x1C00,
        lockbyte_address=0xFBFF,
    ),
    0xE8B5: MCUDescriptor(
        name="EFM8BB51x",
        signature=0xE8B5,
        eeprom_offset=0x3000,
        page_size=2048,
        flash_size=63485,
        bootloader_address=0xF000,
        lockbyte_address=0xF7FF,
    ),
}

# ---------------------------------------------------------------------------
# ARM MCU descriptors (AM32 / AT32)
# Source: webapp/esc-configurator/src/utils/Hardware/Arm.js
# ---------------------------------------------------------------------------
ARM_MCUS: dict[int, MCUDescriptor] = {
    # AM32 default — signature 0x0000 is a fallback for unknown ARM ESCs
    0x0000: MCUDescriptor(
        name="AM32 (default)",
        signature=0x0000,
        eeprom_offset=0x7C00,
        page_size=1024,
        flash_size=32768,
    ),
    # AT32 variant
    0x1F32: MCUDescriptor(
        name="AT32F421",
        signature=0x1F32,
        eeprom_offset=0xF800,
        page_size=1024,
        flash_size=65536,
    ),
}

# Combined lookup table: signature -> MCUDescriptor
_ALL_MCUS: dict[int, MCUDescriptor] = {**SILABS_MCUS, **ARM_MCUS}


def get_mcu_by_signature(signature: int) -> Optional[MCUDescriptor]:
    """Look up an MCU descriptor by its signature value.

    Args:
        signature: 16-bit MCU signature from init_flash response bytes 0-1.

    Returns:
        MCUDescriptor if found, None otherwise.
    """
    return _ALL_MCUS.get(signature)


def get_default_mcu_for_interface_mode(interface_mode: int) -> Optional[MCUDescriptor]:
    """Get a sensible default MCU descriptor when the exact signature is not in the table.

    This provides fallback EEPROM addresses based on the bootloader class so that
    settings operations can proceed even for MCU signatures we don't recognize.

    Args:
        interface_mode: The interfaceMode byte from init_flash response (byte 3).
            1 = SiLabs (imSIL_BLB), 4 = ARM (imARM_BLB)

    Returns:
        MCUDescriptor with default values for the given interface mode, or None
        for unsupported modes (Atmel/SimonK use EEPROM commands instead).
    """
    if interface_mode == 1:
        # Default Silabs: assume EFM8BB21x (most common BLHeli_S/Bluejay MCU)
        return SILABS_MCUS[0xE8B2]
    elif interface_mode == 4:
        # Default ARM: assume AM32 default
        return ARM_MCUS[0x0000]
    return None


def compute_erase_page_number(eeprom_offset: int, page_size: int) -> int:
    """Compute the page erase number for the EEPROM settings region.

    Mirrors the JavaScript reference calculation:
        eepromOffset / pageSize * pageMultiplier
    where pageMultiplier = 4 if pageSize != 512, else 1.

    Args:
        eeprom_offset: The EEPROM base address (e.g. 0x1A00).
        page_size: The flash page size in bytes (e.g. 512).

    Returns:
        The page number to pass to the cmd_DevicePageErase command.
    """
    page_multiplier = 4 if page_size != 512 else 1
    return (eeprom_offset // page_size) * page_multiplier
