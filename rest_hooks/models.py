from collections import OrderedDict

import requests

from django.conf import settings
from django.core import serializers
from django.db import models

try:
    # Django <= 1.6 backwards compatibility
    from django.utils import simplejson as json
except ImportError:
    # Django >= 1.7
    import json

from rest_hooks.utils import get_module, find_and_fire_hook, distill_model_event

from rest_hooks import signals


HOOK_EVENTS = getattr(settings, 'HOOK_EVENTS', None)
if HOOK_EVENTS is None:
    raise Exception('You need to define settings.HOOK_EVENTS!')

if getattr(settings, 'HOOK_THREADING', True):
    from rest_hooks.client import Client
    client = Client()
else:
    client = requests

AUTH_USER_MODEL = getattr(settings, 'AUTH_USER_MODEL', 'auth.User')


class Hook(models.Model):
    """
    Stores a representation of a Hook.
    """
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    user = models.ForeignKey(AUTH_USER_MODEL, related_name='hooks')
    event = models.CharField('Event', max_length=64,
                                      db_index=True,
                                      choices=[(e, e) for e in HOOK_EVENTS.keys()])
    target = models.URLField('Target URL', max_length=255)

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
        """
        payload = payload_override or self.serialize_hook(instance)
        if getattr(settings, 'HOOK_DELIVERER', None):
            deliverer = get_module(settings.HOOK_DELIVERER)
            deliverer(self.target, payload, instance=instance, hook=self)
        else:
            client.post(
                url=self.target,
                data=json.dumps(payload, cls=serializers.json.DjangoJSONEncoder),
                headers={'Content-Type': 'application/json'}
            )

        signals.hook_sent_event.send_robust(sender=self.__class__, payload=payload, instance=instance, hook=self)
        return None

    def __unicode__(self):
        return u'{} => {}'.format(self.event, self.target)


##############
### EVENTS ###
##############

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from rest_hooks.signals import hook_event, raw_hook_event


get_opts = lambda m: m._meta.concrete_model._meta


@receiver(post_save, dispatch_uid='instance-saved-hook')
def model_saved(sender, instance,
                        created,
                        raw,
                        using,
                        **kwargs):
    """
    Automatically triggers "created" and "updated" actions.
    """
    opts = get_opts(instance)
    model = '.'.join([opts.app_label, opts.object_name])
    action = 'created' if created else 'updated'
    distill_model_event(instance, model, action)


@receiver(post_delete, dispatch_uid='instance-deleted-hook')
def model_deleted(sender, instance,
                          using,
                          **kwargs):
    """
    Automatically triggers "deleted" actions.
    """
    opts = get_opts(instance)
    model = '.'.join([opts.app_label, opts.object_name])
    distill_model_event(instance, model, 'deleted')


@receiver(hook_event, dispatch_uid='instance-custom-hook')
def custom_action(sender, action,
                          instance,
                          user=None,
                          **kwargs):
    """
    Manually trigger a custom action (or even a standard action).
    """
    opts = get_opts(instance)
    model = '.'.join([opts.app_label, opts.object_name])
    distill_model_event(instance, model, action, user_override=user)


@receiver(raw_hook_event, dispatch_uid='raw-custom-hook')
def raw_custom_event(sender, event_name,
                             payload,
                             user,
                             send_hook_meta=True,
                             instance=None,
                             **kwargs):
    """
    Give a full payload
    """
    hooks = Hook.objects.filter(user=user, event=event_name)

    for hook in hooks:
        new_payload = payload
        if send_hook_meta:
            new_payload = {
                'hook': hook.dict(),
                'data': payload
            }

        hook.deliver_hook(instance, payload_override=new_payload)
