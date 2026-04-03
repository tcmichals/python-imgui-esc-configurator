---
title: Pico 2 Firmware Implementation Plan
doc_type: design
status: historical
audience:
	- human
	- ai-agent
	- developer
canonicality: supporting
subsystem: firmware
purpose: Capture original architecture planning, system topology rationale, and resource allocation ideas.
related_docs:
	- ../README.md
	- README.md
	- DOC_METADATA_STANDARD.md
	- SYSTEM_HOW_IT_WORKS.md
verified_on: 2026-03-22
---

# Pico 2 Firmware Implementation Plan

> **AI doc role:** supporting architecture/planning context
>
> **Use this in prompts for:** original design intent, system topology rationale, hardware resource allocation ideas
>
> **Warning:** this is planning-oriented context and should be cross-checked against current code and canonical docs

See also:

- `DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

## Overview
This document outlines the architectural implementation for porting the `SPIQuadCopter` hardware from an FPGA (Tang Nano 20K / Arty S7) to the Raspberry Pi Pico 2 (RP2350).

### System Topology
- **Host (Pi Zero 2W Running Linux):** Executes the main Betaflight/INAV flight loop (PID calculations, sensor fusion, gyro reading, high-level control) under a Linux environment.
- **Co-Processor (Pico 2):** Acts as a dedicated high-speed, real-time hardware I/O proxy. It receives motor/LED demands from the Pi Zero 2W via SPI and returns PWM/Telemetry data, ensuring the Linux scheduler does not interfere with microsecond-critical drone hardware timing.

#### Host-to-Coprocessor Link: SPI vs. USB Serial
The link between the Pi Zero 2W and the Pico 2 strictly utilizes **Hardware SPI** rather than USB Serial.
- **Why SPI?** SPI is completely synchronous and DMA-mappable with near-zero latency. When the Pi Zero finishes an 8kHz PID calculation, it slams the clock line instantly, guaranteeing data arrives at the ESCs within nanoseconds synchronously without drift.
- **Why not USB?** USB operates on a 1ms (or 125µs) polling schedule using the OS software stack. The Linux kernel buffers packets, which introduces severe non-deterministic jitter. This batched delivery causes stuttering in real-time DSHOT/motor updates, destroying flight stability.

## 1. PWM Decoding (6 Channels)
- **Mechanism:** Dual hardware PWM slices configured in Input Edge-Capture Mode.
- **Resource:** 6 Hardware PWM channels (0 PIO State Machines required).
- **Operation:** The pins will clock the hardware counter directly upon receiving high edges. The CPU periodically checks for overflow (timeout) and captures the precise pulse width dynamically, handling receiver failsafes exactly like the FPGA approach.

## 2. NeoPixel Handling (Adafruit RGBW Strip)
- **Mechanism:** Programmable I/O (PIO).
- **Resource:** 1 PIO State Machine.
- **Operation:** Uses the canonical Pico C/C++ SDK `ws2812` PIO assembly example. The CPU writes 32-bit RGBW values to the TX FIFO through a DMA channel, and the PIO generates the required 800kHz single-wire timing.

## 3. DSHOT Output (4 Motors)
- **Mechanism:** Programmable I/O (PIO), DSHOT600.
- **Resource:** 4 PIO State Machines (or 1 using side-set multiplexing).
- **Operation:** Configures a generic DSHOT timing PIO script. The CPU generates the 16-bit DSHOT frames (Command, Throttle, Telemetry request, CRC) and writes them to the PIO's TX FIFO. The PIO completely manages the precision bit-banging required to drive the 4 ESCs identically to the original `dshot_out.v`.

## 4. ESC-Config Passthrough (Serial Port / Half-Duplex)
- **Mechanism:** Hardware UARTs multiplexed or a discrete PIO UART bidirectional engine.
- **Resource:** 1 Hardware UART or 1 PIO State Machine.
- **Operation:** Bounces serial data bidirectionally between the USB CDC (Virtual COM Port) and the 1-wire/2-wire ESC telemetry configuration connection, effectively allowing the BLHeli configuration software to interact directly with the multi-rotors through the flight controller.

## 5. Main SPI Protocol (Flight Controller SPI Slave)
- **Mechanism:** RP2350 dedicated SPI Hardware (PL022).
- **Resource:** `SPI0` or `SPI1` configured as an SPI Slave.
- **Operation:** Accurately mimics the FPGA's 8-bit or 16-bit payload framing protocol (e.g. replacing `spi_slave.sv` and `wb_spisystem`). This runs at tens of MHz using DMA to accept command payloads and transmit status back without jitter.
