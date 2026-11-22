# Humanoid Robot: Step-by-Step Build Guide

**Raspberry Pi 3 Model B / B+, PCA9685, 6 × MG996R, 3 × MG90S, HC-SR04, MQ-2 + MCP3008, DHT22, Pi camera, MAX98357A**

This guide takes you from a box of parts to a walking robot that you control with a phone joystick. Follow the steps in order. Each step ends with a check, and you should not continue until the check passes.

| Document | What it covers |
|---|---|
| **BUILD_GUIDE.md** (this file) | Parts, assembly, software install, calibration, daily use |
| [WIRING.md](WIRING.md) | Every wire, the GPIO pin table and the pre-power checklist |
| [wiring_diagram.svg](wiring_diagram.svg) / [power_diagram.svg](power_diagram.svg) | Printable wiring and power diagrams |
| [SD_CARD_PROTECTION.md](SD_CARD_PROTECTION.md) | How the SD card is protected against corruption |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | What to do when something does not work |

> **Safety first.** This is an educational prototype. It is **not** a certified smoke, gas or fire alarm, so never rely on it to protect people. Li-ion packs can burn if they are shorted or charged wrongly; have the 4S pack built or checked by a qualified person. Keep fingers away from the servos when the power is on.

---

## Step 0: How the robot works (2-minute overview)

```text
  Phone (Wi-Fi "Humanoid-Robot")  --->  http://10.42.0.1  joystick + live video
                                         |
  Raspberry Pi 3B -- main.py (starts automatically at boot)
     |-- PCA9685 (I2C) ----> 6 leg servos + head + 2 arms
     |-- HC-SR04 ----------> obstacle distance
     |-- MCP3008 (SPI) ----> MQ-2 smoke/gas + battery voltage
     |-- DHT22 ------------> temperature / humidity
     |-- MAX98357A (I2S) --> speaker (voice greeting and warnings)
     |-- camera (CSI) -----> live video to the phone
     '-- LEDs, buzzer, buttons
  SD card: READ-ONLY at runtime -> switching the power off cannot corrupt it.
```

The robot works **without a phone**. On its own it watches its sensors, raises alarms, and can patrol. The phone adds manual driving, live video and settings.

---

## Step 1: Collect the parts

The main parts are in section 3 of the project documentation (`Humanoid_Robot_Complete_Project_Documentation.md`). This build also needs the **extra parts below**. They are cheap, and most of them prevent damage to the Pi or the SD card.

| Extra part | Qty | Why |
|---|---:|---|
| **High-endurance microSD, 32 GB, A1** (SanDisk High Endurance or Samsung PRO Endurance), bought from a trusted shop | 1 (+1 spare) | Fake or cheap cards are the #1 cause of "corrupted SD card" |
| Resistors 1 kΩ | 2 | HC-SR04 ECHO divider (top) and buzzer transistor base |
| Resistors 2 kΩ (or 2 × 1 kΩ in series) | 1 | HC-SR04 ECHO divider (bottom) |
| Resistors 10 kΩ | 3 | DHT22 pull-up, buzzer base pull-down, MQ-2 divider (top) |
| Resistor 20 kΩ (or 2 × 10 kΩ in series) | 1 | MQ-2 divider (bottom) |
| Resistors 100 kΩ and 22 kΩ | 1 each | Battery-voltage divider |
| Resistors 330 Ω | 6 | One per LED |
| NPN transistor S8050 or 2N2222 | 1 | Drives the buzzer (a GPIO pin is too weak) |
| Diode 1N4148 | 1 | Protects the transistor from the buzzer |
| Capacitor 100 nF | 1 | Smooths the battery-voltage reading |
| Capacitor 1000 µF 16 V | 1 | On the 6 V servo rail, absorbs servo current spikes |
| Capacitor 470 µF 10 V | 1 | On the 5 V Pi rail, prevents under-voltage dips |
| **5 V buck converter rated 5 A** (adjustable, set to 5.1 V) | 1 | A 3 A unit is the minimum; 5 A gives margin for the camera, speaker and MQ-2 heater |
| Latching emergency-stop (mushroom) switch, 10 A | 1 | Cuts servo power only; the Pi keeps running |
| Push buttons | 3 | E-STOP, MODE, SHUTDOWN |
| Pi camera ribbon cable (long enough to reach the head) | 1 | |
| Multimeter, soldering iron, heat-shrink tubing | | For setting and checking voltages |

**Raspberry Pi 3B or 3B+?** Both work with exactly the same pins and software. The robot's Wi-Fi uses 2.4 GHz, which both boards support.

---

## Step 2: Build the mechanics

### 2.1 Leg layout (3 servos per leg)

```text
          torso (battery LOW in the torso/hips = more stable)
   R_HIP  [servo, axis left-right]   L_HIP     swings the leg forward / back
     |                                  |
   R_KNEE [servo, axis left-right]   L_KNEE    bends the knee (lifts the foot)
     |                                  |
   R_ANKLE[servo, axis front-back]   L_ANKLE   tilts the body sideways (weight shift)
   ====== foot (anti-slip rubber) ======
```

- **Hip and knee** servos rotate around the left-right axis (pitch).
- **Ankle** servos rotate around the front-back axis (roll). Tilting both ankles moves the body's weight over one foot so the other foot can lift.
- **Head** (MG90S) turns left and right. **Arms** (MG90S) swing forward and up.
- Keep leg segments short (6–8 cm) and the robot light (under ~1.5 kg). MG996R servos give about 10 kg·cm at 6 V, so long legs or a heavy body will make them stall.
- Make the feet wide and flat with the anti-slip rubber underneath. Wider feet make a more stable walk.

### 2.2 Center every servo BEFORE you fit the horns (important!)

If you fit the horns at a random angle, the robot cannot stand straight. Do this before the final assembly:

1. Finish Steps 3–6 first (wiring + software), with the servos plugged into the PCA9685 but **not yet** fixed to the brackets.
2. Power on. At startup the program moves **every servo to 90°** (the home pose).
3. While the servos hold 90°, fit each horn so that its joint is **straight**: legs straight down, feet flat, head facing forward, arms hanging down.
4. Small errors are fixed later with **Trim** on the Settings page (Step 8).

---

## Step 3: Wire everything

Open **[WIRING.md](WIRING.md)** and wire one component at a time, following its tables and diagrams. These are the rules that protect the Pi and the SD card:

1. **Never power servos from the Pi.** The servos get their own 6 V buck converter.
2. **All grounds connect together** (battery −, both bucks, Pi GND, PCA9685 GND, sensors).
3. **GPIO pins are 3.3 V only.** The HC-SR04 ECHO and the MQ-2 output must go through their resistor dividers.
4. **Set both buck converters with a multimeter before connecting anything** (6.0 V servo and 5.1 V Pi).
5. Use thick, short wires for the 5 V supply to the Pi (18 AWG or thicker). Thin wires cause **under-voltage**, a common cause of SD card damage.

**Check:** go through the *Pre-power checklist* in WIRING.md.

---

## Step 4: Prepare the SD card (on your Windows PC)

1. Install **Raspberry Pi Imager** from raspberrypi.com/software.
2. Insert the microSD card and start Imager.
   - **Device:** Raspberry Pi 3
   - **OS:** *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (32-bit)**. Lite means no desktop: it boots faster and uses less memory.
   - **Storage:** your microSD card
3. Fill in the **customisation** settings. In Imager 1.x, answer *"Use OS customisation?"* with **Edit settings**; in Imager 2.x these are the Customisation pages of the wizard.
   - Hostname: `humanoid-robot`
   - Username and password: choose them and write them down
   - Wireless LAN: your **home Wi-Fi** name and password (needed once, to download software)
   - Wireless LAN country: your country
   - **Services** tab: enable **SSH** with password authentication
4. Write the card and wait for verification to finish.
5. Imager ejects the card. Take it out and put it back in: Windows now shows a drive called **bootfs**.
6. **Copy the whole `humanoid_robot` folder onto the bootfs drive.**
7. Eject the drive safely and put the card into the Pi.

**Check:** the bootfs drive contains `humanoid_robot\system\install.sh`.

---

## Step 5: Install the robot software (on the Pi)

1. Power the Pi with the robot's 5 V supply or a good USB power supply. The first boot takes 1–2 minutes.
2. On your PC, open a terminal (PowerShell) and connect over SSH:
   ```bash
   ssh <your-username>@humanoid-robot.local
   ```
   If `.local` does not work, find the Pi's IP address in your router and use `ssh <user>@<ip>`.
3. Copy the program from the boot partition and run the installer:
   ```bash
   cp -r /boot/firmware/humanoid_robot ~/
   sudo bash ~/humanoid_robot/system/install.sh
   ```
   The installer asks two things:
   - a **password for the robot's own Wi-Fi** (at least 8 characters; write it down)
   - your **Wi-Fi country code**, if it was not set already

   Then it runs on its own for 10–20 minutes. It installs packages, configures audio and the sensors, installs the robot service and creates the hotspot.
4. When it prints **Installation finished**, reboot:
   ```bash
   sudo reboot
   ```

> After this reboot, the Pi **stops using your home Wi-Fi** and starts its own network, **Humanoid-Robot**. Your SSH session closes. From now on, connect your PC or phone to **Humanoid-Robot** and use `ssh <user>@10.42.0.1`.

**Check:** about 45 seconds after power-on, the robot says *"Hello! Humanoid Robot System activated…"* and the green LEDs light up.

---

## Step 6: Connect the phone

1. On the phone, join the Wi-Fi network **Humanoid-Robot** with the password you chose. If the phone warns *"no internet"*, choose **stay connected**.
2. Open the browser and go to **http://10.42.0.1**
3. Tap **Start video** to see the camera.
4. The green dot in the top-left corner means the phone is connected.

**Check:** the **Activity → Startup checks** list shows **OK** for every part. Fix any **FAIL** using [TROUBLESHOOTING.md](TROUBLESHOOTING.md) before you continue.

You can also check everything from SSH:

```bash
sudo robot-status
```

---

## Step 7: Test each part on its own

Put the robot on a stand with its feet in the air. Test each part in this order:

| Part | How to test | Expected result |
|---|---|---|
| LEDs | Power on | All LEDs flash once (lamp test), then green stays on |
| Buzzer | Power on | One short beep at startup |
| Speaker | Speak card → **Hello** | The robot speaks |
| Distance | Hold your hand 10 cm in front | Distance tile shows ~10 cm |
| Temperature | Breathe warm air on the DHT22 | Temperature and humidity rise slowly |
| Smoke / gas | Wait 2 min (warm-up), then hold a just-blown-out match near the MQ-2 (outdoors or under supervision) | Tile turns yellow then red, alarm sounds; press **Silence** |
| Battery | Run from the battery | Battery tile shows 14–16.8 V |
| E-STOP button | Press it | Red LEDs, *"Emergency stop activated"*; hold **MODE** for 2 s to release |
| MODE button | Short press | Switches Monitor ↔ Auto patrol (spoken) |
| SHUTDOWN button | Hold 2 s | The Pi shuts down cleanly |
| Servos | Settings → Test **+15°** on each joint | Only that joint moves, in the expected direction |
| Camera | Start video | Live picture on the phone |

---

## Step 8: Calibrate the servos (Settings page)

Open **http://10.42.0.1/settings** with the robot on its stand.

1. **Direction check.** Press **Test +15°** for each joint. The correct direction is:

   | Joint | +15° should… |
   |---|---|
   | R_HIP / L_HIP | swing that leg **forward** |
   | R_KNEE / L_KNEE | **bend** that knee (foot goes back/up) |
   | R_ANKLE / L_ANKLE | tilt the body to the **robot's right** (both ankles the same way) |
   | HEAD | turn the head to the **robot's left** |
   | R_ARM / L_ARM | **raise** that arm forward |

   If a joint moves the wrong way, tick **Invert** for it.
2. **Trim.** Move each Trim slider until the joint is perfectly straight in the home pose.
3. **Limits.** If a joint hits the frame before its end, reduce **Max** or raise **Min** so the servo can never stall against the frame. A stalled servo gets hot and draws a lot of current.
4. Press **Save permanently**. While SD card protection is still off, this writes to the SD card. The message must say **Settings saved permanently**.

**Check:** reboot (Settings → Reboot). The trims are still there.

### 8.1 Tune the walk

The walking motion lives in `/opt/humanoid-robot/motion/gaits.json` as a list of keyframes (degrees away from the home pose). Start with small movements on a flat, non-slippery floor:

```bash
sudo nano /opt/humanoid-robot/motion/gaits.json
sudo systemctl restart humanoid-robot
```

- Robot falls **sideways** → make the ANKLE lean smaller (10 → 7), or make the feet wider.
- Feet **scrape** the floor → bend the KNEE more (25 → 30).
- Steps **too long** → make the HIP values smaller (15 → 10).
- Everything **too fast** → Settings → Walking → *Time per gait step* (320 → 450 ms).

Always walk with one hand ready to catch the robot, and keep the servo E-STOP switch within reach.

---

## Step 9: Turn on SD card protection (the crucial step)

Do this only when everything works and your calibration is saved:

```bash
sudo robot-protect
```

Answer **y**. The Pi builds a protected boot image (about 1 minute) and reboots. From now on:

- the SD card is **read-only**, so **you can switch the power off at any moment** without corrupting it
- the web page shows **SD PROTECTED** (green)
- `sudo robot-status` shows `PROTECTED now`

**Check (power-cut test):** while the robot is running, switch the main power off and on **10 times**. Wait about 20 seconds between tries, at different moments (during boot, while speaking, while walking). It must start and greet you every time.

How this works, and how to make changes later, is explained in [SD_CARD_PROTECTION.md](SD_CARD_PROTECTION.md).

---

## Step 10: Daily use

### Power on

1. Check the battery is charged and the **servo E-STOP switch** is released.
2. Switch the **main power** on.
3. After about 45 seconds the robot greets you, checks its sensors and camera, and says *"I am ready to assist you"*. If a part failed, it names that part instead.
4. Join **Humanoid-Robot** Wi-Fi with the phone and open **http://10.42.0.1**.

### Phone controls

| Control | Function |
|---|---|
| **Joystick** | Drag up = walk forward, down = backward, left/right = turn. Further from the center = faster. Release = stop. |
| Arrow buttons / **STOP** | The same as the joystick, for hold-to-walk |
| **EMERGENCY STOP** | Freezes the robot in place. It stays stopped until you press **Release emergency stop** (or hold **MODE** for 2 s). |
| **Mode** | **Monitor**: stands still and watches the sensors. **Manual**: phone driving. **Auto patrol**: walks and turns away from obstacles. Using the joystick always switches to Manual. |
| **Head** slider / **Gestures** | Turn the head; wave, raise arms, look around |
| **Speak** | Preset phrases or your own text (spoken offline) |
| **Silence** | Mutes the alarm sound for 60 s. During a smoke or heat emergency it also *acknowledges* the alarm, which lets you drive the robot away. |
| Keyboard (PC) | Arrows / W A S D to walk, Space = stop, Esc = emergency stop |

The robot **stops by itself** if the phone disconnects, the screen locks, or no command arrives for 0.5 seconds.

### LEDs and buzzer

| State | LEDs | Buzzer | Meaning |
|---|---|---|---|
| STARTING | green → yellow → red chase | 1 beep | Booting and checking |
| READY | green on | – | Everything OK, standing |
| MOVING | green blinking | – | Walking |
| OBSTACLE | yellow fast blink | – | Something closer than 25 cm, so forward is blocked |
| WARNING | yellow on | chirp every 5 s | High temperature, possible smoke or low battery |
| EMERGENCY | red blinking | beeping | Smoke/gas or heat danger. The robot stops and signals with its arms. |
| STOPPED | red on | – | Emergency stop is on |
| SHUTDOWN | yellow slow blink | – | Shutting down or rebooting |

### Buttons on the robot

| Button | Press | Hold 2 s |
|---|---|---|
| **E-STOP** (GPIO16, pin 36) | Emergency stop (freeze) | – |
| **MODE** (GPIO26, pin 37) | Monitor ↔ Auto patrol | Release the emergency stop |
| **SHUTDOWN** (GPIO27, pin 13) | – | Clean shutdown |
| **Servo E-STOP switch** (power) | Cuts servo power. The robot goes limp and **falls**, so use it only in a real emergency. | – |

### Power off

- **Protected mode** (normal use): just switch the main power off.
- Optionally, use **Settings → Shut down** (or hold SHUTDOWN). The robot crouches first so it does not fall, then the Pi turns off. Switch the main power off after about 20 seconds.
- In **maintenance mode**, always shut down first.

### Battery

- The robot warns at **13.6 V** (*"My battery is low"*).
- Below **13.2 V** for 30 seconds it shuts down by itself. This protects both the cells and the SD card.
- Charge only with the matching 16.8 V 4S charger, never unattended.

---

## Step 11: Changing the software later

1. `sudo robot-maintenance`: the Pi reboots with a writable SD card. You can also use Settings → *Switch to MAINTENANCE mode*.
2. Copy your new `humanoid_robot` folder to the Pi (for example with WinSCP, or via the bootfs drive), then run:
   ```bash
   sudo bash ~/humanoid_robot/system/install.sh
   ```
3. Test, then `sudo robot-protect` again.

Small edits (such as `gaits.json`) can be made directly in `/opt/humanoid-robot/` while in maintenance mode.

---

## Appendix A: Run the robot program on a PC (simulator)

You can try the whole phone interface on Windows without any hardware:

```bash
py -m pip install aiohttp
```
```bash
py humanoid_robot/main.py --sim
```

Open **http://localhost:8080**. The **Simulator** card lets you change the distance, temperature, gas, battery and SD protection, so you can see every alarm and safety rule work.

Run the automatic tests:

```bash
py -m pip install pytest
```
```bash
cd humanoid_robot
py -m pytest tests
```

## Appendix B: Where things are

| Path on the Pi | Content |
|---|---|
| `/opt/humanoid-robot/` | The robot program (copied by install.sh) |
| `/opt/humanoid-robot/config/defaults.json` | Default thresholds, servo table, spoken phrases |
| `/opt/humanoid-robot/config/pins.py` | GPIO pin map (matches WIRING.md) |
| `/opt/humanoid-robot/motion/gaits.json` | Walking keyframes and gestures |
| `/opt/humanoid-robot/sounds/` | Optional recorded WAV files (see README there) |
| `/var/lib/humanoid-robot/settings.json` (+ `.bak`) | Your saved calibration and thresholds |
| `journalctl -u humanoid-robot -f` | Live log of the robot program |
