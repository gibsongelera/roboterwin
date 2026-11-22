"""GPIO pin map for the Humanoid Robot (BCM numbering).

This file is the single source of truth for the wiring. It MUST match
docs/WIRING.md and docs/wiring_diagram.svg. Physical header pins are given in
the comments.

Pins that are used by kernel drivers (set up in /boot/firmware/config.txt by
system/install.sh) are listed for reference only; the Python code never
claims them.
"""

# --- I2C1: PCA9685 16-channel servo driver -------------------------------
I2C_BUS = 1               # SDA = GPIO2 (pin 3), SCL = GPIO3 (pin 5)
PCA9685_ADDRESS = 0x40
PCA9685_OE = 22           # pin 15, active-low output enable (HIGH = servos off)

# --- DHT22 temperature / humidity ----------------------------------------
DHT22_DATA = 4            # pin 7, read through the kernel "dht11" IIO driver

# --- HC-SR04 ultrasonic distance sensor ----------------------------------
ULTRASONIC_TRIGGER = 23   # pin 16
ULTRASONIC_ECHO = 24      # pin 18, through a 1k / 2k voltage divider (5 V -> 3.3 V)

# --- SPI0: MCP3008 analog-to-digital converter ---------------------------
SPI_BUS = 0               # MOSI GPIO10 (19), MISO GPIO9 (21), SCLK GPIO11 (23)
SPI_DEVICE = 0            # CE0 = GPIO8 (pin 24)
ADC_CH_MQ2 = 0            # MQ-2 analog output through a 10k / 20k divider
ADC_CH_BATTERY = 1        # battery voltage through a 100k / 22k divider

# --- Alerts ----------------------------------------------------------------
BUZZER = 17               # pin 11, drives an NPN transistor (S8050 / 2N2222)
LED_GREEN = 5             # pin 29, two green LEDs, each with its own 330 ohm resistor
LED_YELLOW = 6            # pin 31, two yellow LEDs
LED_RED = 13              # pin 33, two red LEDs

# --- Push buttons (to GND, internal pull-ups) --------------------------------
BUTTON_ESTOP = 16         # pin 36, software emergency stop (latching)
BUTTON_MODE = 26          # pin 37, press = next mode, hold 2 s = reset E-stop
BUTTON_SHUTDOWN = 27      # pin 13, hold 2 s = clean shutdown (kernel gpio-shutdown)

# --- I2S audio: MAX98357A (kernel driver, reference only) ------------------
I2S_BCLK = 18             # pin 12
I2S_LRCLK = 19            # pin 35
I2S_DIN = 21              # pin 40

# Spare / do-not-use: GPIO20 (I2S data-in), GPIO7 (SPI CE1), GPIO14/15 (UART),
# GPIO12, GPIO25.
