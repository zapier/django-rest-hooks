import requests
import time
from mock import patch, MagicMock, ANY

from datetime import datetime

try:
    # Django <= 1.6 backwards compatibility
    from django.utils import simplejson as json
except ImportError:
    # Django >= 1.7
    import json

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.test import TestCase
from django.test.utils import override_settings
try:
    from django.contrib.comments.models import Comment
    comments_app_label = 'comments'
except ImportError:
    from django_comments.models import Comment
    comments_app_label = 'django_comments'

from rest_hooks import models
from rest_hooks import signals
from rest_hooks.admin import HookForm

Hook = models.Hook


urlpatterns = []
HOOK_EVENTS_OVERRIDE = {
    'comment.added':        comments_app_label + '.Comment.created',
    'comment.changed':      comments_app_label + '.Comment.updated',
    'comment.removed':      comments_app_label + '.Comment.deleted',
    'comment.moderated':    comments_app_label + '.Comment.moderated',
    'special.thing':        None,
}

ALT_HOOK_EVENTS = dict(HOOK_EVENTS_OVERRIDE)
ALT_HOOK_EVENTS['comment.moderated'] += '+'


@override_settings(HOOK_EVENTS=HOOK_EVENTS_OVERRIDE, HOOK_DELIVERER=None)
class RESTHooksTest(TestCase):
    """
    This test Class uses real HTTP calls to a requestbin service, making it easy
    to check responses and endpoint history.
    """

    #############
    ### TOOLS ###
    #############

    def setUp(self):
        self.client = requests # force non-async for test cases

        self.user = User.objects.create_user('bob', 'bob@example.com', 'password')
        self.site, created = Site.objects.get_or_create(domain='example.com', name='example.com')

    def make_hook(self, event, target):
        return Hook.objects.create(
            user=self.user,
            event=event,
            target=target
        )

    #############
    ### TESTS ###
    #############

    @override_settings(HOOK_EVENTS=ALT_HOOK_EVENTS)
    def test_get_event_actions_config(self):
        self.assertEquals(
            models.get_event_actions_config(),
            {
                comments_app_label + '.Comment': {
                    'created': ('comment.added', False),
                    'updated': ('comment.changed', False),
                    'deleted': ('comment.removed', False),
                    'moderated': ('comment.moderated', True),
                },
            }
        )

    def test_no_user_property_fail(self):
        with self.assertRaises(Exception):
            models.find_and_fire_hook('some.fake.event', self.user)

        models.find_and_fire_hook('special.thing', self.user)

    def test_no_hook(self):
        comment = Comment.objects.create(
            site=self.site,
            content_object=self.user,
            user=self.user,
            comment='Hello world!'
        )

    @patch('rest_hooks.models.client.post', autospec=True)
    def perform_create_request_cycle(self, method_mock):
        method_mock.return_value = None

        target = 'http://example.com/perform_create_request_cycle'
        hook = self.make_hook('comment.added', target)

        comment = Comment.objects.create(
            site=self.site,
            content_object=self.user,
            user=self.user,
            comment='Hello world!'
        )
        # time.sleep(1) # should change a setting to turn off async

        return hook, comment, json.loads(method_mock.call_args_list[0][1]['data'])

    def test_simple_comment_hook(self):
        """
        Uses the default serializer.
        """
        hook, comment, payload = self.perform_create_request_cycle()

        self.assertEquals(hook.id, payload['hook']['id'])
        self.assertEquals('comment.added', payload['hook']['event'])
        self.assertEquals(hook.target, payload['hook']['target'])

        self.assertEquals(comment.id, payload['data']['pk'])
        self.assertEquals('Hello world!', payload['data']['fields']['comment'])
        self.assertEquals(comment.user.id, payload['data']['fields']['user'])

    def test_comment_hook_serializer_method(self):
        """
        Use custom serialize_hook on the Comment model.
        """
        def serialize_hook(comment, hook):
            return { 'hook': hook.dict(),
                     'data': { 'id': comment.id,
                               'comment': comment.comment,
                               'user': { 'username': comment.user.username,
                                         'email': comment.user.email}}}
        Comment.serialize_hook = serialize_hook
        hook, comment, payload = self.perform_create_request_cycle()

        self.assertEquals(hook.id, payload['hook']['id'])
        self.assertEquals('comment.added', payload['hook']['event'])
        self.assertEquals(hook.target, payload['hook']['target'])

        self.assertEquals(comment.id, payload['data']['id'])
        self.assertEquals('Hello world!', payload['data']['comment'])
        self.assertEquals('bob', payload['data']['user']['username'])

        del Comment.serialize_hook

    @patch('rest_hooks.models.client.post')
    def test_full_cycle_comment_hook(self, method_mock):
        method_mock.return_value = None
        target = 'http://example.com/test_full_cycle_comment_hook'

        hooks = [self.make_hook(event, target) for event in ['comment.added', 'comment.changed', 'comment.removed']]

        # created
        comment = Comment.objects.create(
            site=self.site,
            content_object=self.user,
            user=self.user,
            comment='Hello world!'
        )
        # time.sleep(0.5) # should change a setting to turn off async

        # updated
        comment.comment = 'Goodbye world...'
        comment.save()
        # time.sleep(0.5) # should change a setting to turn off async

        # deleted
        comment.delete()
        # time.sleep(0.5) # should change a setting to turn off async

        payloads = [json.loads(call[2]['data']) for call in method_mock.mock_calls]

        self.assertEquals('comment.added', payloads[0]['hook']['event'])
        self.assertEquals('comment.changed', payloads[1]['hook']['event'])
        self.assertEquals('comment.removed', payloads[2]['hook']['event'])

        self.assertEquals('Hello world!', payloads[0]['data']['fields']['comment'])
        self.assertEquals('Goodbye world...', payloads[1]['data']['fields']['comment'])
        self.assertEquals('Goodbye world...', payloads[2]['data']['fields']['comment'])

    @patch('rest_hooks.models.client.post')
    def test_custom_instance_hook(self, method_mock):
        from rest_hooks.signals import hook_event

        method_mock.return_value = None
        target = 'http://example.com/test_custom_instance_hook'

        hook = self.make_hook('comment.moderated', target)

        comment = Comment.objects.create(
            site=self.site,
            content_object=self.user,
            user=self.user,
            comment='Hello world!'
        )

        hook_event.send(
            sender=comment.__class__,
            action='moderated',
            instance=comment
        )
        # time.sleep(1) # should change a setting to turn off async

        payloads = [json.loads(call[2]['data']) for call in method_mock.mock_calls]

        self.assertEquals('comment.moderated', payloads[0]['hook']['event'])
        self.assertEquals('Hello world!', payloads[0]['data']['fields']['comment'])

    @patch('rest_hooks.models.client.post')
    def test_raw_custom_event(self, method_mock):
        from rest_hooks.signals import raw_hook_event

        method_mock.return_value = None
        target = 'http://example.com/test_raw_custom_event'

        hook = self.make_hook('special.thing', target)

        raw_hook_event.send(
            sender=None,
            event_name='special.thing',
            payload={
                'hello': 'world!'
            },
            user=self.user
        )
        # time.sleep(1) # should change a setting to turn off async

        payload = json.loads(method_mock.mock_calls[0][2]['data'])

        self.assertEquals('special.thing', payload['hook']['event'])
        self.assertEquals('world!', payload['data']['hello'])

    def test_timed_cycle(self):
        return # basically a debug test for thread pool bit
        target = 'http://requestbin.zapier.com/api/v1/bin/test_timed_cycle'

        hooks = [self.make_hook(event, target) for event in ['comment.added', 'comment.changed', 'comment.removed']]

        for n in range(4):
            early = datetime.now()
            # fires N * 3 http calls
            for x in range(10):
                comment = Comment.objects.create(
                    site=self.site,
                    content_object=self.user,
                    user=self.user,
                    comment='Hello world!'
                )
                comment.comment = 'Goodbye world...'
                comment.save()
                comment.delete()
            total = datetime.now() - early

            print(total)

            while True:
                response = requests.get(target + '/view')
                sent = response.json
                if sent:
                    print(len(sent), models.async_requests.total_sent)
                if models.async_requests.total_sent >= (30 * (n+1)):
                    time.sleep(5)
                    break
                time.sleep(1)

        requests.delete(target + '/view') # cleanup to be polite

    def test_signal_emitted_upon_success(self):
        wrapper = lambda *args, **kwargs: None
        mock_handler = MagicMock(wraps=wrapper)

        signals.hook_sent_event.connect(mock_handler, sender=Hook)

        hook, comment, payload = self.perform_create_request_cycle()

        payload['data']['fields']['submit_date'] = ANY
        mock_handler.assert_called_with(signal=ANY, sender=Hook, payload=payload, instance=comment, hook=hook)

    def test_valid_form(self):

        form_data = {
            'user': self.user.id,
            'target': "http://example.com",
            'event': HookForm.get_admin_events()[0][0]
        }
        form = HookForm(data=form_data)
        self.assertTrue(form.is_valid())

    def test_form_save(self):
        form_data = {
            'user': self.user.id,
            'target': "http://example.com",
            'event': HookForm.get_admin_events()[0][0]
        }
        form = HookForm(data=form_data)

        self.assertTrue(form.is_valid())
        instance = form.save()
        self.assertIsInstance(instance, Hook)

    def test_invalid_form(self):
        form = HookForm(data={})
        self.assertFalse(form.is_valid())

    @override_settings(HOOK_CUSTOM_MODEL='rest_hooks.models.Hook')
    def test_get_custom_hook_model(self):
        # Using the default Hook model just to exercise get_hook_model's
        # lookup machinery.
        from rest_hooks.utils import get_hook_model
        from rest_hooks.models import AbstractHook
        HookModel = get_hook_model()
        self.assertIs(HookModel, Hook)
        self.assertTrue(issubclass(HookModel, AbstractHook))
