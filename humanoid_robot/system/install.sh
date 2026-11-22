#!/usr/bin/env bash
# Humanoid Robot installer for Raspberry Pi OS Lite on a Raspberry Pi 3B / 3B+.
#
#   sudo bash humanoid_robot/system/install.sh
#
# Safe to run again (for example after you change the code). Needs internet
# for apt. Run it in MAINTENANCE mode (SD card writable), never while
# protection is on. Afterwards:  sudo reboot, test, then  sudo robot-protect
set -euo pipefail

APP_DIR=/opt/humanoid-robot
DATA_DIR=/var/lib/humanoid-robot
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYS_DIR="$SRC_DIR/system"
MARK_BEGIN="# >>> humanoid-robot >>>"
MARK_END="# <<< humanoid-robot <<<"
SSID="${ROBOT_WIFI_SSID:-Humanoid-Robot}"
HOTSPOT=robot-hotspot

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- checks
[ "$(id -u)" -eq 0 ] || die "Run with sudo:  sudo bash $0"
grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null || die "This is not a Raspberry Pi."
if grep -q "boot=overlay" /proc/cmdline; then
  die "SD card protection is ON. Run 'sudo robot-maintenance' (the Pi reboots), then run this again."
fi
command -v raspi-config >/dev/null || die "raspi-config not found. Use Raspberry Pi OS Lite."
systemctl is-active --quiet NetworkManager || die "NetworkManager is not running. Use Raspberry Pi OS Bookworm or newer."

if [ -d /boot/firmware ]; then BOOT=/boot/firmware; else BOOT=/boot; fi
CONFIG="$BOOT/config.txt"
if findmnt -no OPTIONS "$BOOT" | tr ',' '\n' | grep -qx ro; then
  mount -o remount,rw "$BOOT"   # read-only from an earlier robot-protect
fi

# ---------------------------------------------------------------- questions first, then unattended
PSK="${ROBOT_WIFI_PASSWORD:-}"
if [ -z "$PSK" ]; then
  while :; do
    read -r -s -p "Choose the password for the robot's Wi-Fi '$SSID' (8+ characters): " PSK; echo
    [ "${#PSK}" -ge 8 ] && break
    echo "Too short, try again."
  done
fi
[ "${#PSK}" -ge 8 ] || die "Wi-Fi password must have at least 8 characters."

COUNTRY="$(raspi-config nonint get_wifi_country 2>/dev/null || true)"
if [ -z "$COUNTRY" ]; then
  read -r -p "Two-letter Wi-Fi country code (for example US, GB, PH, DE): " COUNTRY
fi

# ---------------------------------------------------------------- 1. packages
step "1/9 Installing software packages (this can take 10-20 minutes)"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  python3 python3-aiohttp python3-picamera2 python3-gpiozero python3-lgpio \
  python3-spidev python3-smbus i2c-tools espeak-ng alsa-utils initramfs-tools
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-smbus2 || true

# ---------------------------------------------------------------- 2. interfaces
step "2/9 Enabling I2C, SPI and Wi-Fi country"
raspi-config nonint do_i2c 0
raspi-config nonint do_spi 0
[ -n "$COUNTRY" ] && raspi-config nonint do_wifi_country "${COUNTRY^^}" || true
rfkill unblock wifi 2>/dev/null || true

# ---------------------------------------------------------------- 3. config.txt
step "3/9 Configuring $CONFIG (audio, DHT22, shutdown button, watchdog)"
cp -n "$CONFIG" "$CONFIG.before-robot" 2>/dev/null || true
sed -i "/^$MARK_BEGIN\$/,/^$MARK_END\$/d" "$CONFIG"
sed -i -E 's/^dtparam=audio=on/#&  # disabled by humanoid-robot/' "$CONFIG"
sed -i -E 's/^(dtoverlay=vc4-kms-v3d)$/\1,noaudio/' "$CONFIG"
sed 's/\r$//' "$SYS_DIR/config.txt.snippet" >> "$CONFIG"

# ---------------------------------------------------------------- 4. program
step "4/9 Installing the robot program to $APP_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  rm -rf "$APP_DIR.new"
  mkdir -p "$APP_DIR.new"
  cp -r "$SRC_DIR/." "$APP_DIR.new/"
  rm -rf "$APP_DIR.new/sim_data"
  find "$APP_DIR.new" -name "__pycache__" -type d -prune -exec rm -rf {} +
  rm -rf "$APP_DIR.old"
  [ -d "$APP_DIR" ] && mv "$APP_DIR" "$APP_DIR.old"
  mv "$APP_DIR.new" "$APP_DIR"
  rm -rf "$APP_DIR.old"
fi
# Byte-compile now: in protected mode Python cannot write cache files.
python3 -m compileall -q "$APP_DIR" || true
mkdir -p "$DATA_DIR"
chmod 755 "$DATA_DIR"

# ---------------------------------------------------------------- 5. audio
step "5/9 Sound output (MAX98357A)"
[ -f /etc/asound.conf ] && cp -n /etc/asound.conf /etc/asound.conf.before-robot || true
sed 's/\r$//' "$SYS_DIR/asound.conf" > /etc/asound.conf

# ---------------------------------------------------------------- 6. SD card care
step "6/9 SD card care: RAM logs, no swap, no background updates, watchdog"
mkdir -p /etc/systemd/journald.conf.d /etc/systemd/system.conf.d
sed 's/\r$//' "$SYS_DIR/journald-volatile.conf" > /etc/systemd/journald.conf.d/humanoid-robot.conf
sed 's/\r$//' "$SYS_DIR/watchdog.conf" > /etc/systemd/system.conf.d/humanoid-robot-watchdog.conf
if systemctl list-unit-files dphys-swapfile.service >/dev/null 2>&1; then
  systemctl disable --now dphys-swapfile.service 2>/dev/null || true
  dphys-swapfile swapoff 2>/dev/null || true
  dphys-swapfile uninstall 2>/dev/null || true
fi
for timer in apt-daily.timer apt-daily-upgrade.timer man-db.timer; do
  systemctl disable --now "$timer" 2>/dev/null || true
done

# ---------------------------------------------------------------- 7. commands
step "7/9 Installing robot-protect, robot-maintenance and robot-status commands"
for cmd in robot-protect robot-maintenance robot-status; do
  sed 's/\r$//' "$SYS_DIR/$cmd" > "/usr/local/sbin/$cmd"
  chmod 755 "/usr/local/sbin/$cmd"
done

# ---------------------------------------------------------------- 8. service
step "8/9 Starting the robot program automatically at boot"
sed 's/\r$//' "$SYS_DIR/humanoid-robot.service" > /etc/systemd/system/humanoid-robot.service
systemctl daemon-reload
systemctl enable humanoid-robot.service

# ---------------------------------------------------------------- 9. hotspot
step "9/9 Creating the robot Wi-Fi hotspot '$SSID' (active after reboot)"
nmcli connection delete "$HOTSPOT" >/dev/null 2>&1 || true
nmcli connection add type wifi ifname wlan0 con-name "$HOTSPOT" autoconnect yes ssid "$SSID" \
  802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
  ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled \
  wifi-sec.key-mgmt wpa-psk wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp \
  wifi-sec.psk "$PSK" connection.autoconnect-priority 100 >/dev/null
sync

cat <<EOF

=====================================================================
 Installation finished.

 Next steps:
   1. sudo reboot
      After the reboot the Pi stops using your home Wi-Fi and starts
      its own Wi-Fi network:  $SSID  (password: the one you chose)
   2. Join that Wi-Fi with your phone and open  http://10.42.0.1
      (SSH still works:  ssh <user>@10.42.0.1)
   3. Check everything:  sudo robot-status
   4. Calibrate the servos on the Settings page and press "Save permanently".
   5. When everything works, turn on SD card protection:
         sudo robot-protect
      From then on you can switch the power off at any time.
=====================================================================
EOF
