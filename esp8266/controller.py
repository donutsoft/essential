import machine, time, utime
from umqtt.simple import MQTTClient
from machine import Pin

UNDEFINED = -1
OFF = 0
ON = 1
PULSING = 2
PUSH_BUTTON_ON_DELAY = .03
PUSH_BUTTON_OFF_DELAY = .05
DIFFUSER_TOPIC = b"diffuser"
LIGHT_TOPIC = b"light"
CLIENT = "homedic"

class Controller:
  def __init__(self, mqttHost):
    self.mqttHost = mqttHost
    self.buttonPushTimes = {}
    self.powerMode = OFF
    self.lightMode = OFF

  def mqttCallback(self, topic, msg):
    print('MQTT Callback:', topic, msg)
    if topic == b"homedic/light/effect":
      if msg == b"color_loop":
        self.setLightMode(2)
      elif msg == b"none":
        if self.lightMode == 2:
          self.setLightMode(1)
        else:
          self.setLightMode(0)
    elif topic == b"homedic/light/switch":
      if int(msg) == 1 and self.lightMode == 2:
        print("Ignoring message")
        # HomeAssistant turns bulb on after setting effect.
        return
      self.setLightMode(int(msg) % 3)
    elif topic == b"homedic/fan/set":
      if msg == b"on":
        if self.powerMode == 0:
          self.setPowerMode(1)
        else:
          # Advertise the new state in the event that Home assistnat restarted
          self.setPowerMode(self.powerMode)
      elif msg == b"off":
        self.setPowerMode(0)
    elif topic == b"homedic/fan/speed":
      if msg == b"low":
        self.setPowerMode(2)
      elif msg == b"high":
        self.setPowerMode(1)
      elif msg == b"off":
        self.setPowerMode(0)

  def powerSwitchButtonPush(self, pin):
    print("Power switch button push")
    self.setPowerMode((self.powerMode + 1) % 3)

  def lightSwitchButtonPush(self, pin):
    print("Light switch button push")
    self.setLightMode((self.lightMode + 1) % 3)

  def setPowerMode(self, value):
    print("Setting power mode to: " + str(value))
    while self.powerMode is not value:
      self.powerSwitchOutput.value(1)
      time.sleep(PUSH_BUTTON_ON_DELAY)
      self.powerSwitchOutput.value(0)
      time.sleep(PUSH_BUTTON_OFF_DELAY)
      self.powerMode = (self.powerMode + 1) % 3
    if self.powerMode == 0:
      self.client.publish(b'homedic/fan/speed_state', b'off')
      self.client.publish(b'homedic/fan/state', b'off') 
    if self.powerMode == 1:
      self.client.publish(b'homedic/fan/speed_state', b'high')
      self.client.publish(b'homedic/fan/state', b'on')
    if self.powerMode == 2:
      self.client.publish(b'homedic/fan/speed_state', b'low')
      self.client.publish(b'homedic/fan/state', b'on')

  def setLightMode(self, value):
    print("Setting light mode to: " + str(value))
    while self.lightMode is not value:
      self.lightSwitchOutput.value(1)
      time.sleep(PUSH_BUTTON_ON_DELAY)
      self.lightSwitchOutput.value(0)
      time.sleep(PUSH_BUTTON_OFF_DELAY)
      self.lightMode = (self.lightMode + 1) % 3
    if self.lightMode == 0 or self.lightMode == 1:
      self.client.publish(b'homedic/light/status', bytes(str(self.lightMode), 'utf-8'))
      self.client.publish(b'homedic/light/effect_status', b'none')
    if self.lightMode == 2:
      self.client.publish(b'homedic/light/status', bytes(str(1), 'utf-8'))
      self.client.publish(b'homedic/light/effect_status', b'color_loop')

  def debounce(self, pin, callbackMethod):
    currentTime = utime.ticks_ms()
    pinName = str(pin)

    if pin.value() == 1:
      self.buttonPushTimes[pinName] = currentTime
      return

    if pinName in self.buttonPushTimes:
      if currentTime - self.buttonPushTimes[pinName] > 150:
        callbackMethod(pin)
    else:
        callbackMethod(pin)
    self.buttonPushTimes[pinName] = currentTime

  def initializeMqtt(self):
    self.client = MQTTClient(CLIENT, self.mqttHost)
    self.client.set_callback(self.mqttCallback)
    self.client.connect()
    self.client.subscribe(b'homedic/light/switch')
    self.client.subscribe(b'homedic/light/effect')
    self.client.subscribe(b'homedic/fan/set')
    self.client.subscribe(b'homedic/fan/speed')

  def start(self):
    self.initializeMqtt()
    self.powerSwitchInput = Pin(5, machine.Pin.IN, machine.Pin.PULL_UP) # D1
    self.powerSwitchOutput = Pin(4, machine.Pin.OUT) # D2
    self.lightSwitchOutput = Pin(14, machine.Pin.OUT) # D5
    self.lightSwitchInput = Pin(2, machine.Pin.IN, machine.Pin.PULL_UP) # D4

    self.setLightMode(0)
    self.setPowerMode(0)

    self.lightSwitchInput.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=lambda pin: self.debounce(pin, self.lightSwitchButtonPush))
    self.powerSwitchInput.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=lambda pin: self.debounce(pin, self.powerSwitchButtonPush))
    Pin(2, machine.Pin.OUT).value(1) # Turn status light off to indicate it booted
    while True:
      self.client.wait_msg()
