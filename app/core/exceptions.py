class AppException(Exception):
    """Custom exception for application-specific errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "APPLICATION_ERROR",
    ):
        """
        Initialize an application-specific exception.

        Args:
            message (str): Human-readable error message.
            status_code (int): HTTP status code associated with the error.Defaults to 400.
            error_code (str): Application-specific error identifier.Defaults to "APPLICATION_ERROR".
        """

        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)