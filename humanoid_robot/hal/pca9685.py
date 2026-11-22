"""Minimal PCA9685 16-channel PWM driver for hobby servos (I2C, smbus).

Written without extra libraries so it installs from apt only
(python3-smbus2, or python3-smbus as a fallback).
"""

import time

MODE1 = 0x00
MODE2 = 0x01
LED0_ON_L = 0x06
ALL_LED_ON_L = 0xFA
PRESCALE = 0xFE

MODE1_RESTART = 0x80
MODE1_AI = 0x20       # register auto-increment
MODE1_SLEEP = 0x10
MODE2_OUTDRV = 0x04   # totem-pole outputs
FULL_OFF = 0x10       # bit 4 of LEDn_OFF_H

OSC_HZ = 25_000_000


def prescale_for(freq_hz, osc_hz=OSC_HZ):
    """PRESCALE register value for a PWM frequency (datasheet 7.3.5)."""
    value = int(round(osc_hz / (4096.0 * freq_hz))) - 1
    return max(3, min(255, value))


def period_us_for(prescale, osc_hz=OSC_HZ):
    """Actual PWM period in microseconds for a PRESCALE value."""
    return 1_000_000.0 * 4096.0 * (prescale + 1) / osc_hz


def us_to_ticks(pulse_us, period_us):
    """Convert a pulse width to the 12-bit OFF count."""
    ticks = int(round(pulse_us * 4096.0 / period_us))
    return max(0, min(4095, ticks))


def _open_bus(bus_number):
    try:
        from smbus2 import SMBus
    except ImportError:  # pragma: no cover - fallback for python3-smbus
        from smbus import SMBus
    return SMBus(bus_number)


class PCA9685:
    def __init__(self, i2c_bus=1, address=0x40, freq_hz=50, bus=None):
        self.address = address
        self._bus = bus if bus is not None else _open_bus(i2c_bus)
        self._write(MODE2, MODE2_OUTDRV)
        self._write(MODE1, MODE1_AI)
        time.sleep(0.005)
        self.period_us = 20000.0
        # No all_off() here: if the robot program restarts, the PCA9685 keeps
        # holding the last pose instead of letting a standing robot collapse.
        self.set_frequency(freq_hz)

    def _write(self, register, value):
        self._bus.write_byte_data(self.address, register, value & 0xFF)

    def _read(self, register):
        return self._bus.read_byte_data(self.address, register)

    def set_frequency(self, freq_hz):
        prescale = prescale_for(freq_hz)
        old = self._read(MODE1) & ~MODE1_RESTART & 0xFF
        self._write(MODE1, old | MODE1_SLEEP)  # PRESCALE is only writable while asleep
        self._write(PRESCALE, prescale)
        self._write(MODE1, old)
        time.sleep(0.005)
        self._write(MODE1, old | MODE1_RESTART | MODE1_AI)
        self.period_us = period_us_for(prescale)

    def set_pulse_us(self, channel, pulse_us):
        off = us_to_ticks(pulse_us, self.period_us)
        self._bus.write_i2c_block_data(self.address, LED0_ON_L + 4 * channel,
                                       [0, 0, off & 0xFF, off >> 8])

    def channel_off(self, channel):
        self._bus.write_i2c_block_data(self.address, LED0_ON_L + 4 * channel, [0, 0, 0, FULL_OFF])

    def all_off(self):
        self._bus.write_i2c_block_data(self.address, ALL_LED_ON_L, [0, 0, 0, FULL_OFF])

    def close(self):
        try:
            self.all_off()
        finally:
            close = getattr(self._bus, "close", None)
            if close:
                close()
