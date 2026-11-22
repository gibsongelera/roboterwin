# HUMANOID ROBOT — COMPLETE PROJECT DOCUMENTATION

**Project name:** Raspberry Pi Humanoid Emergency Assistance Robot  
**Platform:** Raspberry Pi 3 Model B+  
**Document type:** Project description, master materials checklist, functions, and implementation guide  
**Updated:** October 28, 2026  
**Project status:** Design and materials checklist documented; actual purchases and completed functions require verification.

---

## 1. ROBOT DESCRIPTION

Our project is a **walking humanoid emergency-assistance robot** powered by a **Raspberry Pi 3 Model B+**. It is designed to move using servo motors, monitor its surroundings through sensors, warn nearby people of possible hazards, and accept commands from a smartphone. The robot is intended to operate **locally without an internet connection** for its basic sensing, movement, and alarm functions.

The robot uses an **HC-SR04 ultrasonic sensor** to detect nearby obstacles, an **MQ-2 sensor** to detect indications of smoke or combustible gas, and a **DHT22 sensor** to monitor temperature and humidity. A **5 MP Raspberry Pi camera** supports live viewing and can later be used for computer-vision features. When an alert condition is detected, the robot can be programmed to activate a **buzzer, warning LEDs, and spoken messages** using a speaker and MAX98357A amplifier. An external **PCA9685 servo controller** coordinates the motors that move its legs, head, and arms.

The main priority is **emergency detection and alerts**, followed by walking and obstacle avoidance, optional local smartphone control, live camera monitoring on the phone, and a spoken greeting after every successful startup. Longer-term concepts include a **guide robot** and **waste detection/collection**, but these require further software and/or hardware development. This is an educational/prototype system, **not a replacement for certified fire, smoke, or gas detectors**.

### 1.1 Main objectives

1. Develop a compact, walking, humanoid robot.
2. Detect nearby obstacles and prevent avoidable collisions.
3. Monitor environmental indicators related to smoke, gas, temperature, and humidity.
4. Produce audible and visible alerts during defined warning conditions.
5. Support local/offline operation and smartphone-based movement commands.
6. Provide camera viewing and a foundation for future object recognition.
7. Design a modular robot that can be expanded with new sensors and functions.

---

## 2. ROBOT FEATURES AND FUNCTIONS

| No. | Function | Description | Main components | Implementation note |
|---|---|---|---|---|
| 1 | Walking forward/backward | Coordinated leg-servo sequences for walking. | 6 × MG996R, PCA9685 | Needs gait design, alignment and stability tests. |
| 2 | Turn left/right | Change walking direction through controlled leg movement. | MG996R, PCA9685 | Requires calibrated turning gait. |
| 3 | Head movement | Move the head as part of the robot's interaction. | MG90S, PCA9685 | Exact axis depends on the mounting design. |
| 4 | Arm gestures | Make simple arm motions/signals. | MG90S, PCA9685 | Limited by 3 small servos shared across head/arms. |
| 5 | Obstacle detection | Estimate distance to objects in front of the robot. | HC-SR04 | ECHO signal needs safe 3.3 V interfacing. |
| 6 | Obstacle avoidance | Stop or turn when an obstacle is detected. | HC-SR04, servos | Behavior requires programming and testing. |
| 7 | Smoke/gas indication | Detect environmental changes associated with smoke/combustible gas. | MQ-2, MCP3008 | Requires calibration; not a certified safety alarm. |
| 8 | Temperature/humidity monitoring | Read surrounding temperature and humidity. | DHT22 | Configurable warning thresholds. |
| 9 | Emergency alarm | Sound a buzzer and illuminate warning LEDs. | Buzzer, LEDs | Triggered by configured alert conditions. |
| 10 | Spoken warnings | Play pre-recorded or synthesized warning phrases. | MAX98357A, 4 Ω 3 W speaker | Needs an offline audio/TTS implementation. |
| 11 | Live camera view | Show images/video from the robot's camera. | 5 MP Pi camera | Works over a supported local connection. |
| 12 | Smartphone control | Send walking/turning/stop commands. | Raspberry Pi Bluetooth, phone app | A compatible app/control interface is required. |
| 13 | Offline operation | Run core controls and sensor monitoring without cloud services. | Raspberry Pi, local software | Phone video/control requires local connectivity. |
| 14 | Manual buttons | Trigger local inputs or selected actions. | Push buttons | Assign functions during programming. |
| 15 | Robot status indicators | Show normal, warning and danger states. | Green/yellow/red LEDs | LED patterns configurable. |
| 16 | Guide robot *(future)* | Provide guided movement or directions. | Camera, sensor/software upgrades | Requires robust localization/navigation. |
| 17 | Waste recognition *(future)* | Identify waste through computer vision. | Camera, vision model | Requires training/testing. |
| 18 | Waste collection *(future)* | Physically pick up detected items. | **Additional gripper/mechanism required** | Not possible with current listed parts alone. |
| 19 | Optional phone controller | Manual controls for forward, backward, left, right, stop, and emergency stop; robot can operate autonomously without phone. | Phone, local web interface or Bluetooth control app | Manual mode must have priority and safe stop handling. |
| 20 | Live video on phone | Display a low-latency view from the robot camera inside a phone dashboard. | 5 MP Pi camera, Raspberry Pi Wi-Fi | Use local Wi-Fi/hotspot for video, not Bluetooth; no internet required. |
| 21 | Startup voice greeting | Speak a welcome/status message automatically after boot and audio initialization. | MAX98357A, 4 Ω 3 W speaker | Plays after successful boot, not immediately at electrical power-on. |

---

## 2.1 OPTIONAL PHONE CONTROLLER + LIVE VIDEO (PLANNED)

- The robot **must work without a phone**: monitoring, alerts and any implemented autonomous behavior run locally on the Raspberry Pi.
- When the phone is connected, a **mobile-friendly controller/dashboard** can display **Forward**, **Backward**, **Left**, **Right**, **Stop**, and **Emergency Stop** buttons, sensor readings, and a **live camera preview**.
- **Connection:** Prefer a local **Wi-Fi network or Raspberry Pi hotspot** for a single web dashboard combining controls and video; internet service is not necessary. Bluetooth can be a separate option for low-bandwidth movement commands, but **not** for practical live-video streaming.
- **Safety:** Loss of controller connection or a stale command must stop manual motion; obstacle and emergency logic remain active. Test the emergency stop independently before walking tests.
- **Implementation:** Camera streaming software and a local web server/dashboard are required; their operation is a **planned feature**, not yet verified as working.

## 2.2 AUTOMATIC STARTUP VOICE GREETING (PLANNED)

On every successful power-up, after Raspberry Pi OS boots and the speaker is initialized, the robot plays a short greeting. **Example script:**

> Hello! Humanoid Robot System activated. Initializing my systems. Please wait while I check my sensors and camera. I am ready to assist you.

The greeting may use a locally stored audio file or offline text-to-speech. A `systemd` service can automatically launch the main robot program on boot. Announce “ready” only once hardware checks succeed. If initialization fails, use an appropriate fault message rather than claiming everything is ready.

---

## 3. MASTER MATERIALS LIST

**Checklist note:** This list consolidates the components discussed in our earlier design. It is **not a verified purchase inventory**. Mark the “On hand?” column after physically checking your parts or receipts.

### 3.1 Main controller and electronics

| # | Material | Quantity | Purpose | On hand? |
|---|---|---:|---|---|
| 1 | Raspberry Pi 3 Model B+ | 1 | Main computer/robot brain | ☐ |
| 2 | 32 GB microSD card | 1 | Operating system, code and files | ☐ |
| 3 | PCA9685 16-channel servo controller | 1 | PWM signals for up to 16 servo channels | ☐ |
| 4 | MCP3008 analog-to-digital converter | 1 | Read MQ-2 analog signals | ☐ |
| 5 | Breadboard | 1 | Prototype circuits | ☐ |
| 6 | Perfboard | 1–2 | More permanent wiring | ☐ |
| 7 | Jumper wires (M–M, M–F, F–F) | 1 set | Signal and component connections | ☐ |
| 8 | Servo extension wires | 1 set | Extend servo leads as needed | ☐ |

### 3.2 Motors and mechanical parts

| # | Material | Quantity | Purpose | On hand? |
|---|---|---:|---|---|
| 9 | MG996R servo motor | 6 | Main leg/joint actuators | ☐ |
| 10 | MG90S servo motor | 3 | Head and arm motions | ☐ |
| 11 | Metal servo U-brackets | 6–8 | Support movable joints | ☐ |
| 12 | Servo horns/hubs | 1 set | Attach mechanical parts | ☐ |
| 13 | Screws, nuts and bolts | 1 set | Assembly and fasteners | ☐ |
| 14 | Black foam board | As needed | Lightweight body panels | ☐ |
| 15 | Anti-slip rubber sheet | 1 | Improve foot grip | ☐ |
| 16 | Standoffs/spacers | 1 set | Mount circuit boards | ☐ |

### 3.3 Sensors and input devices

| # | Material | Quantity | Purpose | On hand? |
|---|---|---:|---|---|
| 17 | HC-SR04 ultrasonic sensor | 1 | Obstacle/distance sensing | ☐ |
| 18 | MQ-2 smoke/gas sensor | 1 | Smoke/combustible gas indication | ☐ |
| 19 | DHT22 temperature/humidity sensor | 1 | Environmental monitoring | ☐ |
| 20 | Raspberry Pi 5 MP camera | 1 | Live view and future vision tasks | ☐ |
| 21 | Push buttons | 2 or more | Local manual input | ☐ |

### 3.4 Sound, alerts and indicators

| # | Material | Quantity | Purpose | On hand? |
|---|---|---:|---|---|
| 22 | MAX98357A I²S audio amplifier | 1 | Digital audio amplification | ☐ |
| 23 | 4 Ω 3 W speaker | 1 | Voice and alert playback | ☐ |
| 24 | Active buzzer | 1 | Audible emergency warning | ☐ |
| 25 | Red LEDs | 2 | Danger status | ☐ |
| 26 | Green LEDs | 2 | Normal/ready status | ☐ |
| 27 | Yellow LEDs | 2 | Warning status | ☐ |
| 28 | Suitable LED resistors | 1 set | Limit LED current | ☐ |

### 3.5 Batteries, charging and power distribution

| # | Material | Quantity | Purpose | On hand? |
|---|---|---:|---|---|
| 29 | 18650 rechargeable Li-ion cells | 4 | Battery pack cells | ☐ |
| 30 | 4S 20A BMS | 1 | 4-series-cell protection | ☐ |
| 31 | 16.8 V lithium-ion charger | 1 | Charge a correctly assembled 4S pack | ☐ |
| 32 | DC charging port (5.5 × 2.5 mm) | 1 | Charger connection if compatible | ☐ |
| 33 | 6 V high-current buck converter (20 A design target) | 1 | Regulated servo supply | ☐ |
| 34 | 5 V buck converter rated ≥3 A | 1 | Raspberry Pi supply | ☐ |
| 35 | Main power switch | 1 | Power isolation | ☐ |
| 36 | 20 A fuse and holder | 1 | Main pack protection (must be correctly sized) | ☐ |
| 37 | XT60 connectors | 1 set | Main battery connection | ☐ |
| 38 | Servo power distribution board | 1 | Distribute high-current servo supply | ☐ |
| 39 | 18–22 AWG hookup wires | 1 set | Low-current connections where suitable | ☐ |
| 40 | 12–14 AWG power wires | As needed | Main supply wiring, sized to load | ☐ |
| 41 | Heat-shrink tubing | 1 set | Insulation | ☐ |
| 42 | Cable ties | 1 set | Cable organization | ☐ |

**Planned total servo count: 9 (6 MG996R + 3 MG90S).** Quantities for mounting hardware, wiring, LEDs and controls should be confirmed against the final physical layout.

---

## 4. OVERALL HARDWARE ARCHITECTURE

```text
                  4S 18650 BATTERY PACK
                [Correct BMS + main fuse]
                           |
                      Main switch
                           |
                  Power distribution
                  /                 \
          5 V regulator          6 V servo regulator
                |                         |
        Raspberry Pi 3B+       Servo power distribution
                |                         |
       +--------+--------+             PCA9685
       |        |        |           control signals
    Sensors   Camera   Audio                 |
       |               amplifier      6 x MG996R +
       |                   |           3 x MG90S
   HC-SR04,            Speaker
   DHT22, MQ-2
   (MQ-2 -> MCP3008)

   Pi GPIO / I2C / SPI -> PCA9685, sensor interfaces,
                          LEDs, buzzer, push buttons

        IMPORTANT: common signal ground is required.
        Do not power servos from the Raspberry Pi GPIO.
```

### Important electrical safety notes

- **Battery:** The 4S design is the current planning reference; an earlier 2S2P concept also existed. Do **not** mix the two charging/BMS configurations. Have the pack built or checked by a qualified person; use matched cells and the proper 4S charger/BMS.
- **Servo power:** Use a separately regulated, adequately rated supply with common signal ground; verify peak and stall current before selecting fuses, wiring and converter.
- **GPIO voltage:** Raspberry Pi GPIO is **3.3 V only**. Use safe level shifting/dividers as needed, including the HC-SR04 ECHO pin and any 5 V outputs.
- **MQ-2 and MCP3008:** Confirm analog voltage stays within the MCP3008 supply/reference limits and that the interface is safe for the Pi.
- **Audio and GPIO assignments:** Final pin map must be checked for shared pins and collisions before hookup.
- **Emergency reliability:** Prototype readings can be inaccurate; do not rely on this robot for life-safety decisions.

---

## 5. SOFTWARE AND PROGRAMMING

| Software / module | Intended use |
|---|---|
| Raspberry Pi OS | Operating system |
| Python 3 | Main robot program |
| PCA9685 control library | Servo commands and calibration |
| GPIO library | Buttons, buzzers, LEDs, digital inputs |
| SPI / MCP3008 driver | Analog sensor readings |
| DHT22-compatible library | Temperature and humidity |
| Raspberry Pi camera software | Photo/video capture |
| Bluetooth control layer | Local phone command input |
| Offline text-to-speech / audio playback | Spoken messages |
| Optional local web interface | Status dashboard and camera view over local Wi-Fi |

### Suggested software modules

```text
humanoid_robot/
├── main.py                   # Start robot and main event loop
├── config/                   # GPIO assignments and thresholds
├── motion/                   # Servo calibration and walking gaits
├── sensors/                  # Distance, smoke/gas, temp/humidity
├── alerts/                   # Buzzer, LEDs, speech
├── camera/                   # Camera capture/streaming
├── control/                  # Buttons, Bluetooth, manual commands
├── safety/                   # Stop logic, fault handling
└── docs/                     # Wiring and operating instructions
```

---

## 6. BASIC ROBOT OPERATION

1. **Power ON:** Switch on the correctly protected and regulated power supplies.
2. **Initialize:** Raspberry Pi boots; scripts initialize sensors, audio and the PCA9685.
3. **Voice greeting:** After successful boot and audio initialization, speak: “Hello! Humanoid Robot System activated. All systems initializing. Sensors are online. Camera is ready. I am now ready to assist you.” Only announce sensors/camera as ready if checks succeed.
4. **Servo calibration:** Set a safe home position and verify that servos can move without binding.
5. **Normal mode:** Monitor sensors and accept local commands.
6. **Movement:** Execute validated walking/turning sequences when safe.
7. **Obstacle handling:** Stop or turn if a configured distance limit is reached.
8. **Warning response:** When sensor thresholds indicate a possible hazard, stop movement where appropriate and activate voice, lights and buzzer.
9. **Shutdown:** Move to a safe rest pose, stop motors and shut down cleanly before disconnecting power.

### Example configurable robot states

| State | Meaning | Output |
|---|---|---|
| READY | Startup finished | Green indicator |
| MOVING | Executing movement | Motors active under gait controller |
| OBSTACLE | Object too close | Stop/avoid obstacle |
| WARNING | Threshold exceeded | Yellow LED + message |
| EMERGENCY | Major alert condition | Red LEDs + buzzer + spoken warning |
| STOPPED | Manual or safety stop | Motor commands halted |

---

## 7. DEVELOPMENT PRIORITIES

| Phase | Target | Completion criteria |
|---|---|---|
| 1 | Parts and electrical validation | Components counted; safe power/voltage plan approved |
| 2 | Raspberry Pi and peripherals | OS boots, sensors/audio tested one at a time |
| 3 | Servo calibration | All 9 servo channels labeled and limits tested |
| 4 | Walking mechanics | Robot stands and performs repeatable, stable movement |
| 5 | Alerts and obstacle logic | Warning/stop behaviors tested |
| 6 | Phone controls and camera | Local command input and camera view operational |
| 7 | Integrated tests | Repeatable end-to-end tests and documentation |
| 8 | Future upgrades | Guide mode, vision-based waste detection, optional gripper |

---

## 8. PROJECT SUMMARY

| Category | Planned specification |
|---|---|
| Robot type | Walking humanoid emergency-assistance prototype |
| Main controller | Raspberry Pi 3 Model B+ |
| Servo driver | PCA9685, 16-channel |
| Servo motors | 9 total (6 MG996R + 3 MG90S) |
| Core sensors | HC-SR04, MQ-2, DHT22 |
| Camera | Raspberry Pi 5 MP |
| Audio | MAX98357A + 4 Ω 3 W speaker |
| Alerts | Active buzzer + 6 colored LEDs |
| Battery design | 4 × 18650 in 4S arrangement, subject to safety checks |
| Control | Local / offline with planned smartphone interface |
| Primary goal | Emergency sensing and warning |
| Future goals | Navigation guide, waste recognition and collection |

**Inventory disclaimer:** “Included in master list” does not necessarily mean “purchased,” “installed,” or “functioning.” Update the on-hand checklist and test records to track the actual project status.
