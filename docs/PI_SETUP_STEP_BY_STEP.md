# Raspberry Pi 3 Setup: Start to Finish (Raspberry Pi OS Lite)

This guide covers a brand-new Raspberry Pi 3 and a fresh microSD card, all the way to the robot program running.
Do the steps in order and copy each command exactly.

- **PC** = your Windows computer. Its commands go in **PowerShell**.
- **Pi** = the Raspberry Pi. Its commands go in the **SSH window** (that is, PowerShell after you run `ssh`).
- `#` starts a comment. Do not type the comment part.
- When you type a password in the terminal, **nothing shows on screen**. That is normal. Type it and press Enter.

## Your SD card settings (already flashed and checked)

| Setting | Value on your card |
|---|---|
| OS | Raspberry Pi OS **Lite 32-bit** (2026-10-06 build) |
| Username | `roboterwin` |
| Hostname | `robot`, so the Pi is `robot.local` on the network |
| Wi-Fi for setup | your phone hotspot **nubia Neo 5 GT 5G** |
| Wi-Fi country / time zone | PH / Asia/Manila |
| SSH | ON, with password login |
| Robot program | `humanoid_robot` folder copied onto the card |

If the card already works, skip Part 1 and start at **Part 2**.

---

## Part 1: Flash the OS (only for a new or broken card)

1. Install **Raspberry Pi Imager** from https://www.raspberrypi.com/software/
2. Insert the microSD card into the PC and open Imager.
3. Choose:
   - **Device:** Raspberry Pi 3
   - **OS:** Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)**
   - **Storage:** your microSD card. Check the size: the card should show about 29–32 GB. **Do not pick your PC's hard disk.**
4. Customisation (Imager 1.x: click **Edit settings**; Imager 2.x: the Customisation pages):
   - Hostname: `robot`
   - Username: `roboterwin`, plus a password you will remember (write it down)
   - Wi-Fi: SSID `nubia Neo 5 GT 5G` and the hotspot password. Type the name exactly, with capitals and spaces.
   - Wi-Fi country: `PH`, time zone `Asia/Manila`, keyboard `ph` or `us`
   - Services: **Enable SSH** → **Use password authentication**
5. Click **Write**, answer **Yes**, and wait for **Write** and **Verify** to finish. Do not remove the card early.
6. Take the card out and put it back in. Windows shows a drive named **bootfs**.

> **IMPORTANT:** Windows may pop up *"You need to format the disk in drive X: before you can use it."* That is the Linux partition, which Windows cannot read. **Click Cancel. Never format it**, or the OS is erased.

7. Copy the robot program onto the card. Change `D:` if your bootfs drive has a different letter:

```powershell
Copy-Item -Recurse -Force "C:\xampp\htdocs\erwin robot\humanoid_robot" D:\
```

---

## Part 2: Before you power on (avoids 90% of problems)

1. **Check the card** in PowerShell on the PC. It must print `True`:

```powershell
Test-Path D:\humanoid_robot\system\install.sh
```

2. **Eject the card safely.** Do not just pull it out:

```powershell
(New-Object -ComObject Shell.Application).Namespace(17).ParseName('D:').InvokeVerb('Eject')
```

3. **Set up the phone hotspot** (nubia Neo 5 GT 5G):
   - Band: **2.4 GHz**. The Raspberry Pi 3 **cannot see 5 GHz** hotspots.
   - Security: **WPA2-Personal** (or WPA2/WPA3 mixed). Do not use WPA3-only.
   - Keep the **same name and password** you put in Imager.
   - Turn **mobile data ON**. Setup downloads about 200–500 MB.
   - Turn off *"Turn off hotspot automatically when no devices are connected"*.
   - Keep the phone plugged into a charger.
4. **Connect your PC to the same phone hotspot.**
5. **Power supply:** use a good **5 V 2.5 A** micro-USB supply. For this setup the Pi needs nothing connected except the SD card and power: no servos and no robot battery yet. A weak phone charger causes under-voltage and SD card errors.

---

## Part 3: First boot

1. Put the microSD card into the Pi (contacts facing the board) and plug in the power.
2. **Wait 5 minutes.** On the first boot the Pi grows the file system, creates your user, joins the hotspot and installs a few things. It may restart once by itself. **Do not unplug it during this time.**
3. Check that the Pi has joined the hotspot: on the phone, open **Hotspot → Connected devices**. You should see **robot** and its IP address (for example `192.168.43.57`). Write the IP down.
4. On the PC, test the connection:

```powershell
ping robot.local
```

If `robot.local` does not answer, use the IP address from the phone instead of `robot.local` in every command below.

5. Connect with SSH:

```powershell
ssh roboterwin@robot.local
```

- First time: it asks *"Are you sure you want to continue connecting?"*. Type `yes` and press Enter.
- Type your **Pi password** (nothing shows while typing).
- You are in when the prompt looks like `roboterwin@robot:~ $`

> If you re-flashed the card and SSH says *"REMOTE HOST IDENTIFICATION HAS CHANGED"*, run this on the PC, then connect again:
> ```powershell
> ssh-keygen -R robot.local
> ```

---

## Part 4: Commands on the Pi (copy them one at a time)

### 4.1 Wait until first-boot setup is completely finished

```bash
cloud-init status --wait
```

Wait until it prints `status: done`. This can take a few minutes. If it prints `status: error`, you can still continue; that usually means one download failed and is fixed by step 4.3.

### 4.2 Check that the system is right

```bash
cat /proc/device-tree/model; echo
```
Expected: `Raspberry Pi 3 Model B Rev 1.2` (or `3 Model B Plus`).

```bash
dpkg --print-architecture
```
Expected: `armhf` (the 32-bit Lite OS).

```bash
sudo whoami
```
Type your Pi password. Expected: `root`.

```bash
ping -c 3 archive.raspberrypi.com
```
Expected: 3 replies, which means the internet works. If you see `unknown host`, the phone has no mobile data. Fix that first.

```bash
date
```
The date and time must be correct (Philippines time). If they are wrong, wait 1 minute and run `date` again. The Pi sets its clock from the internet.

```bash
vcgencmd get_throttled
```
Expected: `throttled=0x0`. Any other value means **the power supply is too weak**. Change it before you continue.

### 4.3 Update the OS (10–30 minutes on a Pi 3)

```bash
sudo apt update
```

```bash
sudo apt full-upgrade -y
```

```bash
sudo apt install -y avahi-daemon
```

```bash
sudo reboot
```

The SSH window closes. **Wait 1–2 minutes**, then connect again from the PC:

```powershell
ssh roboterwin@robot.local
```

### 4.4 Copy the robot program from the SD card to your home folder

```bash
cp -r /boot/firmware/humanoid_robot ~/
```

```bash
ls ~/humanoid_robot/system/install.sh
```
Expected: `/home/roboterwin/humanoid_robot/system/install.sh`

### 4.5 Run the robot installer (10–20 minutes)

```bash
sudo bash ~/humanoid_robot/system/install.sh
```

It asks:

1. Your **Pi password** (for sudo).
2. **"Choose the password for the robot's Wi-Fi 'Humanoid-Robot'"**: make up a **new** password of at least 8 characters and **write it down**. Your phone will use it to connect to the robot.
3. If it asks for a country code, type `PH`.

Then it runs by itself through steps `1/9` to `9/9`. Keep the SSH window open and the phone hotspot on.
It is finished when it prints **`Installation finished.`**

> If the connection drops during the install, reconnect with SSH and run these two commands. The installer is safe to run again.
> ```bash
> sudo dpkg --configure -a
> ```
> ```bash
> sudo bash ~/humanoid_robot/system/install.sh
> ```

### 4.6 Reboot into robot mode

```bash
sudo reboot
```

**What changes now:** the Pi **stops using your phone hotspot** and creates its own Wi-Fi network called **Humanoid-Robot**.

1. On the PC (and the phone), connect to Wi-Fi **Humanoid-Robot** with the robot Wi-Fi password from step 4.5. If Windows or the phone says *"No internet"*, choose **Stay connected**.
2. Connect again with SSH. The address is now always **10.42.0.1**:

```powershell
ssh roboterwin@10.42.0.1
```

### 4.7 Check that everything is running

```bash
sudo robot-status
```

```bash
systemctl status humanoid-robot --no-pager
```
Expected: `active (running)` in green.

```bash
journalctl -u humanoid-robot -n 50 --no-pager
```
This shows the robot program's last 50 log lines. It should have no `ERROR` lines, except for parts that are not wired yet.

Then open **http://10.42.0.1** in the phone's browser. The robot control page with the joystick should appear.

> Without the robot hardware connected, some startup checks show **FAIL** (servos, sensors, camera). That is normal at this point. They turn **OK** after you wire the parts in Part 5.

---

## Part 5: Wire the hardware, then test

1. Always shut down before you touch any wire:

```bash
sudo shutdown -h now
```

Wait until the green LED on the Pi stops blinking (about 20 seconds), **then** unplug the power.

2. Wire everything by following [WIRING.md](WIRING.md) and its *pre-power checklist*.
3. Power on, connect to Wi-Fi **Humanoid-Robot**, and connect with SSH (`ssh roboterwin@10.42.0.1`).
4. Check that the PCA9685 servo board is detected:

```bash
sudo i2cdetect -y 1
```
Expected: `40` appears in the table (`70` may appear too, which is normal).

5. Check the status again. All parts should now say OK:

```bash
sudo robot-status
```

6. Test each part and calibrate the servos on **http://10.42.0.1/settings**, following [BUILD_GUIDE.md](BUILD_GUIDE.md) Steps 7 and 8. Press **Save permanently** when you finish.

---

## Part 6: Protect the SD card (last step, do not skip)

Until this step, **never pull the power without `sudo shutdown -h now` first**. The SD card can get corrupted.

When everything works and the calibration is saved:

```bash
sudo robot-protect
```

Answer `y`. The Pi works for about 1 minute and reboots by itself. Connect again and check:

```bash
sudo robot-status
```
Expected: `PROTECTED now`. The web page also shows **SD PROTECTED** in green.

From now on the SD card is read-only, so **you can switch the power off at any time** without damage.

To change the software later (the SD card becomes writable again):

```bash
sudo robot-maintenance
```

The Pi reboots. Make your changes, then run `sudo robot-protect` again. See [SD_CARD_PROTECTION.md](SD_CARD_PROTECTION.md).

---

## Later: give the Pi internet again (for updates)

Robot mode has no internet. To use the phone hotspot again for a while:

1. Turn the phone hotspot on (2.4 GHz).
2. On the Pi (SSH via 10.42.0.1), run the command below. Your SSH session **will disconnect**, which is expected:

```bash
sudo nmcli connection down robot-hotspot
```

3. Connect the PC to the phone hotspot again, then run `ssh roboterwin@robot.local`.
4. Do your updates, then run `sudo reboot`. The robot's own Wi-Fi comes back.

---

## Quick fixes

| Problem | Fix |
|---|---|
| `ping robot.local` fails | Use the IP from the phone's *Connected devices* list: `ssh roboterwin@<IP>` |
| The Pi never appears on the hotspot | Hotspot must be **2.4 GHz** and WPA2, with the exact same name and password. Re-flash (Part 1) if you typed them wrong. |
| `Connection refused` / `timed out` on SSH | Wait 2 more minutes (first boot is slow), then try again |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | On the PC: `ssh-keygen -R robot.local` (or `ssh-keygen -R 10.42.0.1`) |
| `Could not get lock /var/lib/dpkg/lock` | Something is still installing. Run `cloud-init status --wait`, wait 2 minutes, try again. |
| `dpkg was interrupted` | `sudo dpkg --configure -a`, then run the command again |
| `throttled=` is not `0x0` | Power supply too weak or cable too thin. Use a 5 V 2.5 A supply. |
| Installer says `SD card protection is ON` | `sudo robot-maintenance`, wait for the reboot, run the installer again |
| Phone cannot open http://10.42.0.1 | Phone must be on Wi-Fi **Humanoid-Robot**. Turn mobile data off for a moment, or choose *Stay connected* on the "No internet" warning. |
| Windows asks to format the SD card | **Cancel.** Never format it. |
| Pi does not boot at all (only red LED, no green blinking) | Re-flash the card (Part 1), or try a different good-quality card |

More help: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
