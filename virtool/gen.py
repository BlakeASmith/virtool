import inspect
import logging
import functools
import tornado.gen
import concurrent.futures


logger = logging.getLogger(__name__)

#: This 10-worker thread pool is created when the :module:`virtool.gen` module is imported. All functions decorated with
#: :function:`synchronous` are run in one of the threads in the pool. Implements
#: :class:`~concurrent.Futures.ThreadPoolExecutor`.
THREAD_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=10)

logger.debug("Created THREAD_POOL.")


def coroutine(func):
    """
    A decorator that takes applies the :func:`tornado.gen.coroutine` decorator to the passed function. Adds the
    attribute ``is_coroutine`` to the returned function so it can be recognized as a coroutine when the
    documentation is generated.

    :param func: the function to decorate.
    :type func: function

    :return: the decorated function.
    :rtype: function

    """
    # Make sure ``func`` is a user-defined function.
    if not inspect.isfunction(func):
        var_type = type(func)
        raise TypeError("Invalid type {} for func argument. Must be user-defined function".format(repr(var_type)))

    # The tornado.gen.coroutine decorator already implemented functools.wraps.
    wrapped = tornado.gen.coroutine(func)
    wrapped.is_coroutine = True

    return wrapped


def synchronous(func):
    """
    Returns a coroutine where the passed function is run in a separate thread using the
    :class:`~concurrent.futures.ThreadPoolExecutor` object referenced by :data:`.THREAD_POOL`. The attribute
    ``is_synchronous`` is set on the returned function so it is recognized as synchronous during documentation.

    :param func: the function to decorate.
    :type func: function

    :return: the decorated function.
    :rtype: function

    """
    @functools.wraps(func)
    @coroutine
    def wrapper(*args, **kwargs):
        response = yield THREAD_POOL.submit(func, *args, **kwargs)
        return response

    wrapper.is_synchronous = True

    return wrapper


def exposed_method(required_permissions, unprotected=False):
    """
    A decorator that makes the decorated function available to clients through a :class:`virtool.dispatcher.Dispatcher`
    by adding the ``is_exposed`` attribute to the returned function. The dispatcher will try to pass the
    :class:`Transaction` as the sole argument for the decorated function, allowing the function to access the data and
    connection information passed from the client. The decorated function **must** return a tuple containing:

    * a boolean indicating whether the function was called successfully
    * any data to pass back to the client in a transaction

    :param required_permissions: the requesting user must have these permissions for the function to be called.
    :type required_permissions: list

    :param unprotected: makes the method unprotected when ``False``, meaning unauthorized connections can call it.
    :type: bool

    :return: the decorated function
    :rtype: function

    """
    if not isinstance(required_permissions, list):
        raise TypeError(
            "Required permissions for an exposed method must be passed as a list (may be empty) to the decorator"
        )

    # This is the 'actual decorator' that returns the wrapper function.
    def decorator(func):
        # Add this attribute to the function so the dispatcher knows that function
        func.is_exposed = True

        if unprotected:
            func.is_unprotected = True

        # Decorate it the function so it is a Virtool coroutine.
        func = coroutine(func)

        @functools.wraps(func)
        @coroutine
        def wrapper(self, transaction):
            # Set to True if the requesting connection is allowed to call the exposed method.
            is_allowed = True

            if not unprotected:
                user = transaction.connection.user

                if required_permissions:
                    # A set of permissions the user has.
                    possessed_permissions = {perm for perm in required_permissions if user["permissions"][perm]}

                    # True if the required_permissions are included in the user's *permissions* field.
                    is_allowed = possessed_permissions == set(required_permissions)

                # Log a warning if the user was not permitted to call the function. This indicates the user is making
                # requests outside of the graphical UI.
                if not is_allowed:
                    message = "User {} attempted to call exposed method {}.{} without the required permissions".format(
                        transaction.connection.user["_id"],
                        transaction.interface,
                        transaction.method
                    )

                    raise RequiredPermissionError(message)

            result = yield func(self, transaction)

            try:
                # Try to unpack a two-member tuple into the success and data value. If this fails, the exposed method
                # is invalid because it does not return a two-member tuple.
                success, data = result

            except ValueError as err:
                arg = err.args[0]

                if "too many values to unpack" in arg or "not enough values to unpack" in arg:
                    raise TypeError("Exposed method must return a tuple of 2 items with the first being a bool")

                raise

            except TypeError as err:
                arg = err.args[0]

                if "object is not iterable" in arg:
                    raise TypeError("Exposed method must return a tuple of 2 items with the first being a bool")

                raise

            if not isinstance(success, bool):
                raise TypeError("Exposed method must return a tuple of 2 items with the first being a bool")

            transaction.fulfill(success, data)

        return wrapper

    return decorator


class RequiredPermissionError(Exception):
    pass
