from collections import OrderedDict

import requests

import django
from django.conf import settings
from django.core import serializers
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models.signals import post_save, post_delete
from django.test.signals import setting_changed
from django.dispatch import receiver

try:
    # Django <= 1.6 backwards compatibility
    from django.utils import simplejson as json
except ImportError:
    # Django >= 1.7
    import json

from rest_hooks.signals import hook_event, raw_hook_event, hook_sent_event
from rest_hooks.utils import distill_model_event, get_hook_model, get_module, find_and_fire_hook


if getattr(settings, 'HOOK_CUSTOM_MODEL', None) is None:
    settings.HOOK_CUSTOM_MODEL = 'rest_hooks.Hook'

HOOK_EVENTS = getattr(settings, 'HOOK_EVENTS', None)
if HOOK_EVENTS is None:
    raise Exception('You need to define settings.HOOK_EVENTS!')

_HOOK_EVENT_ACTIONS_CONFIG = None


def get_event_actions_config():
    global _HOOK_EVENT_ACTIONS_CONFIG
    if _HOOK_EVENT_ACTIONS_CONFIG is None:
        _HOOK_EVENT_ACTIONS_CONFIG = {}
        for event_name, auto in HOOK_EVENTS.items():
            if not auto:
                continue
            model_label, action = auto.rsplit('.', 1)
            action_parts = action.rsplit('+', 1)
            action = action_parts[0]
            ignore_user_override = False
            if len(action_parts) == 2:
                ignore_user_override = True

            model_config = _HOOK_EVENT_ACTIONS_CONFIG.setdefault(model_label, {})
            if action in model_config:
                raise ImproperlyConfigured(
                    "settings.HOOK_EVENTS have a dublicate {action} for model "
                    "{model_label}".format(action=action, model_label=model_label)
                )
            model_config[action] = (event_name, ignore_user_override,)
    return _HOOK_EVENT_ACTIONS_CONFIG


if getattr(settings, 'HOOK_THREADING', True):
    from rest_hooks.client import Client
    client = Client()
else:
    client = requests.Session()

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')


class AbstractHook(models.Model):
    """
    Stores a representation of a Hook.
    """
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    user = models.ForeignKey(AUTH_USER_MODEL, related_name='%(class)ss', on_delete=models.CASCADE)
    event = models.CharField('Event', max_length=64, db_index=True)
    target = models.URLField('Target URL', max_length=255)

    class Meta:
        abstract = True

    def clean(self):
        """ Validation for events. """
        if self.event not in HOOK_EVENTS.keys():
            raise ValidationError(
                "Invalid hook event {evt}.".format(evt=self.event)
            )

    def dict(self):
        return {
            'id': self.id,
            'event': self.event,
            'target': self.target
        }

    def serialize_hook(self, instance):
        """
        Serialize the object down to Python primitives.

        By default it uses Django's built in serializer.
        """
        if getattr(instance, 'serialize_hook', None) and callable(instance.serialize_hook):
            return instance.serialize_hook(hook=self)
        if getattr(settings, 'HOOK_SERIALIZER', None):
            serializer = get_module(settings.HOOK_SERIALIZER)
            return serializer(instance, hook=self)
        # if no user defined serializers, fallback to the django builtin!
        data = serializers.serialize('python', [instance])[0]
        for k, v in data.items():
            if isinstance(v, OrderedDict):
                data[k] = dict(v)

        if isinstance(data, OrderedDict):
            data = dict(data)

        return {
            'hook': self.dict(),
            'data': data,
        }

    def deliver_hook(self, instance, payload_override=None):
        """
        Deliver the payload to the target URL.

        By default it serializes to JSON and POSTs.

        Args:
            instance: instance that triggered event.
            payload_override: JSON-serializable object or callable that will
                return such object. If callable is used it should accept 2
                arguments: `hook` and `instance`.
        """
        if payload_override is None:
            payload = self.serialize_hook(instance)
        else:
            payload = payload_override

        if callable(payload):
            payload = payload(self, instance)

        if getattr(settings, 'HOOK_DELIVERER', None):
            deliverer = get_module(settings.HOOK_DELIVERER)
            deliverer(self.target, payload, instance=instance, hook=self)
        else:
            client.post(
                url=self.target,
                data=json.dumps(payload, cls=DjangoJSONEncoder),
                headers={'Content-Type': 'application/json'}
            )

        hook_sent_event.send_robust(sender=self.__class__, payload=payload, instance=instance, hook=self)
        return None

    def __unicode__(self):
        return u'{} => {}'.format(self.event, self.target)


class Hook(AbstractHook):
    if django.VERSION >= (1, 7):
        class Meta(AbstractHook.Meta):
            swappable = 'HOOK_CUSTOM_MODEL'



##############
### EVENTS ###
##############


def get_model_label(instance):
    if instance is None:
        return None
    opts = instance._meta.concrete_model._meta
    try:
        return opts.label
    except AttributeError:
        return '.'.join([opts.app_label, opts.object_name])


@receiver(post_save, dispatch_uid='instance-saved-hook')
def model_saved(sender, instance,
                        created,
                        raw,
                        using,
                        **kwargs):
    """
    Automatically triggers "created" and "updated" actions.
    """
    model_label = get_model_label(instance)
    action = 'created' if created else 'updated'
    distill_model_event(instance, model_label, action)


@receiver(post_delete, dispatch_uid='instance-deleted-hook')
def model_deleted(sender, instance,
                          using,
                          **kwargs):
    """
    Automatically triggers "deleted" actions.
    """
    model_label = get_model_label(instance)
    distill_model_event(instance, model_label, 'deleted')


@receiver(hook_event, dispatch_uid='instance-custom-hook')
def custom_action(sender, action,
                          instance,
                          user=None,
                          **kwargs):
    """
    Manually trigger a custom action (or even a standard action).
    """
    model_label = get_model_label(instance)
    distill_model_event(instance, model_label, action, user_override=user)


@receiver(raw_hook_event, dispatch_uid='raw-custom-hook')
def raw_custom_event(
        sender,
        event_name,
        payload,
        user,
        send_hook_meta=True,
        instance=None,
        trust_event_name=False,
        **kwargs
        ):
    """
    Give a full payload
    """
    model_label = get_model_label(instance)

    new_payload = payload

    if send_hook_meta:
        new_payload = lambda hook, instance: {
            'hook': hook.dict(),
            'data': payload
        }

    distill_model_event(
        instance,
        model_label,
        None,
        user_override=user,
        event_name=event_name,
        trust_event_name=trust_event_name,
        payload_override=new_payload,
    )


@receiver(setting_changed)
def handle_hook_events_change(sender, setting, *args, **kwargs):
    global _HOOK_EVENT_ACTIONS_CONFIG
    global HOOK_EVENTS
    if setting == 'HOOK_EVENTS':
        _HOOK_EVENT_ACTIONS_CONFIG = None
        HOOK_EVENTS = settings.HOOK_EVENTS
