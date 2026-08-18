class DataStatusError(RuntimeError):
    code = "data_status_unavailable"


class DataStatusUnavailableError(DataStatusError):
    pass
