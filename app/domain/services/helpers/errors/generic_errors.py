class InvalidFieldError(Exception):
    """
        InvalidFieldError is raised when a field is invalid.
    """

    def __init__(self, field: str, message: str = '') -> None:
        self.field = field
        self.message = message or f'Field {field} is invalid.'
        super().__init__(self.message)


class UnauthorizedError(Exception):
    """
        UnauthorizedError is raised when the user is not authorized.
    """

    def __init__(self, message: str = 'Unauthorized') -> None:
        self.message = message
        super().__init__(self.message)
