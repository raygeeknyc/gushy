import logging
logging.getLogger('').setLevel(logging.DEBUG)
import os
import time
import Queue
import sys
import threading

try:
    import RPi.GPIO as GPIO
except RuntimeError:
    logging.error('Error importing RPi.GPIO!  This is probably because you need superuser privileges.  You can achieve this by using "sudo" to run your script')
GPIO.setmode(GPIO.BCM)

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image

import urllib
import urllib2

import calendar

POT_A_PIN = 18
POT_B_PIN = 24
PB1_PIN = 19
PB2_PIN = 25

try:
    import RPi.GPIO as GPIO
except RuntimeError:
    logging.error('Error importing RPi.GPIO!  This is probably because you need superuser privileges.  You can achieve this by using "sudo" to run your script')

GPIO.setup(PB1_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PB2_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

POT_MIN = 30    # Set this to the observed potentiometer minimum
POT_MAX = 170    # Set this to the observed potentiometer maximum
_POT_RANGE = (POT_MAX+1) - POT_MIN
logging.debug("pot range: {}".format(_POT_RANGE))

from datetime import datetime
import calendar
_EPOCH_BASE = calendar.timegm(datetime(1970, 1, 1).timetuple())
_ZIGGY_BASE_URL = 'ziggy-214721.appspot.com/settarget'

LED_MATRIX_ROWS = 16
LED_MATRIX_COLS = 32

def _discharge():
  GPIO.setup(POT_A_PIN, GPIO.IN)
  GPIO.setup(POT_B_PIN, GPIO.OUT)
  GPIO.output(POT_B_PIN, False)
  time.sleep(0.005)

def _charge_time():
  GPIO.setup(POT_B_PIN, GPIO.IN)
  GPIO.setup(POT_A_PIN, GPIO.OUT)
  count = 0
  GPIO.output(POT_A_PIN, True)
  while not GPIO.input(POT_B_PIN):
    count += 1
  return count
 
def _analog_read():
  _discharge()
  return _charge_time()

def getPotentiometerValue():
  return _analog_read()

def _getButton1():
  return not GPIO.input(PB1_PIN) 

def _getButton2():
  return not GPIO.input(PB2_PIN) 

SPEECH_TMP_FILE='/tmp/speech.wav'
PICO_CMD='/usr/bin/pico2wave -l en-US --wave "%s" "%s";echo "talk";/usr/bin/aplay "%s"'

_display = None

DATE_SET_DELAY_SECS = 1
DATE_POLL_DELAY_SECS = 0.5

def setupDisplay():
  options = RGBMatrixOptions()
  options.rows = 16
  options.cols = 32
  options.brightness = 100
  display = RGBMatrix(options = options)
  return display

def getDateAsUTCTimestamp(naive_datetime):
  " Convert datetime to the unix timestamp, UTC seconds since the epoch. "
  timestamp_utc = calendar.timegm(naive_datetime.timetuple())
  unix_ts = (timestamp_utc - _EPOCH_BASE)
  return unix_ts

def sendTargetDateToCloud(target_datetime, base_url):
  timestamp = getDateAsUTCTimestamp(target_datetime)
  query_params = urllib.urlencode({'datetime':'{}'.format(timestamp)})
  query = 'https://{}?{}'.format(base_url, query_params)
  logging.debug("sending {}".format(query))
  request = urllib2.urlopen(query)
  response = request.read()
  logging.debug("response received: {}".format(response))

def connectToCloudService():
  " Returns reference to timestore cloud service. "
  return _ZIGGY_BASE_URL

def getDateUpButton():
  " Returns True if up button is pressed "
  return _getButton1()

def getDateDownButton():
  " Returns True if down button is pressed "
  return _getButton2()

def getTimeOfDay():
  " Return hour of day from the potentiometer, scaled to 0..23. "
  raw = getPotentiometerValue()
  print("raw: {}".format(raw))
  if raw < POT_MIN:
    raw = POT_MIN
  if raw > POT_MAX:
    raw = POT_MAX
  print("clipped raw: {}".format(raw))
  tod = raw - POT_MIN
  print("tod: {}".format(tod))
  portion = (1.0*tod)/_POT_RANGE
  print("portion: {}".format(portion))
  hour = int(portion*24)
  return hour

def scrollDate(target, days_delta):
  """
  Args
    target base date
    days_delta number of days to increment target date.
  Returns adjusted date
  """
  d = target + datetime.timedelta(days=days_delta)
  return d

def scrollMonth(target, months_delta):
  """
  Args
    target base date
    months_delta number of months to increment target date.
  Returns adjusted date
  """
  d = target + datetime.timedelta(months=months_delta)
  return d

def showDate(display, target_date):
  " Display the date and time. "
  offscreen_canvas = display.CreateFrameCanvas()
  font = graphics.Font()
  font.LoadFont("fonts/4x6.bdf")  # Was 7x13.bdf in sample
  text_color = graphics.Color(0, 255, 255)
  date_str = target_date.strftime('%m.%d.%y\n')
  print("Date: {}".format(date_str))
  len = graphics.DrawText(offscreen_canvas, font, 1, 7, text_color, date_str)
  text_color = graphics.Color(255, 0, 255)
  time_str = target_date.strftime('%H:%M')
  print("Time: {}".format(time_str))
  len = graphics.DrawText(offscreen_canvas, font, 6, 14, text_color, time_str)
  time.sleep(0.05)
  offscreen_canvas = display.SwapOnVSync(offscreen_canvas)

def speakDate(target_date):
  " Speak the date and time, be well spoken. " 
  dow = calendar.day_name[target_date.weekday()]
  month = target_date.strftime('%B')
  day = target_date.strftime('%d')
  suffix = 'th'
  if day[-1:] == '1':
    suffix = 'st'
  if day[-1:] == '2':
    suffix = 'nd'
  if day[-1:] == '3':
    suffix = 'rd'
  hour = target_date.hour
  daypart = 'A. M. '
  if hour == 0:
    hour = 12
  elif hour > 12:
    hour -= 12
    daypart = 'P. M. '
  spoken_datetime = '{}, {} on {}, the {}{} of {}'.format(hour, daypart, dow, day, suffix, month)
  print("Saying: {}".format(spoken_datetime))
  try:
    os.system(PICO_CMD % (SPEECH_TMP_FILE, spoken_datetime, SPEECH_TMP_FILE))
    time.sleep(5)
  except Exception, e:
    logging.exception('Error speaking')

def processDateChanges(date_queue):
  logging.info("Starting date processor thread")

  while True:
    new_date = None
    try:
      t = date_queue.get(False)
      logging.debug("Date queue had an entry")
      new_date = t
    except Queue.Empty:
      if not new_date:
        logging.debug("Empty date queue, waiting")
        time.sleep(DATE_POLL_DELAY_SECS)
        continue
      logging.debug("New target date: {}".format(new_date))
      showDate(display, new_date)
      speakDate(new_date)
      sendTargetDateToCloud(new__date, datetime_service)
      new_date = None
      time.sleep(DATE_SET_DELAY_SECS)
    except Exception, e:
      logging.exception("Error processing dates")
      break
  logging.warning("Done processing dates")

def main():
  display = setupDisplay()
  datetime_service = connectToCloudService()
  target_date = datetime.now()
  previous_target_date = datetime.now()
  date_queue = Queue.Queue()
  try:
    date_setter = threading.Thread(target = processDateChanges, args=(date_queue))
    date_setter.start()
  except Exception, e:
    logging.exception("Error setting up date processor thread")
    sys.exit(-1)

  while True:
    if getDateDownButton() and getDateUpButton():
       slider_position = getTimeOfDay()
       logging.debug("slider: {}".format(slider_position))
       if slider_position < 12:
        target_date = scrollMonth(target_date, -1)   
       else:
        target_date = scrollMonth(target_date, 1)   
    else:
      if getDateDownButton():
        target_date = scrollDate(target_date, -1)   
      elif getDateUpButton():
        target_date = scrollDate(target_date, 1)   
      target_hour = getTimeOfDay()
      logging.debug("target_hour: {}".format(target_hour))
      target_date = target_date.replace(hour=target_hour, minute=0)
    if target_date != previous_target_date:
      date_queue.put(target_date)
      previous_target_date = target_date

    time.sleep(1)

main()
