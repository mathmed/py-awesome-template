
class InvalidPasswordError(Exception):
    """Raised when the password is invalid."""

    def __init__(self, message: str = "Invalid password"):
        self.message = message
        super().__init__(self.message)


class UserNotFoundError(Exception):
    """Raised when the user is not found."""

    def __init__(self, message: str = "User not found"):
        self.message = message
        super().__init__(self.message)


class EmailAlreadyExistsError(Exception):
    """Raised when the email already exists."""

    def __init__(self, message: str = "Email already exists"):
        self.message = message
        super().__init__(self.message)
