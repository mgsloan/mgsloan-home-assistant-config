import hassapi as hass

class NfcCounter(hass.Hass):

  def initialize(self):
    self.COUNTER_PREFIX = 'nfc_counter.'
    self.COUNTERS = [{
        'name': 'contact_lens_uses_left',
        'name_right': 'contact_lens_uses_right',
        'message_name': 'contact lens use count',
        'tag_id': 'f106326d-9a8c-485b-8d1c-723c25fb5c8b',
        'initial_value': 1,
      }, {
        'name': 'floss_uses',
        'message_name': 'floss use count',
        'tag_id': '77dd76fe-ce27-47bc-9b9a-f8ca2844e9e9',
      }]
    self.listen_event(self.on_tag_scanned, 'tag_scanned')
    self.listen_event(self.on_notification_action, 'mobile_app_notification_action')

  def on_tag_scanned(self, event_name, data, kwargs):
    counter_spec = self.get_counter_spec_by_tag_id(data['tag_id'])
    self.log(counter_spec)
    if not counter_spec:
      return
    name = counter_spec['name']
    if name == 'contact_lens_uses_left':
      self.contact_lens_tag_scanned(counter_spec)
    elif name == 'floss_uses':
      self.floss_scanned()

  def contact_lens_tag_scanned(self, counter_spec):
    uses_left = self.increment_counter('contact_lens_uses_left')
    uses_right = self.increment_counter('contact_lens_uses_right')
    remaining_left = 14 - uses_left
    remaining_right = 14 - uses_right

    if remaining_left < 0 and remaining_right < 0:
      message = f'Replace contacts, as these have had {uses_left} (L) + {uses_right} (R) uses.'
    elif remaining_left == 0 and remaining_right == 0:
      message = 'This is the last day of using this pair of contacts!'
    elif remaining_left < 0:
      message = f'Replace left contact, as it has {uses_left} uses. Right has {remaining_right}.'
    elif remaining_right < 0:
      message = f'Replace right contact, as it has {uses_right} uses. Left has {remaining_left}.'
    elif remaining_left == remaining_right:
      message = f'{remaining_left} days of contact lens wear remaining.'
    else:
      message = f'{remaining_left} (L) + {remaining_right} (R) days of contact lens wear remaining.'

    self.notify(counter_spec, message)

  def floss_scanned(self):
    self.increment_counter('floss_uses')

  def get_counter_spec_by_tag_id(self, tag_id):
    for counter_spec in self.COUNTERS:
      if counter_spec['tag_id'] == tag_id:
        return counter_spec

  def get_counter_spec_by_name(self, name):
    for counter_spec in self.COUNTERS:
      if counter_spec['name'] == name:
        return counter_spec

  def increment_counter(self, name):
    new_count = self.get_counter(name) + 1
    self.set_counter(name, new_count)
    return new_count

  def decrement_counter(self, name):
    new_count = self.get_counter(name) - 1
    self.set_counter(name, new_count)
    return new_count

  def get_counter(self, name):
    full_name = 'nfc_counter.' + name
    count = self.get_state(full_name)
    return int(count) if count else 0

  def set_counter(self, name, count):
    full_name = 'nfc_counter.' + name
    self.set_state(full_name, state=count)

  def notify(self, counter_spec, message):
    name = counter_spec['name']
    name_right = counter_spec.get('name_right')
    actions = []
    if counter_spec['initial_value'] != None:
      actions.append({
          'action': 'nfc_counter reset ' + name,
          'title': 'Reset',
          'destructive': True,
          })
    actions.append({
          'action': 'nfc_counter decrement ' + name,
          'title': 'Undo',
         })
    self.send_message(message, actions)

  def send_message(self, message, actions=[]):
    self.call_service(
      'notify/mobile_app_pixel_6a',
      message=message,
      data={'actions': actions})

  def on_notification_action(self, event_name, data, kwargs):
    raw_action = data['action']
    if not raw_action.startswith('nfc_counter '):
      return

    _, action, counter_name = raw_action.split()

    counter_spec = self.get_counter_spec_by_name(counter_name)
    if not counter_spec:
      self.log(f'Failed to find counter {counter_name}')
      return

    name = counter_spec['name']
    message_name = counter_spec['message_name']
    initial_value = counter_spec.get('initial_value')
    if action == 'reset':
      if counter_spec['name_right']:
        self.send_message(
          f'Which {message_name} to reset?',
          [{
            'action': 'nfc_counter reset_left ' + counter_name,
            'title': 'Reset Left',
          }, {
            'action': 'nfc_counter reset_right ' + counter_name,
            'title': 'Reset Right ',
          }, {
            'action': 'nfc_counter reset_both ' + counter_name,
            'title': 'Reset Both',
          }])
      else:
        self.set_counter(name, initial_value)
        self.send_message(f'Reset {message_name} to {initial_value}.')
    elif action == 'reset_left':
      self.set_counter(name, initial_value)
      self.send_message(f'Reset left {message_name} to {initial_value}.')
    elif action == 'reset_right':
      self.set_counter(counter_spec['name_right'], initial_value)
      self.send_message(f'Reset right {message_name} to {initial_value}.')
    elif action == 'reset_both':
      self.set_counter(name, initial_value)
      self.set_counter(counter_spec['name_right'], initial_value)
      self.send_message(f'Reset both {message_name} to {initial_value}.')
    elif action == 'decrement':
      new_count = self.decrement_counter()
      self.send_message(f'Decremented {message_name} to {new_count}.')

  def strip_prefix(self, text, prefix):
    if text.startswith(prefix):
      return text[len(prefix):]
    return None
