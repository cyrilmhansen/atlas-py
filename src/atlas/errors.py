class AtlasError(Exception):
    pass


class ValidationError(AtlasError, ValueError):
    pass


class AdmissionError(AtlasError):
    pass


class ClosedStoreError(AtlasError):
    pass
