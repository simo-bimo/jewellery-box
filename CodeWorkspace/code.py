import time
import random

import board
import alarm
import digitalio
import adafruit_lis3dh
from adafruit_magtag.magtag import MagTag

import ssl
import wifi
import socketpool
import adafruit_requests

from secrets import secrets

DATA_URL = "https://simo-bimo.github.io/belles-box-quotes/quotes.json"
ACC_THRESHOLD = 6.5
Y_WAIT_TIME = 0.5


master_json = None

do_lights = False
light_values = (100, 100, 100)
current_index = 0
if alarm.wake_alarm != None:
    do_lights = alarm.sleep_memory[0]
    light_values = tuple([alarm.sleep_memory[i] for i in range(1,4)])
    current_index = alarm.sleep_memory[4]

# TODO Change the -auto-level on some of the images so they aren't blown out trying to capture contrast.
# TODO Make sure they're actually 4 bit. They're 24 bit. This'd give you 4 or 5 times as many images.

# We don't care about these because we assume the screen is already set.
# They don't need to be saved.
number_quotes = 0
quotes = []

def connect_and_download():
    global master_json
    global number_quotes
    global do_lights
    global light_values
    global quotes
    global current_index

    # Connect to wifi
    # TODO Multiple wifi network support.
    wifi.radio.connect(secrets["ssid"], secrets["password"])

    # TODO No connection, choose a default image.

    # Create a socket pool
    pool = socketpool.SocketPool(wifi.radio)
    # Make an SSL Session
    session = adafruit_requests.Session(pool, ssl.create_default_context())

    master_json = session.get(DATA_URL).json()
    number_quotes = len(master_json[1]['quotes'])
    do_lights = master_json[0]['settings']['do_lights']
    light_values = tuple(master_json[0]['settings']['light_RGB'])
    quotes = master_json[1]['quotes']

    print(f"Do lights is set to: {do_lights}, with RGB values of: {light_values}.")
    print(f"There are {number_quotes} quotes.")
    print(f"They are: {quotes}")
    alarm.sleep_memory[0] = do_lights
    alarm.sleep_memory[1] = light_values[0]
    alarm.sleep_memory[2] = light_values[1]
    alarm.sleep_memory[3] = light_values[2]
    alarm.sleep_memory[4] = (current_index+1) % number_quotes
    pass

def update_screen(mg):
    # index = random.randrange(0, int(number_quotes-1))
    index = current_index
    print(f"Selected quote #{index+1} of {number_quotes}.")
    if (quotes[index]['image'] == 'none'):
        mg.graphics.set_background(int(0))
    elif (quotes[index]['image'] == 'black'):
        mg.graphics.set_background(int(255 << 16 | 255 << 8 | 255))
    else:
        mg.graphics.set_background(f"/bmps/{quotes[index]['image']}")

    if quotes[index]['text'] != 'none':
        mg.add_text(
            text_position=(
                mg.graphics.display.width * quotes[index]['x_position'],
                mg.graphics.display.height * quotes[index]['y_position']
            ),
            text_scale=quotes[index]['text_size'],
            text_anchor_point=(0.5, 0.5),
        )
        mg.set_text(quotes[index]['text'])

    pass

def accelerometer_setup():
    # Lower power mode, 25Hz, XYZ enabled
    lis._write_register_byte(0x20, 0b00111111)

    # Set interrupt to INT1 register
    lis._write_register_byte(0x22, 0b01000000)

    # Block data update
    lis._write_register_byte(0x23, 0b10000000)

    # 4D gyro with nonlatched interrupt on INT1.
    lis._write_register_byte(0x24, 0b00000100)
    
    # Enable High Y interrupts on INT1
    # 6D position recognition
    lis._write_register_byte(0x30, 0b11001000)

    # Set the threshold (i.e. how much leeway?) for the interrupt to occur
    lis._write_register_byte(0x32, 0b00110000)

    # Amount of time required is 1 * LSB = 0.04s (because we're in 25Hz mode)
    lis._write_register_byte(0x33, 0x01)
    pass

magtag = MagTag()
global lis

"""
Main operational checks.
"""
i2c = board.I2C()
lis = adafruit_lis3dh.LIS3DH_I2C(i2c, address=0x19)

x,y,z = lis.acceleration

print(f"Accelerometer: [{x}, {y}, {z}]")

# _ = lis._read_register_byte(0x31)

# Loop until the box is closed.
while (y >= ACC_THRESHOLD):
    # TODO add a check for the light sensor here to see if it's worthwhile

    # (If it's not dark, don't waste battery).
    if (do_lights):
        # print("Doing the lights!")
        magtag.peripherals.neopixel_disable = False
        magtag.peripherals.neopixels.fill(light_values)

    time.sleep(Y_WAIT_TIME)
    x,y,z = lis.acceleration

# We assume that once the 5 second light timer happens,
# The box is closed, so it's safe to connect to wifi and redownload.

if (z > ACC_THRESHOLD or alarm.wake_alarm == None):
    connect_and_download()
    update_screen(magtag)
    magtag.refresh()

"""
Reset things to go to sleep
"""
magtag.peripherals.neopixel_disable = True

accelerometer_setup()
# Reset the interrupt bit.
_ = lis._read_register_byte(0x31)

#TODO Add an alarm for time aswell, to wake up at 3am (or at settings.reload_time) and download from the web again.
pin_alarm = alarm.pin.PinAlarm(pin=board.ACCELEROMETER_INTERRUPT, value=True)
alarm.exit_and_deep_sleep_until_alarms(pin_alarm)