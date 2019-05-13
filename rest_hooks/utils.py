import django

try:
    from django.apps import apps as django_apps
except ImportError:
    django_apps = None
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

if django.VERSION >= (2, 0,):
    get_model_kwargs = {'require_ready': False}
else:
    get_model_kwargs = {}


def get_module(path):
    """
    A modified duplicate from Django's built in backend
    retriever.

        slugify = get_module('django.template.defaultfilters.slugify')
    """
    try:
        from importlib import import_module
    except ImportError as e:
        from django.utils.importlib import import_module

    try:
        mod_name, func_name = path.rsplit('.', 1)
        mod = import_module(mod_name)
    except ImportError as e:
        raise ImportError(
            'Error importing alert function {0}: "{1}"'.format(mod_name, e))

    try:
        func = getattr(mod, func_name)
    except AttributeError:
        raise ImportError(
            ('Module "{0}" does not define a "{1}" function'
                            ).format(mod_name, func_name))

    return func


def get_hook_model():
    """
    Returns the Custom Hook model if defined in settings,
    otherwise the default Hook model.
    """
    model_label = getattr(settings, 'HOOK_CUSTOM_MODEL', None)
    if django_apps:
        model_label = (model_label or 'rest_hooks.Hook').replace('.models.', '.')
        try:
            return django_apps.get_model(model_label, **get_model_kwargs)
        except ValueError:
            raise ImproperlyConfigured("HOOK_CUSTOM_MODEL must be of the form 'app_label.model_name'")
        except LookupError:
            raise ImproperlyConfigured(
                "HOOK_CUSTOM_MODEL refers to model '%s' that has not been installed" % model_label
            )
    else:
        if model_label in (None, 'rest_hooks.Hook'):
            from rest_hooks.models import Hook
            HookModel = Hook
        else:
            try:
                HookModel = get_module(settings.HOOK_CUSTOM_MODEL)
            except ImportError:
                raise ImproperlyConfigured(
                    "HOOK_CUSTOM_MODEL refers to model '%s' that cannot be imported" % model_label
                )
        return HookModel



def find_and_fire_hook(event_name, instance, user_override=None, payload_override=None):
    """
    Look up Hooks that apply
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
    except ImportError:
        from django.contrib.auth.models import User
    from rest_hooks.models import HOOK_EVENTS

    if event_name not in HOOK_EVENTS.keys():
        raise Exception(
            '"{}" does not exist in `settings.HOOK_EVENTS`.'.format(event_name)
        )

    filters = {'event': event_name}

    # Ignore the user if the user_override is False
    if user_override is not False:
        if user_override:
            filters['user'] = user_override
        elif hasattr(instance, 'user'):
            filters['user'] = instance.user
        elif isinstance(instance, User):
            filters['user'] = instance
        else:
            raise Exception(
                '{} has no `user` property. REST Hooks needs this.'.format(repr(instance))
            )
    # NOTE: This is probably up for discussion, but I think, in this
    # case, instead of raising an error, we should fire the hook for
    # all users/accounts it is subscribed to. That would be a genuine
    # usecase rather than erroring because no user is associated with
    # this event.

    HookModel = get_hook_model()

    hooks = HookModel.objects.filter(**filters)
    for hook in hooks:
        hook.deliver_hook(instance, payload_override=payload_override)


def distill_model_event(
        instance,
        model=False,
        action=False,
        user_override=None,
        event_name=False,
        trust_event_name=False,
        payload_override=None,
        ):
    """
    Take `event_name` or determine it using action and model
    from settings.HOOK_EVENTS, and let hooks fly.

    if `event_name` is passed together with `model` or `action`, then
    they should be the same as in settings or `trust_event_name` should be
    `True`

    If event_name is not found or is invalidated, then just quit silently.

    If payload_override is passed, then it will be passed into HookModel.deliver_hook

    """
    from rest_hooks.models import get_event_actions_config, HOOK_EVENTS

    if event_name is False and (model is False or action is False):
        raise TypeError(
            'distill_model_event() requires either `event_name` argument or '
            'both `model` and `action` arguments.'
        )
    if event_name:
        if trust_event_name:
            pass
        elif event_name in HOOK_EVENTS:
            auto = HOOK_EVENTS[event_name]
            if auto:
                allowed_model, allowed_action = auto.rsplit('.', 1)

                allowed_action_parts = allowed_action.rsplit('+', 1)
                allowed_action = allowed_action_parts[0]

                model = model or allowed_model
                action = action or allowed_action

                if not (model == allowed_model and action == allowed_action):
                    event_name = None

                if len(allowed_action_parts) == 2:
                    user_override = False
    else:
        event_actions_config = get_event_actions_config()

        event_name, ignore_user_override = event_actions_config.get(model, {}).get(action, (None, False))
        if ignore_user_override:
            user_override = False

    if event_name:
        if getattr(settings, 'HOOK_FINDER', None):
            finder = get_module(settings.HOOK_FINDER)
        else:
            finder = find_and_fire_hook
        finder(event_name, instance, user_override=user_override, payload_override=payload_override)
