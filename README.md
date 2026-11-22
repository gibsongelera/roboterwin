# Humanoid Robot: Raspberry Pi 3B Emergency-Assistance Robot

A walking humanoid robot that watches for obstacles, smoke/gas and heat, warns people with voice, lights and a buzzer, and can be driven from a **phone joystick website** with **live video**. Everything runs offline on a Raspberry Pi 3B / 3B+. The **SD card is read-only at runtime**, so you can switch the power off at any time without corrupting it.

> Educational prototype: **not** a certified smoke, gas or fire alarm.

## Start here

1. **[docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md)**: step-by-step from parts to a walking robot
2. **[docs/WIRING.md](docs/WIRING.md)**: GPIO pin table and every wire, plus [wiring_diagram.svg](docs/wiring_diagram.svg) and [power_diagram.svg](docs/power_diagram.svg)
3. **[docs/SD_CARD_PROTECTION.md](docs/SD_CARD_PROTECTION.md)**: how "never corrupt the SD card" works
4. **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)**: what to do when a part fails
5. [Humanoid_Robot_Complete_Project_Documentation.md](Humanoid_Robot_Complete_Project_Documentation.md): the original project description and parts list

## Quick start (on the Pi)

1. Flash **Raspberry Pi OS Lite (32-bit)** with Raspberry Pi Imager (enable SSH and your home Wi-Fi).
2. Copy the `humanoid_robot` folder onto the **bootfs** drive.
3. Boot the Pi, connect with SSH, then run:

   ```bash
   cp -r /boot/firmware/humanoid_robot ~/
   ```
   ```bash
   sudo bash ~/humanoid_robot/system/install.sh
   ```
   ```bash
   sudo reboot
   ```

4. Connect the phone to the Wi-Fi **Humanoid-Robot** and open **http://10.42.0.1**
5. Test and calibrate (Settings page), then make the SD card read-only:

   ```bash
   sudo robot-protect
   ```

## Try it on a PC (no hardware)

```bash
py -m pip install aiohttp
```
```bash
py humanoid_robot/main.py --sim
```

Then open http://localhost:8080. The Simulator card lets you fake obstacles, smoke, heat and a low battery.

## Pin map (summary, BCM numbers)

| Function | GPIO | Pin |
|---|---|---|
| PCA9685 SDA / SCL / OE | 2 / 3 / 22 | 3 / 5 / 15 |
| DHT22 data | 4 | 7 |
| HC-SR04 TRIG / ECHO (via divider) | 23 / 24 | 16 / 18 |
| MCP3008 MOSI / MISO / SCLK / CE0 | 10 / 9 / 11 / 8 | 19 / 21 / 23 / 24 |
| MAX98357A BCLK / LRC / DIN | 18 / 19 / 21 | 12 / 35 / 40 |
| Buzzer (via NPN) | 17 | 11 |
| LEDs green / yellow / red | 5 / 6 / 13 | 29 / 31 / 33 |
| Buttons E-STOP / MODE / SHUTDOWN | 16 / 26 / 27 | 36 / 37 / 13 |

Full details: [docs/WIRING.md](docs/WIRING.md). The code reads the same map from `humanoid_robot/config/pins.py`.

## Project layout

```text
humanoid_robot/            copied to /opt/humanoid-robot on the Pi
├── main.py                entry point (systemd starts it at boot)
├── core.py                startup checks, greeting, 10 Hz safety/control loop
├── config/                pins.py, defaults.json (thresholds, servos, phrases), settings.py (safe save/load)
├── hal/                   PCA9685 driver, hardware factory, PC simulator
├── motion/                servo joints + limits, keyframe gait engine, gaits.json
├── sensors/               HC-SR04, DHT22 (kernel driver), MCP3008 + MQ-2 logic, Pi health
├── alerts/                LEDs + buzzer patterns, offline speech (espeak-ng)
├── camera/                picamera2 hardware-MJPEG stream
├── control/               aiohttp web server + phone website (static/)
├── safety/                state machine (E-stop, emergency, obstacle, watchdog), battery monitor
├── sounds/                optional recorded WAV phrases
├── system/                install.sh, robot-protect, robot-maintenance, robot-status, service + config files
└── tests/                 pytest tests (run on a PC)
```
