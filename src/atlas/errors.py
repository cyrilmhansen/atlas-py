class AtlasError(Exception):
    pass


class ValidationError(AtlasError, ValueError):
    pass


class AdmissionError(AtlasError):
    pass


class GroundingError(AtlasError):
    pass


class UnsupportedRuleError(GroundingError):
    pass


class ClosedStoreError(AtlasError):
    pass
