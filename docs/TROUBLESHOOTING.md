# Troubleshooting

Start with:

```bash
sudo robot-status
```
```bash
journalctl -u humanoid-robot -n 80
```

The **Startup checks** list on the phone page (and on the Settings page) also tells you which part failed and why.

> To fix wiring or install software, switch to maintenance mode first (`sudo robot-maintenance`) when the fix needs file changes. Wiring fixes do not need it, but **always switch the power off before touching wires.**

---

## Boot, SD card and power

| Symptom | Likely cause | Fix |
|---|---|---|
| Pi does not boot, red LED only | Bad or fake SD card, or bad image | Re-flash with Raspberry Pi Imager; use a genuine high-endurance card; restore your backup image |
| Rainbow screen / reboot loop, *"under-voltage"* in `robot-status`, or the robot says *"power supply voltage is too low"* | 5 V supply too weak | Set the buck to 5.1 V; use a 5 A buck; use 18 AWG or thicker, short 5 V and GND wires (two of each to pins 2/4 and 6/14); add the 470 µF capacitor; never feed servos from the 5 V rail |
| Pi reboots whenever the robot walks | Servo current pulls down the battery or the shared supply | Servos must use the separate 6 V buck; fuse and wires sized for 15–20 A; 1000 µF on the servo rail; charge the battery |
| `robot-protect` says *"kernel … is installed but … is running"* | A kernel update has not been booted yet | `sudo reboot`, then `sudo robot-protect` again |
| Settings are lost after reboot | Protected mode keeps changes in RAM only | `sudo robot-maintenance` → save on the Settings page → `sudo robot-protect` |
| `install.sh` says *"SD card protection is ON"* | Install needs a writable card | `sudo robot-maintenance`, then run the installer again |
| `$'\r': command not found` when running a script | The file got Windows line endings | `sed -i 's/\r$//' ~/humanoid_robot/system/*` and run again |

## Wi-Fi and phone

| Symptom | Likely cause | Fix |
|---|---|---|
| No **Humanoid-Robot** Wi-Fi | Wi-Fi country not set, or the hotspot was not created | `sudo raspi-config nonint do_wifi_country XX` (your code), `rfkill unblock wifi`, run `install.sh` again, reboot |
| Phone connects but page does not open | Phone switched to mobile data ("no internet") | Turn mobile data off or tap *stay connected*; open exactly `http://10.42.0.1` (http, not https) |
| Page opens but shows **OFFLINE** | The robot program is not running | `sudo systemctl status humanoid-robot`, then `journalctl -u humanoid-robot -n 80` |
| Robot stops every half second while driving | Weak Wi-Fi, so commands arrive late | Stay closer (2.4 GHz range, ~10 m indoors); avoid metal between phone and Pi |
| Need home Wi-Fi again (for updates) | The hotspot has priority | Plug in an Ethernet cable, **or** run `sudo nmcli connection down robot-hotspot` then `sudo nmcli connection up preconfigured` (the Imager profile; `nmcli connection show` lists the names) |

## Servos and walking

| Symptom | Likely cause | Fix |
|---|---|---|
| Startup check **Servo controller FAIL** | PCA9685 not found on I2C | Check SDA → pin 3, SCL → pin 5, VCC → 3.3 V, GND; `sudo i2cdetect -y 1` must show `40` |
| Servos do not move, but the PCA9685 is found | No 6 V on V+, servo E-STOP switch pressed, or OE held high | Measure 6 V at the servo rail; release the E-STOP switch; OE → GPIO22 (pin 15) |
| Servos jitter or buzz | Weak servo supply, or no common ground | Common GND between the 6 V buck, PCA9685 and Pi; 1000 µF capacitor; thicker wires |
| A joint moves the wrong way | Mirrored mounting | Settings → tick **Invert** for that joint → Save |
| The robot leans or falls when standing | Horns not centered | Settings → adjust **Trim** (see BUILD_GUIDE Step 2.2 and 8) |
| A servo gets hot while standing | It is pushing against the frame | Reduce that joint's **Min/Max** limits, or re-center its horn |
| Robot falls over while walking | Gait too big or too fast | Edit `motion/gaits.json`: smaller ANKLE and HIP values, larger step time (BUILD_GUIDE 8.1) |
| *"Stop walking first"* when pressing a gesture | Gestures only run while standing still | Release the joystick, then press the gesture |

## Sensors

| Symptom | Likely cause | Fix |
|---|---|---|
| **Distance sensor FAIL** / "--" | No echo pulse | TRIG → GPIO23 (pin 16); ECHO → **1 kΩ** → GPIO24 (pin 18) with **2 kΩ** to GND; VCC 5 V; check that the divider is the right way round |
| Distance always ~250 cm | Nothing in front, or the sensor is tilted toward the floor or ceiling | Point it straight ahead, about 10 cm or more above the floor |
| **Temperature sensor FAIL** | Kernel driver not loaded, or no pull-up | `grep dht11 /boot/firmware/config.txt`; DATA → GPIO4 (pin 7) with a 10 kΩ resistor to 3.3 V; DHT22 VCC on 3.3 V |
| **Gas sensor FAIL: MCP3008 not responding** | SPI wiring | CLK pin 23, DOUT pin 21, DIN pin 19, CS pin 24; MCP3008 VDD and VREF on **3.3 V**; `ls /dev/spidev0.0` |
| **Gas sensor FAIL: MQ-2 reads 0 V** | MQ-2 not powered, or AO not connected | MQ-2 VCC 5 V; AO → 10 kΩ → CH0, with 20 kΩ from CH0 to GND |
| Gas alarm right after startup | MQ-2 not warmed up yet, or switched on in dirty air | Alarms are ignored for the 2-minute warm-up; start the robot in clean air; a new MQ-2 needs ~24 h of burn-in the first time |
| Battery shows *"no battery"* | Divider not connected (fine on bench power) | 100 kΩ from battery + (after the fuse) to CH1, 22 kΩ from CH1 to GND, 100 nF across the 22 kΩ |
| Battery % wrong | Resistor tolerance | Measure the battery with a multimeter and change `battery_divider_ratio` in `config/defaults.json` (maintenance mode) |

## Sound and camera

| Symptom | Likely cause | Fix |
|---|---|---|
| **Speaker FAIL: no sound card** | I2S overlay missing | `grep max98357a /boot/firmware/config.txt` must show `dtoverlay=max98357a,no-sdmode`; reboot |
| Sound card OK but silent | Wiring or volume | BCLK → pin 12, LRC → pin 35, DIN → pin 40, VIN 5 V; test with `speaker-test -c2 -t wav`; `amixer set PCM 90%` |
| Crackling sound | Weak 5 V supply | See under-voltage above |
| **Camera FAIL** | Ribbon cable | Power off; on the Pi end, the blue side of the ribbon faces the Ethernet/USB ports, contacts toward the HDMI side; check `camera_auto_detect=1`; `rpicam-hello --list-cameras` |
| Video stops after a while | Wi-Fi bandwidth or Pi temperature | Use video only when needed; check CPU temperature on the Raspberry Pi tile (below 75 °C) |
