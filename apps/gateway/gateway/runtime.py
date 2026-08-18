"""Gateway runtime placeholder until ARI supervision is introduced in Phase 02."""

import logging

logging.basicConfig(level=logging.INFO)


def main() -> None:
    logger = logging.getLogger(__name__)
    logger.info("Gateway runtime started; Asterisk transport is not configured yet")


if __name__ == "__main__":
    main()
