# SD Card Protection: Power Off at Any Time Without Corruption

**Goal:** after the robot has booted once, switching the power off (battery unplugged, switch flipped, battery empty) must **never** damage the SD card. This file explains how the robot achieves that and how to work with it.

---

## 1. Why SD cards get corrupted

| Cause | What happens | What this project does about it |
|---|---|---|
| Power cut **while the card is writing** | Half-written files or a damaged file system; the Pi may not boot | **Read-only root file system (overlay)**: in normal use nothing is written at all |
| **Under-voltage** (weak 5 V supply, thin wires) | The Pi browns out in the middle of operations | 5.1 V / 5 A buck converter, thick short wires, 470 µF capacitor; under-voltage is detected, shown and spoken |
| Battery runs flat | The voltage sags slowly and the Pi browns out | Battery monitor: warning at 13.6 V, clean automatic shutdown at 13.2 V |
| Fake or low-quality card | It fails even with careful use | Use a genuine **high-endurance** card from a trusted shop |
| Card wear (constant small writes) | The card wears out over months | Logs kept in RAM, no swap file, automatic background updates disabled |
| Pi freezes | Someone pulls the plug while it is hung | Hardware watchdog reboots it automatically within ~14 s |

---

## 2. How the protection works

Raspberry Pi OS has a built-in **overlay file system** (set up with `raspi-config`). With it switched on:

```text
         what programs see:  /  (looks like a normal, writable disk)
                              |
          +-------------------+--------------------+
          |                                        |
   UPPER layer: RAM (tmpfs)                LOWER layer: SD card
   every write goes here                   mounted READ-ONLY
   lost when power is cut                  never written -> cannot be damaged
```

- The **SD card is mounted read-only**. Linux never writes to it, so cutting the power at any moment leaves it exactly as it was.
- All writes (logs, temporary files, settings changes) go to **RAM** and disappear at power-off.
- The **boot partition** (`/boot/firmware`, holding the kernel and config.txt) is also mounted **read-only**.
- On every power-on the robot starts from the same known-good state.

The robot shows the current mode:

- web page badge: **SD PROTECTED** (green) or **SD WRITABLE** (yellow)
- `sudo robot-status`: `PROTECTED now` / `MAINTENANCE now`

---

## 3. The two modes

| | **PROTECTED** (normal use) | **MAINTENANCE** (making changes) |
|---|---|---|
| SD card | read-only | writable |
| Switch power off any time? | **Yes, always safe** | **No.** Shut down first (Settings → Shut down, SHUTDOWN button, or `sudo poweroff`) |
| Save calibration permanently | No: kept until the next reboot only (the page says so) | Yes |
| Install updates, edit files | Changes vanish at reboot | Yes |
| Turn on | `sudo robot-protect` or Settings → *Switch to PROTECTED mode* | |
| Turn on | | `sudo robot-maintenance` or Settings → *Switch to MAINTENANCE mode* |

Both switches reboot the Pi. The robot keeps standing during the reboot, because the PCA9685 keeps holding the servos.

### Typical workflow

```text
  install.sh  ->  reboot  ->  test + calibrate + "Save permanently"  ->  sudo robot-protect
                                                                            |
                         normal use, power off any time  <------------------+
                                     |
                need a change?  ->  sudo robot-maintenance  ->  change, save  ->  sudo robot-protect
```

---

## 4. What the scripts do

| Command | Action |
|---|---|
| `sudo robot-protect` | Checks that the running kernel matches the installed one (see below), runs `raspi-config nonint enable_bootro` (boot partition read-only) and `raspi-config nonint enable_overlayfs` (read-only root with a RAM overlay), then reboots |
| `sudo robot-maintenance` | Runs `raspi-config nonint disable_overlayfs`, then reboots. The boot partition stays read-only; to edit config.txt, run `sudo mount -o remount,rw /boot/firmware` |
| `sudo robot-status` | Shows the mode now and after the next reboot, power problems, service state and the hardware checks |

**Kernel check:** the protected boot image is built for the kernel that is running. If `apt upgrade` installed a newer kernel, reboot once before running `robot-protect`; the script refuses and tells you if this is needed.

---

## 5. How settings are saved safely

Calibration and thresholds live in `/var/lib/humanoid-robot/settings.json`, with a copy in `settings.json.bak`.

- **Saving** (maintenance mode only) is atomic. The robot writes a temporary file, forces it to the card (`fsync`), renames it over the old file, then syncs the folder. A power cut during a save leaves either the complete old file or the complete new file, never half a file. The same is done for the backup copy.
- **Loading never fails.** If the main file is damaged, the robot uses the backup; if both are damaged, it uses the built-in defaults. Every value is also checked: wrong types and dangerous servo angles are rejected or clamped. **The robot always boots.**
- In **protected mode**, *Save permanently* applies the change for the current session and tells you to switch to maintenance mode to keep it.

---

## 6. Other protections installed by `install.sh`

| Setting | File |
|---|---|
| System logs in RAM only, max 20 MB | `/etc/systemd/journald.conf.d/humanoid-robot.conf` |
| Hardware watchdog (auto-reboot if frozen) | `/etc/systemd/system.conf.d/humanoid-robot-watchdog.conf` + `dtparam=watchdog=on` |
| Swap file disabled | `dphys-swapfile` removed (if present) |
| Automatic apt downloads and man-db timers disabled | `apt-daily.timer`, `apt-daily-upgrade.timer`, `man-db.timer` |
| Shutdown button (kernel-level, works even if the program crashed) | `dtoverlay=gpio-shutdown,gpio_pin=27,...` in config.txt |
| Python files pre-compiled (no cache writes at runtime) | `python3 -m compileall /opt/humanoid-robot` |

---

## 7. Prove it works (do this once)

1. Check that `sudo robot-status` shows **PROTECTED now**.
2. Create a test file: `touch ~/test-file`, then switch the power off **without** shutting down.
3. Power on. `~/test-file` is **gone**, which shows nothing reached the SD card.
4. Repeat the hard power cut **10 times** at different moments: during boot, while speaking, while walking, while streaming video. The robot must boot and greet you every time.
5. Run `sudo robot-status` and check there are no under-voltage warnings. If there are, improve the 5 V wiring.

---

## 8. Keep a spare card (strongly recommended)

Even a protected card can fail physically. When the robot is fully set up and protected:

1. Shut the robot down and put the SD card in your PC.
2. Install **Win32 Disk Imager**, choose an image file name (for example `humanoid-robot-backup.img`) and click **Read**.
3. To restore, or to make a spare card, use **Raspberry Pi Imager → Use custom** with that `.img` file. Do **not** apply OS customisation when restoring.
4. Keep the spare card taped inside the robot.

---

## 9. Limits to know about

- In protected mode, RAM holds all changes. The Pi 3B has 1 GB, which is plenty for the robot, but do not copy large files to it while protected.
- Software installed while protected (`apt install …`) disappears at reboot. Install in maintenance mode.
- The robot's clock has no battery, and the robot has no internet connection on its own Wi-Fi, so log times can be wrong. This does not affect operation.
