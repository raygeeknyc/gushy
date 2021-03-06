import logging
logging.getLogger('').setLevel(logging.DEBUG)
import os
import time

a_pin = 18
b_pin = 24
PB1_PIN = 19
PB2_PIN = 25

try:
    import RPi.GPIO as GPIO
except RuntimeError:
    logging.error('Error importing RPi.GPIO!  This is probably because you need superuser privileges.  You can achieve this by using "sudo" to run your script')

GPIO.setmode(GPIO.BCM)

GPIO.setup(PB1_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PB2_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

POT_MIN = 0    # Set this to the observed potentiometer minimum
POT_MAX = 1024 # Set this to the observed potentiometer maximum
_POT_RANGE = (POT_MAX+1) - POT_MIN

def _discharge():
  GPIO.setup(a_pin, GPIO.IN)
  GPIO.setup(b_pin, GPIO.OUT)
  GPIO.output(b_pin, False)
  time.sleep(0.005)

def _charge_time():
  GPIO.setup(b_pin, GPIO.IN)
  GPIO.setup(a_pin, GPIO.OUT)
  count = 0
  GPIO.output(a_pin, True)
  while not GPIO.input(b_pin):
    count += 1
  return count
 
def _analog_read():
  _discharge()
  return _charge_time()

def getPotentiometerValue():
  return _analog_read()

def getButton1():
  return GPIO.input(PB1_PIN) 

def getButton2():
  return GPIO.input(PB2_PIN) 

def main():
  while True:
    target_hour = getPotentiometerValue()
    print "Pot: {}".format(target_hour)
    print "Button 1: {}".format(getButton1())
    print "Button 2: {}".format(getButton2())
    time.sleep(1)

main()
