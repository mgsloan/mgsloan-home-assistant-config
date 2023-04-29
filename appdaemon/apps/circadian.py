import hassapi as hass
import math
from datetime import datetime, timedelta, time
import pytz
import traceback

class Circadian(hass.Hass):

  def initialize(self):
    self.timezone = pytz.timezone('US/Mountain')
    self.run_every(self.periodic_callback, 'now', 0.5)
    self.listen_event(self.on_tag_scanned, 'tag_scanned')

  def on_tag_scanned(self, event_name, data, kwargs):
    self.now = self.get_now()
    expiry = str(self.now + timedelta(minutes = 30))
    if data['tag_id'] == 'e27da444-ee3f-4543-8a45-769505561e15':
      self.set_state('circadian.string_light_override', state='off', attributes= {'override_expiry': expiry })
    elif data['tag_id'] == 'cae6c71b-8160-4690-8046-18a62b58d3be':
      self.set_state('circadian.string_light_override', state='on', attributes= {'override_expiry': expiry })

  def periodic_callback(self, kwargs):
    self.now = self.get_now()
    self.at_home = self.get_state('device_tracker.pixel_6a') == 'home'

    self.errors = []
    self.record_errors(
      lambda: self.update_string_lights(),
      lambda: self.turn_off('switch.string_lights'))
    self.record_errors(
      lambda: self.set_switch('switch.fresh_air', self.now_is_between('21:00:00', '10:00:00') and self.at_home),
      lambda: self.turn_on('switch.fresh_air'))

    # Figure out next sleep schedule after 8pm.

    self.record_errors(
      lambda: self.once_per_day('update_sleep_schedule', min_time='20:00:00', action=self.update_sleep_schedule))
    self.record_errors(
      lambda: self.light_alarm(),
      lambda: self.turn_off('light.room_strip_light'))

    self.report_errors()

  def update_string_lights(self):
    state = self.now_is_between('sunset - 00:30:00', '23:00:00') and self.at_home
    override = self.get_state('circadian.string_light_override', attribute='all')
    if override:
      expiry_str = override.get('attributes', {}).get('override_expiry')
      if expiry_str and datetime.fromisoformat(expiry_str) > self.now:
        override_state = override.get('state')
        if override_state == 'on':
          state = True
        elif override_state == 'off':
          state = False
    self.set_switch('switch.string_lights', state)

  def light_alarm(self):
    # calendar_state = self.get_state('calendar.automation', attribute='all')
    # if calendar_state.get('state') == 'on':
    #   calendar = calendar_state.get('attributes')
    #   event = calendar.get('message')
    #   if event and 'wake' in event.lower():
    #     wake_start = self.parse_datetime(calendar['start_time'])
    #     wake_end = self.parse_datetime(calendar['end_time'])
    #     strip_light_on = True

    wake_start_str = '08:30:00'
    wake_end_str = '09:00:00'
    blink_time_str = '09:15:00'
    off_time_str = '09:30:00'

    strip_light_on = False
    blink_strip_light = False
    if self.now_is_between(wake_start_str, blink_time_str):
      strip_light_on = True
      wake_start = self.parse_today_time(wake_start_str)
      wake_end = self.parse_today_time(wake_end_str)
    elif self.now_is_between(blink_time_str, off_time_str):
      blink_strip_light = True

    light_name = 'light.room_string_lights'

    if not self.at_home:
      self.set_switch(light_name, False)
    elif strip_light_on:
      t = max(0, min(1, (self.now - wake_start) / (wake_end - wake_start)))
      self.turn_on(
          light_name,
          brightness=pow(t,2) * 1000,
          color_temp_kelvin=self.lerp(2702, 6024, pow(t, 4)))
    elif blink_strip_light:
      if self.get_state(light_name) == 'on':
        self.turn_off(light_name)
      else:
        self.turn_on(light_name, brightness = 1000, color_temp_kelvin = 6024)
    else:
      self.set_switch(light_name, False)

  def record_errors(self, action, fallback=None):
    try:
      action()
    except Exception as e:
      self.errors.append(''.join(traceback.TracebackException.from_exception(e).format()))
      if fallback:
        self.record_errors(fallback)

  def report_errors(self):
    if self.errors:
      raise Exception('\n\n'.join(self.errors))

  def update_sleep_schedule(self):
    sleep_session = self.get_state('sensor.michael_s_previous_sleep_session', attribute='all')['attributes']
    session_start = datetime.strptime(sleep_session['Session Start'], '%Y-%m-%dT%H:%M:%S%z').astimezone(self.timezone)
    time_slept = timedelta(seconds=sleep_session['Time Slept'])
    wakeup_time = (session_start + time_slept).time()
    self.log('session start = ' + str(session_start))
    self.log('now = ' + str(self.now))
    self.log(str(wakeup_time))

  # TODO: ideally would also handle early AM, and offset last update
  # date properly, to handle case where controller is off.
  def once_per_day(self, name, action, min_time=None, max_time=None):
    if min_time and self.to_time(min_time) > self.now.time():
      return
    if max_time and self.to_time(max_time) < self.now.time():
      return

    date_format = '%Y-%m-%d'
    last_update_name = 'circadian.last_' + name + '_date'
    last_update = self.get_state(last_update_name)
    today = self.now.date()
    if not last_update or datetime.strptime(last_update, date_format).date() != today:
      action()
      self.set_state(last_update_name, state=today.strftime(date_format))

  def set_switch(self, switch, desired_state):
    state = self.get_state(switch) == 'on'
    # self.log('state of ' + switch + ' is ' + str(state) + ' and desired state is ' + str(desired_state))
    if state == desired_state:
      return
    if desired_state:
      self.turn_on(switch)
    else:
      self.turn_off(switch)

  def lerp(self, fr, to, t):
    return fr + t * (to - fr)

  def parse_datetime(self, x):
    return self.timezone.localize(datetime.strptime(x, '%Y-%m-%d %H:%M:%S'))

  def parse_today_time(self, x):
    return self.timezone.localize(datetime.combine(self.now, datetime.strptime(x, '%H:%M:%S').time()))

  def to_time(self, x):
    if isinstance(x, time):
      return x
    elif isinstance(x, str):
      return datetime.strptime(x, '%H:%M:%S').time()
    else:
      raise TypeError(str(type(x)) + ' not supported.')
