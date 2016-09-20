[![Travis CI Build](https://img.shields.io/travis/zapier/django-rest-hooks/master.svg)](https://travis-ci.org/zapier/django-rest-hooks)
[![PyPI Download](https://img.shields.io/pypi/v/django-rest-hooks.svg)](https://pypi.python.org/pypi/django-rest-hooks)
[![PyPI Status](https://img.shields.io/pypi/status/django-rest-hooks.svg)](https://pypi.python.org/pypi/django-rest-hooks)
## What are Django REST Hooks?


REST Hooks are fancier versions of webhooks. Traditional webhooks are usually
managed manually by the user, but REST Hooks are not! They encourage RESTful
access to the hooks (or subscriptions) themselves. Add one, two or 15 hooks for
any combination of event and URLs, then get notificatied in real-time by our
bundled threaded callback mechanism.

The best part is: by reusing Django's great signals framework, this library is
dead simple. Here's how to get started:

1. Add `'rest_hooks'` to installed apps in settings.py.
2. Define your `HOOK_EVENTS` in settings.py.
3. Start sending hooks!

Using our **built-in actions**, zero work is required to support *any* basic `created`,
`updated`, and `deleted` actions across any Django model. We also allow for
**custom actions** (IE: beyond **C**R**UD**) to be simply defined and triggered
for any model, as well as truly custom events that let you send arbitrary
payloads.

By default, this library will just POST Django's JSON serialization of a model,
but you can alternatively provide a `serialize_hook` method to customize payloads.

*Please note:* this package does not implement any UI/API code, it only
provides a handy framework or reference implementation for which to build upon.
If you want to make a Django form or API resource, you'll need to do that yourself
(though we've provided some example bits of code below).


### Development

Running the tests for Django REST Hooks is very easy, just:

```
git clone https://github.com/zapier/django-rest-hooks && cd django-rest-hooks
```

Next, you'll want to make a virtual environment (we recommend using virtualenvwrapper
but you could skip this we suppose) and then install dependencies:

```
mkvirtualenv django-rest-hooks
pip install -r devrequirements.txt
```

Now you can run the tests!

```
python runtests.py
```

### Requirements
* Python (2.7, 3.3, 3.4)
* Django (1.5, 1.6, 1.7, 1.8, 1.9)

### Installing & Configuring

We recommend pip to install Django REST Hooks:

```
pip install django-rest-hooks
```

Next, you'll need to add `rest_hooks` to `INSTALLED_APPS` and configure
your `HOOK_EVENTS` setting:

```python
### settings.py ###

INSTALLED_APPS = (
    # other apps here...
    'rest_hooks',
)

HOOK_EVENTS = {
    # 'any.event.name': 'App.Model.Action' (created/updated/deleted)
    'book.added':       'bookstore.Book.created',
    'book.changed':     'bookstore.Book.updated+',
    'book.removed':     'bookstore.Book.deleted',
    # and custom events, no extra meta data needed
    'book.read':         'bookstore.Book.read',
    'user.logged_in':    None
}

### bookstore/models.py ###

class Book(models.Model):
    # NOTE: it is important to have a user property
    # as we use it to help find and trigger each Hook
    # which is specific to users. If you want a Hook to
    # be triggered for all users, add '+' to built-in Hooks
    # or pass user_override=False for custom_hook events
    user = models.ForeignKey('auth.User')
    # maybe user is off a related object, so try...
    # user = property(lambda self: self.intermediary.user)

    title = models.CharField(max_length=128)
    pages = models.PositiveIntegerField()
    fiction = models.BooleanField()

    # ... other fields here ...

    def serialize_hook(self, hook):
        # optional, there are serialization defaults
        # we recommend always sending the Hook
        # metadata along for the ride as well
        return {
            'hook': hook.dict(),
            'data': {
                'id': self.id,
                'title': self.title,
                'pages': self.pages,
                'fiction': self.fiction,
                # ... other fields here ...
            }
        }

    def mark_as_read(self):
        # models can also have custom defined events
        from rest_hooks.signals import hook_event
        hook_event.send(
            sender=self.__class__,
            action='read',
            instance=self # the Book object
        )
```

For the simplest experience, you'll just piggyback off the standard ORM which will
handle the basic `created`, `updated` and `deleted` signals & events:

```python
>>> from django.contrib.auth.models import User
>>> from rest_hooks.model import Hook
>>> jrrtolkien = User.objects.create(username='jrrtolkien')
>>> hook = Hook(user=jrrtolkien,
                event='book.added',
                target='http://example.com/target.php')
>>> hook.save()     # creates the hook and stores it for later...
>>> from bookstore.models import Book
>>> book = Book(user=jrrtolkien,
                title='The Two Towers',
                pages=327,
                fiction=True)
>>> book.save()     # fires off 'bookstore.Book.created' hook automatically
...
```

> NOTE: If you try to register an invalid event hook (not listed on HOOK_EVENTS in settings.py)
you will get a **ValidationError**.

Now that the book has been created, `http://example.com/target.php` will get:

```
POST http://example.com/target.php \
    -H Content-Type: application/json \
    -d '{"hook": {
           "id":      123,
           "event":   "book.added",
           "target":  "http://example.com/target.php"},
         "data": {
           "title":   "The Two Towers",
           "pages":   327,
           "fiction": true}}'
```

You can continue the example, triggering two more hooks in a similar method. However,
since we have no hooks set up for `'book.changed'` or `'book.removed'`, they wouldn't get
triggered anyways.

```python
...
>>> book.title += ': Deluxe Edition'
>>> book.pages = 352
>>> book.save()     # would fire off 'bookstore.Book.updated' hook automatically
>>> book.delete()   # would fire off 'bookstore.Book.deleted' hook automatically
```

You can also fire custom events with an arbitrary payload:

```python
from rest_hooks.signals import raw_hook_event

user = User.objects.get(id=123)
raw_hook_event.send(
    sender=None,
    event_name='user.logged_in',
    payload={
        'username': user.username,
        'email': user.email,
        'when': datetime.datetime.now().isoformat()
    },
    user=user # required: used to filter Hooks
)
```


### How does it work?

Django has a stellar [signals framework](https://docs.djangoproject.com/en/dev/topics/signals/), all
REST Hooks does is register to receive all `post_save` (created/updated) and `post_delete` (deleted)
signals. It then filters them down by:

1. Which `App.Model.Action` actually have an event registered in `settings.HOOK_EVENTS`.
2. After it verifies that a matching event exists, it searches for matching Hooks via the ORM.
3. Any Hooks that are found for the User/event combination get sent a payload via POST.


### How would you interact with it in the real world?

**Let's imagine for a second that you've plugged REST Hooks into your API**.
One could definitely provide a user interface to create hooks themselves via
a standard browser & HTML based CRUD interface, but the real magic is when
the Hook resource is part of an API.

The basic target functionality is:

```shell
POST http://your-app.com/api/hooks?username=me&api_key=abcdef \
    -H Content-Type: application/json \
    -d '{"target":    "http://example.com/target.php",
         "event":     "book.added"}'
```

Now, whenever a Book is created (either via an ORM, a Django form, admin, etc...),
`http://example.com/target.php` will get:

```shell
POST http://example.com/target.php \
    -H Content-Type: application/json \
    -d '{"hook": {
           "id":      123,
           "event":   "book.added",
           "target":  "http://example.com/target.php"},
         "data": {
           "title":   "Structure and Interpretation of Computer Programs",
           "pages":   657,
           "fiction": false}}'
```

*It is important to note that REST Hooks will handle all of this hook
callback logic for you automatically.*

But you can stop it anytime you like with a simple:

```
DELETE http://your-app.com/api/hooks/123?username=me&api_key=abcdef
```

If you already have a REST API, this should be relatively straightforward,
but if not, Tastypie is a great choice.

Some reference [Tastypie](http://tastypieapi.org/) or [Django REST framework](http://django-rest-framework.org/): + REST Hook code is below.

#### Tastypie

```python
### resources.py ###

from tastypie.resources import ModelResource
from tastypie.authentication import ApiKeyAuthentication
from tastypie.authorization import Authorization
from rest_hooks.models import Hook

class HookResource(ModelResource):
    def obj_create(self, bundle, request=None, **kwargs):
        return super(HookResource, self).obj_create(bundle,
                                                    request,
                                                    user=request.user)

    def apply_authorization_limits(self, request, object_list):
        return object_list.filter(user=request.user)

    class Meta:
        resource_name = 'hooks'
        queryset = Hook.objects.all()
        authentication = ApiKeyAuthentication()
        authorization = Authorization()
        allowed_methods = ['get', 'post', 'delete']
        fields = ['event', 'target']

### urls.py ###

from tastypie.api import Api

v1_api = Api(api_name='v1')
v1_api.register(HookResource())

urlpatterns = patterns('',
    (r'^api/', include(v1_api.urls)),
)
```
#### Django REST framework (3.+)

```python
### serializers.py ###

from rest_framework import serializers

from rest_hooks.models import Hook


class HookSerializer(serializers.ModelSerializer):

    class Meta:
        model = Hook
        read_only_fields = ('user',)

### views.py ###

from rest_framework import viewsets

from rest_hooks.models import Hook

from .serializers import HookSerializer


class HookViewSet(viewsets.ModelViewSet):
    """
    Retrieve, create, update or destroy webhooks.
    """
    model = Hook
    serializer_class = HookSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

### urls.py ###

from rest_framework import routers

from . import views

router = routers.SimpleRouter(trailing_slash=False)
router.register(r'webhooks', views.HookViewSet, 'webhook')

urlpatterns = router.urls
```

### Some gotchas:

Instead of doing blocking HTTP requests inside of signals, we've opted
for a simple Threading pool that should handle the majority of use cases.

However, if you use Celery, we'd *really* recommend using a simple task
to handle this instead of threads. A quick example:

```python
### settings.py ###

HOOK_DELIVERER = 'path.to.tasks.deliver_hook_wrapper'


### tasks.py ###

from celery.task import Task

import json
import requests


class DeliverHook(Task):
    max_retries = 5

    def run(self, target, payload, instance_id=None, hook_id=None, **kwargs):
        """
        target:     the url to receive the payload.
        payload:    a python primitive data structure
        instance_id:   a possibly None "trigger" instance ID
        hook_id:       the ID of defining Hook object
        """
        try:
            response = requests.post(
                url=target,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code >= 500:
                response.raise_for_response()
        except requests.ConnectionError:
            delay_in_seconds = 2 ** self.request.retries
            self.retry(countdown=delay_in_seconds)


def deliver_hook_wrapper(target, payload, instance, hook):
    # instance is None if using custom event, not built-in
    if instance is not None:
        instance_id = instance.id
    else:
        instance_id = None
    # pass ID's not objects because using pickle for objects is a bad thing
    kwargs = dict(target=target, payload=payload,
                  instance_id=instance_id, hook_id=hook.id)
    DeliverHook.apply_async(kwargs=kwargs)

```

We also don't handle retries or cleanup. Generally, if you get a `410` or
a bunch of `4xx` or `5xx`, you should delete the Hook and let the user know.
