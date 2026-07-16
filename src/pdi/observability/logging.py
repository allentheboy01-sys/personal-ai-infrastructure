import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """配置 PDI 的控制台日志。"""

    numeric_level = getattr(logging, level.upper(), None)

    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid logging level: {level}")

    logging.basicConfig(
        level=numeric_level,
        format=(
            "%(asctime)s "
            "%(levelname)-8s "
            "%(name)s - "
            "%(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )