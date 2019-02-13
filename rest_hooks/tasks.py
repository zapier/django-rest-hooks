import requests
import json

from celery.task import Task

from django.core.serializers.json import DjangoJSONEncoder

from rest_hooks.utils import get_hook_model


class DeliverHook(Task):
    def run(self, target, payload, instance=None, hook_id=None, **kwargs):
        """
        target:     the url to receive the payload.
        payload:    a python primitive data structure
        instance:   a possibly null "trigger" instance
        hook:       the defining Hook object (useful for removing)
        """
        response = requests.post(
            url=target,
            data=json.dumps(payload, cls=DjangoJSONEncoder),
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 410 and hook_id:
            HookModel = get_hook_model()
            hook = HookModel.object.get(id=hook_id)
            hook.delete()

        # would be nice to log this, at least for a little while...

def deliver_hook_wrapper(target, payload, instance=None, hook=None, **kwargs):
    if hook:
        kwargs['hook_id'] = hook.id
    return DeliverHook.delay(target, payload, **kwargs)
