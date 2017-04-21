from django.conf import settings


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


def find_and_fire_hook(event_name, instance, user_override=None):
    """
    Look up Hooks that apply
    """
    from django.contrib.auth.models import User
    from rest_hooks.models import Hook, HOOK_EVENTS

    if not event_name in HOOK_EVENTS.keys():
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

    hooks = Hook.objects.filter(**filters)
    for hook in hooks:
        hook.deliver_hook(instance)


def distill_model_event(instance, model, action, user_override=None):
    """
    Take created, updated and deleted actions for built-in 
    app/model mappings, convert to the defined event.name
    and let hooks fly.

    If that model isn't represented, we just quit silenty.
    """
    from rest_hooks.models import HOOK_EVENTS

    event_name = None
    for maybe_event_name, auto in HOOK_EVENTS.items():
        if auto:
            # break auto into App.Model, Action
            maybe_model, maybe_action = auto.rsplit('.', 1)
            maybe_action = maybe_action.rsplit('+', 1)
            if model == maybe_model and action == maybe_action[0]:
                event_name = maybe_event_name
                if len(maybe_action) == 2:
                    user_override = False

    if event_name:
        finder = find_and_fire_hook
        if getattr(settings, 'HOOK_FINDER', None):
            finder = get_module(settings.HOOK_FINDER)
        finder(event_name, instance, user_override=user_override)
