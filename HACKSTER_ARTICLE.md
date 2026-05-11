# Beyond the Browser: Porting the ESC Configurator to Python and imgui-bundle

## 1. What is the ESC Configurator?

The **ESC Configurator** is a specialized tool used by drone pilots and engineers to communicate with Electronic Speed Controllers (ESCs). It acts as the "command center" for the hardware that drives the brushless motors on a quadcopter. 

This project specifically focuses on a desktop-native replacement for existing web-based tools, designed for both standard configuration and advanced hardware offloading research.

## 2. What does it do?

The configurator handles the critical tasks required to get a drone in the air and keep it running smoothly:
*   **Discovery:** Automatically detects how many ESCs are connected and what firmware they are running.
*   **Settings Management:** Allows users to change motor direction, PWM frequency, timing, and even custom startup melodies.
*   **Firmware Updates:** Downloads the latest **BLHeli_S** or **Bluejay** firmware from the cloud and flashes it to the hardware.
*   **Diagnostics:** Provides real-time visibility into the serial traffic and system logs, which is essential for debugging hardware issues.

## 3. Why is it a Web Application?

The original version (`esc-configurator.com`) was built as a web app to maximize accessibility. By using the browser, users could configure their hardware on any computer without needing to install specialized software or manage complex drivers. This "zero-install" experience made it the de-facto standard for the community.

## 4. Why did it require Google Chrome?

For years, the web-based configurator was essentially a "Chrome-only" tool. This was due to its reliance on the **WebSerial API**.
*   **Chromium Dominance:** WebSerial was a Chromium-only feature for a long time. Google Chrome and Microsoft Edge provided the native hooks needed for a website to talk directly to a USB/Serial device.
*   **The Firefox Stance:** Mozilla (Firefox) historically opposed WebSerial due to security and privacy concerns, arguing that giving websites direct access to hardware was too risky.
*   **The Future of Firefox:** As of 2025-2026, Firefox has begun implementing experimental support for WebSerial in Nightly builds, but for the stable, secure experience required by hardware tools, Chrome remains the primary host for the web-based version.

## 5. Why create a new one using Python and imgui-bundle?

While the web app is great for general use, a new desktop version was created to push the boundaries of **Hardware Offloading** (using FPGAs).
*   **Direct Integration:** By moving to Python, the project enables direct integration with Linux-based flight control systems and more flexible hardware access.
*   **Rich Aesthetics with ImGui:** The project uses `imgui-bundle` (a Python wrapper for Dear ImGui) to create a "pro-tool" interface. It supports a multi-window layout where users can watch live protocol traces in one window while adjusting settings in another.
*   **High-Performance Asyncio Kernel:** The application leverages an **asynchronous event loop** (`asyncio`) for its backend kernel. This provides non-blocking serial I/O and high throughput, allowing the GUI to remain perfectly responsive at 60 FPS even while streaming high-rate telemetry and processing complex protocol handshakes.

## 6. The AI-Assisted Porting Process

Instead of a simple rewrite, AI was used to perform a high-fidelity architectural port.
*   **Feature & Module Extraction:** AI analyzed the original JavaScript source code to create a complete **Feature List** and **Code Module List**. 
*   **The Feature Cache:** This research is documented in [WEBAPP_FEATURE_CACHE.md](https://github.com/tcmichals/python-imgui-esc-configurator/blob/main/imgui_bundle_esc_config/WEBAPP_FEATURE_CACHE.md). It maps every React component and utility in the web app to its corresponding Python implementation.
*   **Design Parity:** This approach ensured that subtle behaviors—like 4-way protocol retry logic and EEPROM decoding rules—were preserved exactly as they exist in the web version.
*   **Deep Firmware Analysis:** AI was also used to dive into the **Bluejay** and **BLHeli** assembly source code (found in the `rt-fc-offloader` ecosystem). This allowed for mapping out the exact EEPROM layouts and internal state machines, ensuring the Python implementation was "bit-perfect" for the hardware.

## 7. The Hardware Journey: From Legacy to Custom

The transition wasn't just about software; it required a rigorous hardware validation path:
*   **Phase 1: Legacy Validation:** Validation started with an **older, standard flight controller** to test the MSP implementation. This established a "known good" baseline for protocol compatibility.
*   **Phase 2: Custom PIO Offloading:** Once MSP was proven, a custom **Pico/PIO** implementation was created. This allowed for proving out new features and demonstrating how PIO (Programmable I/O) can handle complex DSHOT and PWM tasks with much higher precision than traditional software-based methods.
*   **Phase 3: RTL Determinism:** The final step was moving to **RTL on FPGA** (Tang Nano), achieving the deterministic performance required for safety-critical flight control.

## 8. How to switch between MSP and FCSP

The configurator is designed to be "Protocol Agnostic." 
*   In the **Connection Panel**, you can choose between legacy **MSP** (Multiwii Serial Protocol) or our new **FCSP** (Flight Controller Support Protocol).
*   The GUI itself doesn't care which one you pick; it sends "Feature Intent" commands to the backend, and the Python Worker handles the translation to the specific protocol packets.

## 9. The Pivot to FCSP: Why MSP Wasn't Enough

While the project started with MSP for baseline compatibility, a wall was eventually hit when working on the **FPGA (RTL) offloading** design. This led to the birth of **FCSP**.

### Why the Switch?
*   **The Processor Bottleneck:** The initial FPGA design attempted to use a **RISC-V SERV** core (a bit-serial processor) to keep the footprint minimal. However, it quickly became clear that parsing the legacy **MSP protocol** in software required significantly more processor performance than the SERV core could provide without sacrificing real-time determinism.
*   **The Overhead Barrier:** MSP was designed for serial links and low-rate telemetry. For a 90MHz FPGA design, the project required a protocol that could keep up with high-speed hardware framing without the overhead of legacy MSP byte-stuffing.
*   **Capability Blindness:** One of the biggest hurdles was "advertising" what the hardware could actually do. Legacy MSP makes it difficult to tell the UI that "this specific FPGA bitstream supports 4 ESCs but only 2 have DSHOT telemetry enabled." 
*   **Offloading Alignment:** A protocol was needed that fit the **Split Architecture** (Linux control-plane + deterministic FPGA I/O path). FCSP was designed from the ground up to support this "Offloader" model.

### The Hurdles Encountered
*   **State Synchronization:** Keeping the Python UI in sync with high-speed hardware state transitions was a challenge. This was solved using FCSP's **Type-Length-Value (TLV)** system for robust state advertisement.
*   **Handling Complexity:** Managing multiple ESCs over a single high-speed link required a more sophisticated addressing model than the standard 4-way passthrough provided.
*   **Migration Path:** Existing MSP setups were preserved. The challenge was met by building a "Dual-Path" worker that could fall back to MSP when FCSP wasn't available—a result of the modular Worker-as-Kernel design.

## The Asyncio Pivot: High-Performance Kernel

As the project moved toward high-rate telemetry and multi-ESC synchronization, the legacy threading model reached its limits. We have transitioned the backend kernel to a full **asyncio** architecture using `pyserial-asyncio`.

### Performance Insights
Our automated `pytest` benchmark suite revealed some critical findings that validated our architectural pivot:
- **The Overhead Myth:** We found that `asyncio` introduced a negligible **~3% overhead** for trivial, sequential setup tasks (like a single connection/disconnection). This dispelled the concern that an event loop would be too "heavy" for simple operations.
- **Concurrent Scaling:** The real win was observed during **interleaved workloads**. While a traditional threaded worker would struggle with "jitter" when reading telemetry from 4+ ESCs while simultaneously processing UI commands, the `asyncio` kernel handled these tasks with near-zero latency variations.
- **Zero-Block Responsiveness:** During slow 4-way protocol handshakes (which can take 500ms+), the `asyncio` kernel successfully yielded to other tasks, ensuring that background "Heartbeat" logs and UI responsiveness never stalled—a common failure mode in synchronous systems.

### The "Thread-Bridge" Challenge
One of the most critical lessons learned during this transition was the complexity of bridging the **ImGui UI Thread** with the **Asyncio Kernel Thread**. To avoid non-deterministic race conditions and "nasty" debugging sessions:
- **Rescheduling Commands:** We use `loop.call_soon_threadsafe()` to push commands into the kernel. This ensures the UI thread never touches the internal state of the `asyncio` event loop.
- **Standardized Event Pipes:** We use a standard thread-safe `queue.Queue` for the return path (Kernel → UI), creating a clean, unidirectional bridge between the asynchronous backend and the synchronous frontend.

This architecture ensures that the application remains robust and responsive, even when flooded with real-time data from the FPGA offloader.

## 10. First-Class Observability: Logging and Protocol Tracing

A key differentiator of this desktop tool is its focus on **Observability**. The goal is not just to hope things work; the project provides the tools to see *exactly* how they fail. The UI features two dedicated observability surfaces:
*   **The Log Window:** A user-facing stream of runtime events, errors, and status updates, featuring real-time filtering to help operators find the signal in the noise.
*   **The Protocol Trace Window:** A deep-dive view into every raw byte sent and received. It provides full TX/RX visibility for **MSP, 4-way, and FCSP**, which proved instrumental during the Pico/PIO and FPGA bring-up phases.

Beyond the UI, the project leverages the standard Python `logging` library for:
*   **Rotating File Logs:** Using `RotatingFileHandler` ensures that all diagnostics are persisted to disk without consuming excessive space.
*   **Diagnostics Bundles:** Operators can export a structured bundle containing session metadata, UI logs, and protocol traces for remote troubleshooting.

## 11. Is this Cross-Platform?

**Absolutely.** Python and **imgui-bundle** are a powerful cross-platform duo.
*   **Linux First:** Developed on Linux for deep integration with real-time flight control research.
*   **Windows Ready:** Fully supported on Windows for the "field technician" workflow.

## 12. Future Roadmap

The journey doesn't end with the current implementation. Several exciting paths are being explored for the next phase:
*   **Deep Hardware Offloading:** Further research into moving more of the flight control inner-loop into FPGA RTL, using the configurator as the primary orchestration and diagnostic tool.
*   **Multi-ESC Recovery:** Implementing more advanced "Dead ESC" recovery techniques that leverage the high-speed FCSP protocol to bypass damaged bootloaders.

---

**Interested in the code?** Check out the repository and join the research into high-performance, deterministic flight control.
