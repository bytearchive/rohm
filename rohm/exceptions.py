__all__ = ['DoesNotExist', 'AlreadyExists', 'FieldValidationError']


class DoesNotExist(Exception):
    pass


class AlreadyExists(Exception):
    pass


class FieldValidationError(Exception):
    pass
