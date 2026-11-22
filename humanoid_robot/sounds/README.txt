Optional recorded voice files
=============================

By default the robot speaks with the offline espeak-ng voice.
To use your own recording for a phrase, put a WAV file here named after the
phrase key from config/defaults.json ("phrases" section), for example:

    greeting.wav      played at every startup instead of the synthetic greeting
    ready.wav         "I am ready to assist you."
    estop_on.wav      when the emergency stop is pressed
    obstacle.wav      "Obstacle ahead."

Phrases that contain {reason}, {ssid} or {address} (emergency, warning,
connect_info) change every time, so leave those to the synthetic voice.

Format: 16-bit PCM WAV, mono or stereo, 22050 or 44100 Hz. On Windows you can
record with Audacity and export as "WAV (Microsoft) signed 16-bit PCM".
Copy new files while the robot is in MAINTENANCE mode, then run the installer
again (or copy them to /opt/humanoid-robot/sounds/).
